"""
Coletor (motor genérico) — orquestra a coleta sobre MÚLTIPLAS FONTES.

Fontes (todas com a mesma abstração `Source`):
  - github_html : CRAWLER de HTML de github.com (parsing do DOM);
  - sourceforge : CRAWLER de HTML de sourceforge.net (segunda fonte);
  - github_api  : coletor pela API REST do GitHub (uses_api=True).

FLUXO (igual ao processo de coleta visto em aula):
  1. Inicializa a FRONTEIRA com partições/seeds de cada fonte (persistidas em
     arquivo -> permite RETOMAR).
  2. Enquanto a fronteira não esvazia e a meta não é atingida:
       - pega uma partição, baixa a página de listagem, extrai os itens;
       - para cada item novo (dedup): baixa o detalhe, extrai metadados +
         texto rico + proprietário, e SALVA em arquivo (JSONL);
       - avança a página da partição (checkpoint) até esgotá-la.
  3. Critério de parada: meta de documentos (limite offline) OU fronteira vazia.

ESCALA: o particionamento (por estrelas no GitHub; por faceta de SO/categoria
no SourceForge) gera milhares de listagens disjuntas cuja soma supera 50 mil.
"""

import logging
from typing import Dict, List, Optional

from .config import CrawlerConfig
from .fetcher import Fetcher
from .sources import get_source
from .storage import Storage

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self, config: Optional[CrawlerConfig] = None):
        self.cfg = config or CrawlerConfig()
        self.fetcher = Fetcher(self.cfg)
        self.storage = Storage(self.cfg.output_dir, self.cfg.raw_html_dir)
        # Instancia as fontes selecionadas.
        self.sources = {name: get_source(name) for name in self.cfg.sources}
        self._repos_saved = 0
        self._processed_since_ckpt = 0

    # ---------------- Inicialização / retomada ----------------
    def _bootstrap(self) -> None:
        self._repos_saved = self.storage.repo_count()
        pending = self.storage.load_partitions()
        done = self.storage.done_partition_keys()

        if pending:
            logger.info(
                "Retomando: %d particoes pendentes, %d concluidas, "
                "%d docs, %d usuarios.",
                len(pending), len(done), self._repos_saved,
                self.storage.user_count())
            return

        logger.info("Coleta nova: gerando particoes das fontes %s.",
                    list(self.sources))
        parts = []
        for name, source in self.sources.items():
            src_parts = source.build_partitions(self.cfg)
            parts.extend(src_parts)
            logger.info("  fonte %s: %d particoes.", name, len(src_parts))
        # Filtra partições já concluídas (retomada).
        parts = [p for p in parts if p[0] not in done]
        self.storage.add_partitions(parts)
        logger.info("%d particoes criadas no total.", len(parts))

    # ---------------- Critério de parada ----------------
    def _target_reached(self) -> bool:
        return self._repos_saved >= self.cfg.target_pages

    # ---------------- Loop principal ----------------
    def run(self) -> None:
        self._bootstrap()
        logger.info("Iniciando coleta. Meta: %d documentos. Ja coletados: %d.",
                    self.cfg.target_pages, self._repos_saved)

        while not self._target_reached():
            pending = self.storage.load_partitions()
            if not pending:
                logger.info("Todas as particoes foram processadas.")
                break
            for key, query, start_page in pending:
                if self._target_reached():
                    break
                self._process_partition(key, query, start_page)

        self.storage.commit()
        logger.info(
            "Coleta finalizada. Documentos: %d. Usuarios: %d. "
            "Particoes pendentes: %d.",
            self.storage.repo_count(), self.storage.user_count(),
            self.storage.partitions_pending())

    def _source_for(self, key: str):
        """A key da partição é prefixada com a fonte: 'gh:', 'sf:', 'api:'."""
        prefix = key.split(":", 1)[0]
        mapping = {"gh": "github_html", "sf": "sourceforge", "api": "github_api"}
        name = mapping.get(prefix)
        return self.sources.get(name) if name else None

    def _process_partition(self, key: str, query: str, start_page: int) -> None:
        source = self._source_for(key)
        if source is None:
            # Fonte não selecionada nesta execução: conclui a partição.
            self.storage.finish_partition(key)
            return

        page = start_page
        while page <= self.cfg.search_max_pages and not self._target_reached():
            url, params = source.listing_request(self.cfg, query, page)

            if getattr(source, "uses_api", False):
                data, _ = self.fetcher.get_json(
                    url, params=params,
                    extra_headers=self._api_headers(source))
                if data is None:
                    self.storage.record_failure(key, "listing_failed",
                                                f"page={page}")
                    break
                items = source.parse_listing_json(data)
                item_count = len(items)
                for item in items:
                    if self._target_reached():
                        break
                    self._save_api_item(source, item)
            else:
                html = self.fetcher.get_html(url, params=params)
                if html is None:
                    self.storage.record_failure(key, "listing_failed",
                                                f"page={page}")
                    break
                ids = source.parse_listing(html)
                item_count = len(ids)
                for item_id in ids:
                    if self._target_reached():
                        break
                    self._save_html_item(source, item_id)

            self.storage.update_partition_page(key, page + 1)
            self._maybe_checkpoint()
            logger.info("[%s] pagina %d/%d -> %d itens (coletados=%d)",
                        key, page, self.cfg.search_max_pages, item_count,
                        self._repos_saved)

            if item_count == 0 or item_count < self.cfg.per_page:
                break
            page += 1

        self.storage.finish_partition(key)

    def _api_headers(self, source) -> Dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = getattr(source, "token", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # ---------------- Salvar item (crawler HTML) ----------------
    def _save_html_item(self, source, item_id: str) -> None:
        # `full_name` = como o item é gravado; para o SourceForge é
        # 'sourceforge/<slug>'. Deduplicação por esse id.
        prospective = self._prospective_full_name(source, item_id)
        if prospective and self.storage.doc_exists(prospective):
            return

        detail_url = source.detail_url(item_id)
        html = self.fetcher.get_html(detail_url)
        if html is None:
            self.storage.record_failure(item_id, "detail_failed", detail_url)
            return

        repo = source.parse_detail(item_id, html)

        if self.cfg.fetch_readme:
            readme = source.parse_readme(html)
            if readme:
                readme = readme[: self.cfg.readme_max_bytes]
                repo["readme"] = readme
                if self.cfg.save_raw_html:
                    repo["readme_path"] = self.storage.save_raw_readme(
                        repo["full_name"], readme)

        is_new = self.storage.save_repository(repo)
        self.storage.save_user(source.parse_owner(item_id, repo))
        if is_new:
            self._bump()

    @staticmethod
    def _prospective_full_name(source, item_id: str) -> Optional[str]:
        if source.name == "sourceforge":
            return f"sourceforge/{item_id}"
        if source.name == "github_html":
            return item_id
        return None

    # ---------------- Salvar item (API) ----------------
    def _save_api_item(self, source, item: Dict) -> None:
        repo = source.parse_detail_json(item)
        if not repo.get("full_name"):
            return
        if self.storage.doc_exists(repo["full_name"]):
            return
        # A API não traz o README no item de busca; deixamos o texto rico para
        # descrição. (O README via API é opcional e custa +1 requisição/repo.)
        is_new = self.storage.save_repository(repo)
        self.storage.save_user(source.parse_owner_json(item))
        if is_new:
            self._bump()

    def _bump(self) -> None:
        self._repos_saved += 1
        if self._repos_saved % 100 == 0:
            logger.info("Progresso: %d documentos.", self._repos_saved)

    def _maybe_checkpoint(self) -> None:
        self._processed_since_ckpt += 1
        if self._processed_since_ckpt >= self.cfg.checkpoint_every:
            self._processed_since_ckpt = 0
            self.storage.commit()

    def export(self) -> str:
        path = self.storage.export_jsonl()
        logger.info("Acervo (JSONL) em %s", path)
        return path

    def close(self) -> None:
        self.storage.close()
