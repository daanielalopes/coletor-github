#!/usr/bin/env python3
"""
Ponto de entrada do coletor (Parte 1 do sistema de RI).

Coletor web clássico: baixa o HTML das páginas do GitHub e do SourceForge e
segue os links. Não usa nenhuma API.

Exemplos:
    # Teste rápido: 100 páginas de projeto por site
    python run_coletor.py --target 100

    # Coleta completa: 25 mil páginas de projeto por site
    python run_coletor.py --target 25000

    # Retomar uma coleta interrompida: basta rodar o mesmo comando de novo

    # Só um dos sites, com profundidade máxima 3
    python run_coletor.py --target 1000 --sites github --max-depth 3

    # Estatísticas e exportação sem coletar
    python run_coletor.py --stats
    python run_coletor.py --export-only
"""

import argparse
import logging
import os
import sys

from coletor.config import CrawlerConfig
from coletor.crawler import Crawler
from coletor.stats import report


def build_config(args) -> CrawlerConfig:
    cfg = CrawlerConfig()
    if args.target is not None:
        cfg.target_per_site = args.target
    if args.max_depth is not None:
        cfg.max_depth = args.max_depth
    if args.delay is not None:
        cfg.min_delay = args.delay
    if args.output is not None:
        cfg.output_dir = args.output
    if args.sites:
        cfg.sites = tuple(args.sites)
    if args.block_size is not None:
        cfg.block_size = args.block_size
    if args.debug:
        cfg.log_level = "DEBUG"
    return cfg


def setup_logging(cfg: CrawlerConfig) -> None:
    # O console do Windows usa cp1252 por padrão; nomes de projetos podem ter
    # qualquer caractere.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    os.makedirs(cfg.output_dir, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(cfg.output_dir, cfg.log_filename),
                                encoding="utf-8"),
        ],
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Coletor web de projetos de software livre (GitHub e SourceForge)")
    ap.add_argument("--target", type=int,
                    help="paginas de projeto por site (padrao 25000)")
    ap.add_argument("--max-depth", type=int,
                    help="profundidade maxima a partir das seeds (padrao: sem limite)")
    ap.add_argument("--delay", type=float,
                    help="espera minima entre pedidos ao mesmo dominio, em segundos (padrao 1.0)")
    ap.add_argument("--sites", nargs="+", choices=["github", "sourceforge"],
                    help="sites a coletar (padrao: os dois)")
    ap.add_argument("--output", type=str, help="diretorio de saida (padrao data)")
    ap.add_argument("--block-size", type=int,
                    help="paginas por arquivo de bloco de HTML (padrao 1000)")
    ap.add_argument("--stats", action="store_true",
                    help="so mostrar as estatisticas da coleta e sair")
    ap.add_argument("--export-only", action="store_true",
                    help="so exportar data/projetos.jsonl e sair")
    ap.add_argument("--debug", action="store_true", help="log detalhado")
    args = ap.parse_args()

    cfg = build_config(args)
    if args.delay is not None and args.delay < 1.0:
        ap.error("--delay deve ser de pelo menos 1 segundo")
    setup_logging(cfg)

    crawler = Crawler(cfg)
    try:
        if args.stats:
            print(report(crawler.storage, cfg))
            return
        if args.export_only:
            crawler.export()
            return
        crawler.run()
        crawler.export()
        print(report(crawler.storage, cfg))
    finally:
        crawler.close()


if __name__ == "__main__":
    main()
