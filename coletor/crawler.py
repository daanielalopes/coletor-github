"""
Coletor de repositórios do GitHub (documento principal do RI).

ESTRATÉGIA DE ESCALA (o ponto central para superar 50 mil documentos):
A Search API do GitHub devolve no máximo 1.000 resultados por consulta. Para
coletar muito mais que isso, PARTICIONAMOS o espaço de busca em milhares de
consultas disjuntas, cada uma com <= 1.000 resultados, e somamos os itens.

Particionamento adotado: por número EXATO de estrelas. Para cada valor S de
`star_min..star_max`, a consulta é `stars:S`. Como cada valor de estrela isola
um subconjunto pequeno de repositórios, quase todas as partições cabem no
limite de 1.000 — e a soma cobre dezenas/centenas de milhares de repositórios.

FLUXO:
  1. Gera as partições (fronteira), da mais rara (muitas estrelas) para a mais
     comum, e persiste em SQLite (permite retomar).
  2. Para cada partição: pagina a Search API (100/página, até 10 páginas =
     1.000 itens) coletando repositórios.
  3. De cada repositório: normaliza os metadados, extrai o proprietário
     (usuário) e, opcionalmente, baixa o README (texto rico para a busca).
  4. Critério de parada: meta de repositórios (padrão 50.000) OU partições
     esgotadas.
"""

import logging
from typing import Dict, List, Optional

from .config import CrawlerConfig
from .fetcher import Fetcher
from .storage import Storage

logger = logging.getLogger(__name__)


def parse_repository(item: Dict) -> Dict:
    """Normaliza um objeto de repositório da API para o nosso schema."""
    owner = item.get("owner") or {}
    lic = item.get("license") or {}
    return {
        "id": item.get("id"),
        "full_name": item.get("full_name"),
        "name": item.get("name"),
        "owner_login": owner.get("login"),
        "description": item.get("description"),
        "language": item.get("language"),
        "topics": item.get("topics", []) or [],
        "stars": item.get("stargazers_count"),
        "forks": item.get("forks_count"),
        "watchers": item.get("watchers_count"),
        "open_issues": item.get("open_issues_count"),
        "size_kb": item.get("size"),
        "license_name": lic.get("name"),
        "default_branch": item.get("default_branch"),
        "homepage": item.get("homepage"),
        "html_url": item.get("html_url"),
        "is_fork": item.get("fork"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "pushed_at": item.get("pushed_at"),
    }


def parse_owner(item: Dict) -> Dict:
    owner = item.get("owner") or {}
    return {
        "id": owner.get("id"),
        "login": owner.get("login"),
        "type": owner.get("type"),
        "html_url": owner.get("html_url"),
        "avatar_url": owner.get("avatar_url"),
    }


class Crawler:
    # A Search API só devolve os primeiros 1.000 resultados (10 páginas de 100).
    SEARCH_MAX_PAGES = 10

    def __init__(self, config: Optional[CrawlerConfig] = None):
        self.cfg = config or CrawlerConfig()
        self.fetcher = Fetcher(self.cfg)
        self.storage = Storage(
            self.cfg.output_dir, self.cfg.db_filename, self.cfg.raw_html_dir
        )
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
                "%d repos, %d usuarios.",
                len(pending), len(done), self._repos_saved,
                self.storage.user_count(),
            )
            return

        # Coleta nova: gerar partições por nº exato de estrelas.
        logger.info(
            "Coleta nova: gerando particoes por estrelas (%d..%d).",
            self.cfg.star_min, self.cfg.star_max,
        )
        parts = []
        # Da mais alta para a mais baixa (repos famosos primeiro).
        for s in range(self.cfg.star_max, self.cfg.star_min - 1, -1):
            key = f"stars={s}"
            if key in done:
                continue
            query = f"stars:{s}"
            parts.append((key, query, 1))
        self.storage.add_partitions(parts)
        logger.info("%d particoes criadas.", len(parts))

    # ---------------- Critério de parada ----------------
    def _target_reached(self) -> bool:
        return self._repos_saved >= self.cfg.target_pages

    # ---------------- Loop principal ----------------
    def run(self) -> None:
        self._bootstrap()
        logger.info(
            "Iniciando coleta. Meta: %d repositorios. Ja coletados: %d.",
            self.cfg.target_pages, self._repos_saved,
        )

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
            "Coleta finalizada. Repositorios: %d. Usuarios: %d. "
            "Particoes pendentes: %d.",
            self.storage.repo_count(), self.storage.user_count(),
            self.storage.partitions_pending(),
        )

    def _process_partition(self, key: str, query: str, start_page: int) -> None:
        full_query = f"{query} {self.cfg.search_base_query}".strip() \
            if query != self.cfg.search_base_query else query
        # Aqui a consulta JÁ é 'stars:S'; a base 'stars:>=1' é redundante,
        # então usamos apenas a consulta da partição.
        search_url = f"{self.cfg.api_base}/search/repositories"

        page = start_page
        while page <= self.SEARCH_MAX_PAGES and not self._target_reached():
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": self.cfg.per_page,
                "page": page,
            }
            data, resp = self.fetcher.get_json(search_url, params=params)
            if data is None:
                self.storage.record_failure(key, "search_failed",
                                            f"page={page}")
                break

            items = data.get("items", [])
            total = data.get("total_count", 0)
            if not items:
                break

            for item in items:
                self._save_repo_item(item)

            self.storage.update_partition_page(key, page + 1)
            self._maybe_checkpoint()

            logger.info(
                "[%s] pagina %d/%d -> +%d repos (total_count=%d, "
                "coletados=%d)",
                key, page, self.SEARCH_MAX_PAGES, len(items), total,
                self._repos_saved,
            )

            # Fim das páginas desta partição?
            if len(items) < self.cfg.per_page:
                break
            if page * self.cfg.per_page >= total:
                break
            page += 1

        self.storage.finish_partition(key)

    def _save_repo_item(self, item: Dict) -> None:
        repo = parse_repository(item)

        # README (texto rico para a fase de Indexação).
        if self.cfg.fetch_readme and repo.get("full_name"):
            readme = self._fetch_readme(repo["full_name"])
            if readme:
                readme = readme[: self.cfg.readme_max_bytes]
                repo["readme"] = readme
                if self.cfg.save_raw_html:
                    repo["readme_path"] = self.storage.save_raw_readme(
                        repo["full_name"], readme
                    )

        is_new = self.storage.save_repository(repo)
        self.storage.save_user(parse_owner(item))
        if is_new:
            self._repos_saved += 1
            if self._repos_saved % 100 == 0:
                logger.info("Progresso: %d repositorios.", self._repos_saved)

    def _fetch_readme(self, full_name: str) -> Optional[str]:
        url = f"{self.cfg.api_base}/repos/{full_name}/readme"
        return self.fetcher.get_text(url)

    def _maybe_checkpoint(self) -> None:
        self._processed_since_ckpt += 1
        if self._processed_since_ckpt >= self.cfg.checkpoint_every:
            self._processed_since_ckpt = 0
            self.storage.commit()

    def export(self) -> str:
        path = self.storage.export_jsonl()
        logger.info("Exportado JSONL para %s", path)
        return path

    def close(self) -> None:
        self.storage.close()
