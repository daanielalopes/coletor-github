#!/usr/bin/env python3
"""
Ponto de entrada do Coletor (Parte 1 do Sistema de RI).

Fontes de dados (duas): CRAWLER de HTML de github.com e de sourceforge.net.
Também há uma fonte por API do GitHub (opcional). Os dados são extraídos do
HTML das páginas (parsing do DOM) nos crawlers. Documento: repositório/projeto
(+ proprietário deduplicado).

Armazenamento: SOMENTE ARQUIVOS (JSONL). NÃO há banco de dados.

Exemplos de uso:
    # Teste rápido: 200 documentos das duas fontes de crawler (padrão)
    python run_coletor.py --target 200

    # Coleta completa (>50 mil), exportar ao final
    python run_coletor.py --target 50000 --export

    # Somente uma fonte
    python run_coletor.py --sources github_html
    python run_coletor.py --sources sourceforge

    # Incluir também o coletor por API do GitHub (precisa de GITHUB_TOKEN)
    python run_coletor.py --sources github_html sourceforge github_api

    # Retomar coleta interrompida: rode o mesmo comando de novo
    python run_coletor.py --target 50000
"""

import argparse
import logging
import sys

from coletor.config import CrawlerConfig
from coletor.crawler import Crawler
from coletor.sources import SOURCES


def build_config(args) -> CrawlerConfig:
    cfg = CrawlerConfig()
    if args.sources:
        cfg.sources = args.sources
    if args.target is not None:
        cfg.target_pages = args.target
    if args.delay is not None:
        cfg.request_delay = args.delay
    if args.output is not None:
        cfg.output_dir = args.output
    if args.no_readme:
        cfg.fetch_readme = False
    if args.no_robots:
        cfg.respect_robots = False
    if args.star_max is not None:
        cfg.star_max = args.star_max
    if args.star_min is not None:
        cfg.star_min = args.star_min
    return cfg


def setup_logging(cfg: CrawlerConfig) -> None:
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(cfg.log_file, encoding="utf-8"),
        ],
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Coletor de RI (Parte 1) - crawlers HTML (GitHub + SourceForge)")
    ap.add_argument("--sources", nargs="+", choices=sorted(SOURCES),
                    help="Fontes a coletar (padrao: github_html sourceforge)")
    ap.add_argument("--target", type=int, help="Meta de documentos a coletar")
    ap.add_argument("--delay", type=float, help="Delay base entre requisicoes (s)")
    ap.add_argument("--output", type=str, help="Diretorio de saida")
    ap.add_argument("--no-readme", action="store_true",
                    help="Nao extrair texto rico/README (coleta mais rapida)")
    ap.add_argument("--no-robots", action="store_true",
                    help="Nao consultar robots.txt (nao recomendado)")
    ap.add_argument("--star-max", type=int,
                    help="Estrelas maximas do particionamento GitHub (padrao 5000)")
    ap.add_argument("--star-min", type=int,
                    help="Estrelas minimas do particionamento GitHub (padrao 1)")
    ap.add_argument("--export", action="store_true",
                    help="Ao final, confirmar o caminho do JSONL do acervo")
    ap.add_argument("--export-only", action="store_true",
                    help="Apenas informar o caminho do acervo e sair")
    ap.add_argument("--debug", action="store_true", help="Log detalhado")
    args = ap.parse_args()

    cfg = build_config(args)
    if args.debug:
        cfg.log_level = "DEBUG"
    setup_logging(cfg)

    logging.getLogger(__name__).info(
        "Coletor iniciado. Fontes: %s. Armazenamento: arquivos JSONL (sem BD).",
        cfg.sources)

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
