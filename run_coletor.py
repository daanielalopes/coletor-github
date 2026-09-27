#!/usr/bin/env python3
"""
Ponto de entrada do Coletor (Parte 1 do Sistema de RI).

Exemplos de uso:
    # Coleta padrão (meta de 50.000 filmes, definida em config.py)
    python run_coletor.py

    # Teste rápido: coletar só 100 filmes, 2 workers, delay maior
    python run_coletor.py --target 100 --workers 2 --delay 1.5

    # Retomar uma coleta interrompida (basta rodar de novo; o estado
    # é lido do banco automaticamente)
    python run_coletor.py

    # Ao final, exportar os documentos para JSONL (fase de Indexação)
    python run_coletor.py --export
"""

import argparse
import logging
import sys

from coletor.config import CrawlerConfig
from coletor.crawler import Crawler


def build_config(args) -> CrawlerConfig:
    cfg = CrawlerConfig()
    if args.target is not None:
        cfg.target_pages = args.target
    if args.workers is not None:
        cfg.num_workers = args.workers
    if args.delay is not None:
        cfg.request_delay = args.delay
    if args.output is not None:
        cfg.output_dir = args.output
    if args.respect_robots:
        cfg.respect_robots_txt = True
    if args.no_raw_html:
        cfg.save_raw_html = False
    return cfg


def setup_logging(cfg: CrawlerConfig) -> None:
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(cfg.log_file, encoding="utf-8"),
        ],
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Coletor Letterboxd (RI - Parte 1)")
    ap.add_argument("--target", type=int, help="Meta de páginas de filme")
    ap.add_argument("--workers", type=int, help="Nº de workers concorrentes")
    ap.add_argument("--delay", type=float, help="Delay base entre requisições (s)")
    ap.add_argument("--output", type=str, help="Diretório de saída")
    ap.add_argument("--respect-robots", action="store_true",
                    help="Respeitar o robots.txt (desligado por padrão pois o "
                         "Letterboxd restringe /films/ no robots)")
    ap.add_argument("--no-raw-html", action="store_true",
                    help="Não salvar o HTML bruto em disco")
    ap.add_argument("--export", action="store_true",
                    help="Ao final, exportar films.jsonl")
    ap.add_argument("--export-only", action="store_true",
                    help="Apenas exportar o JSONL do banco existente e sair")
    args = ap.parse_args()

    cfg = build_config(args)
    setup_logging(cfg)

    crawler = Crawler(cfg)
    try:
        if args.export_only:
            crawler.export()
            return
        crawler.run()
        if args.export:
            crawler.export()
    finally:
        crawler.close()


if __name__ == "__main__":
    main()
