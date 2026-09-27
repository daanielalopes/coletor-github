#!/usr/bin/env python3
"""
Ponto de entrada do Coletor (Parte 1 do Sistema de RI).

Fonte de dados: API oficial do GitHub. Documento: repositórios.

Antes de rodar, defina o token da API do GitHub (grátis):
    - Linux/Mac:   export GITHUB_TOKEN=ghp_xxx
    - Windows PS:  $env:GITHUB_TOKEN="ghp_xxx"
    - ou crie um arquivo .env com a linha: GITHUB_TOKEN=ghp_xxx

Exemplos de uso:
    # Teste rápido: coletar 200 repositórios
    python run_coletor.py --target 200

    # Coleta completa (>50 mil) + exportar JSONL ao final
    python run_coletor.py --target 50000 --export

    # Retomar uma coleta interrompida (basta rodar de novo)
    python run_coletor.py --target 50000

    # Coleta mais rápida sem baixar READMEs (menos requisições)
    python run_coletor.py --target 50000 --no-readme

    # Só exportar o que já foi coletado
    python run_coletor.py --export-only
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
    if args.delay is not None:
        cfg.request_delay = args.delay
    if args.output is not None:
        cfg.output_dir = args.output
    if args.token is not None:
        cfg.token = args.token
    if args.no_readme:
        cfg.fetch_readme = False
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
    ap = argparse.ArgumentParser(description="Coletor GitHub (RI - Parte 1)")
    ap.add_argument("--target", type=int, help="Meta de repositórios a coletar")
    ap.add_argument("--delay", type=float,
                    help="Delay base entre requisições (s)")
    ap.add_argument("--output", type=str, help="Diretório de saída")
    ap.add_argument("--token", type=str,
                    help="Token da API do GitHub (prefira a env GITHUB_TOKEN)")
    ap.add_argument("--no-readme", action="store_true",
                    help="Não baixar READMEs (coleta mais rápida)")
    ap.add_argument("--star-max", type=int,
                    help="Estrelas máximas para o particionamento (padrão 5000)")
    ap.add_argument("--star-min", type=int,
                    help="Estrelas mínimas para o particionamento (padrão 1)")
    ap.add_argument("--export", action="store_true",
                    help="Ao final, exportar repositories.jsonl")
    ap.add_argument("--export-only", action="store_true",
                    help="Apenas exportar o JSONL do banco existente e sair")
    ap.add_argument("--debug", action="store_true",
                    help="Log detalhado")
    args = ap.parse_args()

    cfg = build_config(args)
    if args.debug:
        cfg.log_level = "DEBUG"
    setup_logging(cfg)

    if not cfg.token:
        logging.getLogger(__name__).warning(
            "Nenhum GITHUB_TOKEN definido: o limite de 60 req/h torna "
            "inviavel coletar 50 mil. Gere um token em "
            "https://github.com/settings/tokens e defina GITHUB_TOKEN."
        )

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
