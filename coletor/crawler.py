"""
Coletor web clássico (modelo visto em aula), sem uso de nenhuma API.

Laço de cada site:
  1. começa com as seeds na fila;
  2. pega a próxima URL da fila, confere o robots.txt e baixa o HTML com GET;
  3. salva o conteúdo (HTML bruto em blocos gzip e, nas páginas de projeto,
     os campos extraídos);
  4. extrai os links da página;
  5. coloca na fila só os links novos (que não estão no conjunto de URLs
     conhecidas) e que passam no filtro de seleção;
  6. repete até atingir a meta de páginas de projeto ou a fila acabar.

Fila de Mercator simplificada: cada domínio tem a sua fila (no SQLite) e a
sua thread. Assim o GitHub e o SourceForge são coletados em paralelo, mas
cada site recebe no máximo um pedido por vez, com a espera mínima entre
pedidos. Nenhum dos dois é sobrecarregado.

Ordem da fila de cada site (as "filas de frente" do Mercator viram uma
prioridade):
  - prioridade 0: página de projeto achada numa listagem (tópico, diretório
    ou sitemap). A listagem já entrega os projetos que queremos, então eles
    são baixados logo em seguida;
  - prioridade 1: todo o resto (listagens, sitemaps e projetos citados em
    outros projetos, por exemplo num README);
  - dentro da mesma prioridade, a menor profundidade vem antes (busca em
    largura) e, empatando, vale a ordem de chegada.
"""

import logging
import os
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional

from .config import CrawlerConfig
from .extractors import (extract_github_cards, extract_github_repo,
                         extract_links, extract_sitemap_links,
                         extract_sourceforge_project, parse_html)
from .fetcher import Fetcher
from .robots import RobotsRules
from .sites import BASE_URLS, seed_urls
from .storage import BlockWriter, Storage
from .urls import GITHUB, SOURCEFORGE, classify, is_pagination, normalize, site_of

logger = logging.getLogger(__name__)

PRIORITY_PROJECT = 0
PRIORITY_OTHER = 1
REDIRECT_CODES = (301, 302, 303, 307, 308)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class SiteWorker(threading.Thread):
    """Thread que coleta um único domínio, usando a fila desse domínio."""

    def __init__(self, crawler: "Crawler", site: str):
        super().__init__(name=site, daemon=True)
        self.crawler = crawler
        self.cfg: CrawlerConfig = crawler.cfg
        self.site = site
        self.storage: Storage = crawler.storage
        self.stop_event = crawler.stop_event
        self.fetcher = Fetcher(self.cfg, self.stop_event)
        self.robots = RobotsRules(self.fetcher, BASE_URLS[site], self.cfg.user_agent)
        self.writer = BlockWriter(self.storage, self.cfg.raw_dir, site, self.cfg.block_size)
        self.projects = self.storage.project_count(site)
        self.pages = 0        # pedidos HTTP feitos nesta execução
        self.processed = 0    # URLs tiradas da fila nesta execução
        self.done = False
        self.root = normalize(BASE_URLS[site])
        self.suspects: List[Dict] = []   # respostas suspeitas seguidas (ver _track)
        self.kind_until: Dict[str, float] = {}   # tipo de página -> em espera até (ver _hold_kind)
        self.kind_wait: Dict[str, float] = {}    # tipo de página -> duração da última espera

    # ---------------- Laço principal ----------------
    def run(self) -> None:
        try:
            self._run()
        except Exception:
            logger.exception("Erro inesperado na thread %s. A thread foi encerrada.", self.site)
        finally:
            self.done = True
            self.writer.close()
            self.fetcher.close()

    def _run(self) -> None:
        if self.projects >= self.cfg.target_per_site:
            logger.info("Meta ja atingida: %d paginas de projeto.", self.projects)
            return
        if not self._load_robots():
            return
        self._add_sitemaps()

        while not self.stop_event.is_set():
            if self.projects >= self.cfg.target_per_site:
                logger.info("Meta atingida: %d paginas de projeto.", self.projects)
                return
            now = time.monotonic()
            held = {k for k, t in self.kind_until.items() if t > now}
            item = self.storage.next_url(self.site, exclude=held)
            if item is None:
                if held:
                    # Só sobraram tipos de página em espera: aguarda o primeiro liberar.
                    self.stop_event.wait(max(1.0, min(self.kind_until[k] for k in held) - now))
                    continue
                # A outra thread ainda pode achar links para este site.
                if self.crawler.others_running(self):
                    self.stop_event.wait(5)
                    continue
                logger.info("Fila vazia. Fim da coleta deste site.")
                return
            self._process(item)
            self.processed += 1
            if self.processed % 50 == 0:
                logger.info("Progresso: %d paginas baixadas nesta execucao, %d/%d projetos, fila com %d URLs.",
                            self.pages, self.projects, self.cfg.target_per_site,
                            self.storage.frontier_count(self.site))

    def _load_robots(self) -> bool:
        while not self.stop_event.is_set():
            if self.robots.load():
                host = BASE_URLS[self.site].split("//", 1)[1]
                self.fetcher.set_delay(host, self.robots.crawl_delay() or 0.0)
                return True
            logger.warning("Nova tentativa de ler o robots.txt em %.0fs.", self.cfg.robots_retry_wait)
            self.stop_event.wait(self.cfg.robots_retry_wait)
        return False

    def _add_sitemaps(self) -> None:
        """Coloca na fila os sitemaps listados no robots.txt que passam no filtro."""
        entries = []
        for sm in self.robots.sitemaps():
            url = normalize(sm)
            if url and site_of(url) == self.site and classify(url) == "sitemap":
                entries.append({"site": self.site, "url": url, "tipo": "sitemap",
                                "prioridade": PRIORITY_OTHER, "profundidade": 0,
                                "origem": "robots.txt"})
        added = self.storage.add_to_frontier(entries)
        if added:
            logger.info("%d sitemaps do robots.txt colocados na fila.", added)

    # ---------------- Seleção de links ----------------
    def _make_links(self, item: Dict, urls: List[str], redirect: bool = False) -> List[Dict]:
        """
        Filtra os links e calcula prioridade e profundidade de cada um.

        A próxima página de uma listagem (paginação) e os sitemaps citados
        por outro sitemap são continuação da mesma lista, não um nível mais
        fundo, então herdam a profundidade. O destino de um redirecionamento
        também herda profundidade e prioridade.
        """
        out = []
        for url in urls:
            site = site_of(url) if url else None
            if site is None:
                continue
            kind = classify(url)
            if kind is None:
                continue
            if redirect:
                depth, prio = item["profundidade"], item["prioridade"]
            else:
                same_list = is_pagination(item["url"], url) or (
                    item["tipo"] == "sitemap" and kind == "sitemap")
                depth = item["profundidade"] if same_list else item["profundidade"] + 1
                from_list = item["tipo"] in ("listing", "sitemap")
                prio = PRIORITY_PROJECT if (kind == "project" and from_list) else PRIORITY_OTHER
            if self.cfg.max_depth is not None and depth > self.cfg.max_depth:
                continue
            out.append({"site": site, "url": url, "tipo": kind, "prioridade": prio,
                        "profundidade": depth, "origem": item["url"]})
        return out

    # ---------------- Registro e detecção de pane do site ----------------
    def _record(self, item: Dict, visit: Dict, **kwargs) -> int:
        added = self.storage.record(item, visit, **kwargs)
        self._track(item, visit)
        return added

    def _track(self, item: Dict, visit: Dict) -> None:
        """
        Detecta quando o problema é do site e não da página.

        Durante uma instabilidade o SourceForge passou a redirecionar quase
        tudo para a página inicial e a servir páginas sem conteúdo com código
        200. Uma resposta dessas isolada é normal; muitas seguidas indicam que
        o site está com problema. Nesse caso as URLs voltam para a fila (elas
        não foram coletadas de verdade) e a thread pausa antes de continuar.
        """
        result = visit.get("resultado")
        if result == "bloqueada_robots":
            return
        suspicious = result == "soft404" or (
            result == "redirecionada" and visit.get("detalhe") == self.root)
        if not suspicious:
            self.suspects.clear()
            return
        self.suspects.append(item)
        if len(self.suspects) >= self.cfg.incident_threshold:
            n = self.storage.requeue(self.suspects)
            logger.warning("%d respostas suspeitas seguidas (soft-404 ou redirecionamento para a "
                           "pagina inicial): o site parece estar com problema. %d URLs voltaram "
                           "para a fila. Pausa de %.0fs.",
                           len(self.suspects), n, self.cfg.incident_pause)
            self.suspects.clear()
            self.stop_event.wait(self.cfg.incident_pause)

    def _hold_kind(self, kind: str) -> float:
        """Coloca um tipo de página em espera: 2 min, dobrando a cada falha seguida, até 1 h."""
        wait = min(max(2 * self.kind_wait.get(kind, 0.0), self.cfg.throttle_pause),
                   self.cfg.max_throttle_pause)
        self.kind_wait[kind] = wait
        self.kind_until[kind] = time.monotonic() + wait
        return wait

    # ---------------- Processamento de uma URL ----------------
    def _extract_project(self, soup, url: str) -> Optional[Dict]:
        if self.site == GITHUB:
            return extract_github_repo(soup, url, self.storage.hint(url),
                                       self.cfg.readme_max_chars)
        if self.site == SOURCEFORGE:
            return extract_sourceforge_project(soup, url)
        return None

    def _process(self, item: Dict) -> None:
        url, kind = item["url"], item["tipo"]
        visit = {"url": url, "site": self.site, "tipo": kind,
                 "profundidade": item["profundidade"], "coletado_em": now_iso()}

        # 2. robots.txt
        if not self.robots.allowed(url):
            visit["resultado"] = "bloqueada_robots"
            self._record(item, visit)
            logger.info("Bloqueada pelo robots.txt: %s", url)
            return

        # 2. GET
        res = self.fetcher.get(url)
        if res.interrupted:
            return  # parada pedida: a URL continua na fila para a próxima execução
        self.pages += 1
        visit.update({"status_http": res.status, "coletado_em": now_iso(),
                      "bytes": len(res.content)})

        if res.status is None:
            visit.update({"resultado": "erro_rede", "detalhe": res.error})
            self._record(item, visit)
            logger.warning("Erro de rede (desistindo): %s | %s", url, res.error)
            return

        if res.status in REDIRECT_CODES:
            target = normalize(res.headers.get("Location", ""), url)
            links = self._make_links(item, [target], redirect=True)
            visit.update({"resultado": "redirecionada", "detalhe": target})
            added = self._record(item, visit, links=links)
            logger.info("%d redirecionada %s -> %s%s", res.status, url, target,
                        "" if added else " (ignorada)")
            return

        if res.status in (429, 503):
            # O site continua pedindo para esperar mesmo depois do backoff. A URL
            # fica na fila e este tipo de página entra em espera; os outros
            # tipos continuam, no mesmo ritmo de sempre.
            wait = self._hold_kind(kind)
            logger.warning("HTTP %d persistente em %s. Paginas do tipo %s ficam em espera por "
                           "%.0f min; a URL continua na fila e a coleta segue com os outros tipos.",
                           res.status, url, kind, wait / 60)
            return

        if res.status != 200:
            visit.update({"resultado": "erro_http", "detalhe": f"HTTP {res.status}"})
            self._record(item, visit)
            logger.info("HTTP %d: %s", res.status, url)
            return

        self.kind_wait.pop(kind, None)  # o tipo voltou a responder: a próxima espera recomeça curta

        ctype = res.content_type
        project, hints, known = None, None, []

        if kind == "sitemap":
            if "xml" not in ctype and not res.content.lstrip().startswith(b"<?xml"):
                visit.update({"resultado": "tipo_invalido", "detalhe": ctype})
                self._record(item, visit)
                return
            found = extract_sitemap_links(res.content)
            visit["resultado"] = "ok"
        else:
            if "html" not in ctype:
                visit.update({"resultado": "tipo_invalido", "detalhe": ctype})
                self._record(item, visit)
                return
            soup = parse_html(res.content, res.encoding)
            if kind == "project":
                project = self._extract_project(soup, url)
                if project is None:
                    # 200, mas sem as marcas de uma página de projeto: descartada.
                    visit.update({"resultado": "soft404"})
                    self._record(item, visit)
                    logger.info("Descartada (soft-404): %s", url)
                    return
                canonical = normalize(project.get("url") or "")
                known = [(canonical, self.site)] if canonical else []
                digest = project.get("hash_conteudo")
                if self.storage.project_exists(self.site, project["chave"]) or (
                        digest and self.storage.hash_exists(self.site, digest)):
                    visit.update({"resultado": "duplicada", "detalhe": project["chave"]})
                    self._record(item, visit, known=known)
                    logger.info("Descartada (duplicada): %s", url)
                    return
                visit["resultado"] = "projeto"
            else:
                visit["resultado"] = "ok"
                if self.site == GITHUB:
                    hints = extract_github_cards(soup, url)
            found = extract_links(soup, url)

        # 3. salva o HTML bruto
        visit["bloco"], visit["posicao"], visit["tamanho"] = self.writer.write(res.content)

        # 4 e 5. links novos que passam no filtro
        links = self._make_links(item, found)
        if project:
            project.update({"site": self.site, "url_coletada": url,
                            "coletado_em": visit["coletado_em"],
                            "status_http": res.status})
        added = self._record(item, visit, project=project, hints=hints,
                                    links=links, known=known)
        if project:
            self.projects += 1
            logger.info("PROJETO %d/%d %s | +%d links novos",
                        self.projects, self.cfg.target_per_site, project["url"], added)
        else:
            logger.info("%s %s | %d links aceitos, %d novos",
                        kind, url, len(links), added)


class Crawler:
    def __init__(self, config: Optional[CrawlerConfig] = None):
        self.cfg = config or CrawlerConfig()
        self.storage = Storage(self.cfg.output_dir, self.cfg.db_filename)
        self.stop_event = threading.Event()
        self.workers: List[SiteWorker] = []

    def others_running(self, me: SiteWorker) -> bool:
        return any(w is not me and w.is_alive() and not w.done for w in self.workers)

    def seed(self) -> None:
        """Coloca as seeds na fila. Seeds já conhecidas (execução anterior) são ignoradas."""
        for site in self.cfg.sites:
            entries = []
            for url in seed_urls(site, self.cfg):
                kind = classify(url)
                if kind:
                    entries.append({"site": site, "url": url, "tipo": kind,
                                    "prioridade": PRIORITY_OTHER, "profundidade": 0,
                                    "origem": "seed"})
            added = self.storage.add_to_frontier(entries)
            logger.info("[%s] %d seeds novas na fila (%d ja conhecidas). Fila: %d URLs. Projetos: %d.",
                        site, added, len(entries) - added,
                        self.storage.frontier_count(site), self.storage.project_count(site))

    def run(self) -> None:
        self.seed()
        run_id = self.storage.start_run(now_iso())
        start = time.monotonic()
        logger.info("Inicio da coleta. Meta: %d paginas de projeto por site. "
                    "Profundidade maxima: %s. Espera minima: %.1fs.",
                    self.cfg.target_per_site,
                    self.cfg.max_depth if self.cfg.max_depth is not None else "sem limite",
                    self.cfg.min_delay)

        self.workers = [SiteWorker(self, site) for site in self.cfg.sites]
        for w in self.workers:
            w.start()
        last_save = time.monotonic()
        try:
            while any(w.is_alive() for w in self.workers):
                time.sleep(1)
                if time.monotonic() - last_save > 30:
                    self.storage.update_run(run_id, time.monotonic() - start)
                    last_save = time.monotonic()
        except KeyboardInterrupt:
            logger.warning("Interrupcao pedida. Terminando a pagina atual de cada site...")
            self.stop_event.set()
            for w in self.workers:
                w.join()
        finally:
            elapsed = time.monotonic() - start
            self.storage.update_run(run_id, elapsed, now_iso())
            logger.info("Coleta encerrada apos %.0f s.", elapsed)

    def export(self) -> str:
        path = os.path.join(self.cfg.output_dir, self.cfg.export_filename)
        n = self.storage.export_jsonl(path)
        logger.info("%d projetos exportados para %s", n, path)
        return path

    def close(self) -> None:
        self.storage.close()
