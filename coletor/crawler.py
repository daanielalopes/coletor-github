"""
Crawler focado: orquestra fetcher + parser + storage.

Arquitetura:
  - Uma FRONTEIRA (frontier) de URLs pendentes, com duas classes:
      * 'list' -> páginas de listagem paginadas (seeds); produzem novos links.
      * 'film' -> páginas de filme; produzem documentos (metadados).
  - Um pool de workers (threads) consome a fronteira concorrentemente.
  - Deduplicação por URL canônica (conjunto 'visited', persistido em SQLite).
  - Checkpointing periódico: a coleta pode ser interrompida e RETOMADA.
  - Critério de parada: meta de páginas de filme OU fronteira vazia.

Observação de I/O-bound: como o gargalo é a rede, usamos threads (não
processos). O crawl-delay por thread garante polidez mesmo concorrente.
"""

import logging
import queue
import threading
from typing import Optional

from .config import CrawlerConfig
from .fetcher import Fetcher
from .parser import (
    extract_film_links,
    extract_next_list_page,
    parse_film,
)
from .storage import Storage

logger = logging.getLogger(__name__)


class Crawler:
    def __init__(self, config: Optional[CrawlerConfig] = None):
        self.cfg = config or CrawlerConfig()
        self.fetcher = Fetcher(self.cfg)
        self.storage = Storage(
            self.cfg.output_dir, self.cfg.db_filename, self.cfg.raw_html_dir
        )

        self._frontier: "queue.Queue" = queue.Queue()
        self._visited = set()
        self._visited_lock = threading.Lock()
        self._stop = threading.Event()
        self._films_saved = 0
        self._counter_lock = threading.Lock()
        self._processed_since_ckpt = 0

    # ---------------- Inicialização / retomada ----------------
    def _bootstrap(self) -> None:
        """Carrega estado anterior (retomada) ou semeia do zero."""
        self._visited = self.storage.load_visited()
        saved_frontier = self.storage.load_frontier()

        if saved_frontier:
            logger.info(
                "Retomando: %d URLs na fronteira, %d já visitadas, %d filmes.",
                len(saved_frontier), len(self._visited),
                self.storage.film_count(),
            )
            for url, url_type, depth in saved_frontier:
                self._frontier.put((url, url_type, depth))
        else:
            logger.info("Coleta nova: semeando %d seeds.", len(self.cfg.seeds))
            for seed in self.cfg.seeds:
                self._enqueue(seed, "list", 0)

        self._films_saved = self.storage.film_count()

    def _enqueue(self, url: str, url_type: str, depth: int) -> None:
        with self._visited_lock:
            if url in self._visited:
                return
            if self._frontier.qsize() >= self.cfg.max_frontier_size:
                return
            self._visited.add(url)  # marca cedo p/ evitar duplicidade na fila
        self._frontier.put((url, url_type, depth))
        self.storage.add_to_frontier([(url, url_type, depth)])
        self.storage.mark_visited(url)

    # ---------------- Critério de parada ----------------
    def _target_reached(self) -> bool:
        return self._films_saved >= self.cfg.target_pages

    # ---------------- Worker ----------------
    def _worker(self, wid: int) -> None:
        while not self._stop.is_set():
            try:
                url, url_type, depth = self._frontier.get(timeout=5)
            except queue.Empty:
                # Fronteira vazia: encerra este worker.
                return

            try:
                if self._target_reached():
                    self._stop.set()
                    return
                self._process(url, url_type, depth)
            except Exception as e:  # tolerância: um erro não derruba o worker
                logger.exception("Erro processando %s: %s", url, e)
                self.storage.record_failure(url, "exception", str(e))
            finally:
                self.storage.pop_frontier(url)
                self._frontier.task_done()
                self._maybe_checkpoint()

    def _process(self, url: str, url_type: str, depth: int) -> None:
        html = self.fetcher.get(url)
        if html is None:
            self.storage.record_failure(url, "fetch_failed", "sem HTML")
            return

        if url_type == "list":
            self._process_list(html, url, depth)
        else:
            self._process_film(html, url)

    def _process_list(self, html: str, url: str, depth: int) -> None:
        # 1) Extrai links de filme e adiciona à fronteira.
        film_links = extract_film_links(html, self.cfg.base_url)
        for fu in film_links:
            self._enqueue(fu, "film", depth + 1)

        # 2) Enfileira a próxima página da listagem (paginação).
        if depth + 1 < self.cfg.max_list_pages_per_seed:
            nxt = extract_next_list_page(html, url, self.cfg.base_url)
            if nxt:
                self._enqueue(nxt, "list", depth + 1)

        logger.info(
            "[LIST d=%d] %s -> +%d filmes (fila=%d, filmes=%d)",
            depth, url, len(film_links), self._frontier.qsize(),
            self._films_saved,
        )

    def _process_film(self, html: str, url: str) -> None:
        data = parse_film(html, url)
        if not data:
            self.storage.record_failure(url, "parse_failed", "sem metadados")
            return

        if self.cfg.save_raw_html:
            data["raw_html_path"] = self.storage.save_raw_html(url, html)

        self.storage.save_film(data)
        with self._counter_lock:
            self._films_saved += 1
            if self._films_saved % 50 == 0:
                logger.info("Progresso: %d filmes coletados.", self._films_saved)

    def _maybe_checkpoint(self) -> None:
        with self._counter_lock:
            self._processed_since_ckpt += 1
            do = self._processed_since_ckpt >= self.cfg.checkpoint_every
            if do:
                self._processed_since_ckpt = 0
        if do:
            self.storage.commit()

    # ---------------- Loop principal ----------------
    def run(self) -> None:
        self._bootstrap()
        logger.info(
            "Iniciando crawl com %d workers. Meta: %d páginas de filme.",
            self.cfg.num_workers, self.cfg.target_pages,
        )
        threads = []
        for i in range(self.cfg.num_workers):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            t.start()
            threads.append(t)

        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            logger.warning("Interrompido pelo usuário. Salvando checkpoint...")
            self._stop.set()
            for t in threads:
                t.join(timeout=10)

        self.storage.commit()
        logger.info(
            "Coleta finalizada. Total de filmes: %d. Fronteira restante: %d.",
            self.storage.film_count(), self.storage.frontier_size(),
        )

    def export(self) -> str:
        path = self.storage.export_jsonl()
        logger.info("Exportado JSONL para %s", path)
        return path

    def close(self) -> None:
        self.storage.close()
