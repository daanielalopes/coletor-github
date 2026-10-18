#!/usr/bin/env python3
"""
Ponto de entrada do indexador (Parte 2 do sistema de RI).

Lê data/projetos.jsonl (saída do coletor), pré-processa o texto e grava o
índice invertido em data/indice. Não usa banco de dados: o índice é um
conjunto de arquivos binários e de texto escritos pelo próprio programa.

Exemplos:
    # Índice completo com a configuração escolhida (campo, com posições)
    python run_indexador.py

    # Teste rápido com os 2.000 primeiros projetos
    python run_indexador.py --limite 2000 --saida data/indice_teste

    # Outras representações (seção 5 do relatório)
    python run_indexador.py --granularidade documento
    python run_indexador.py --granularidade chunk --tamanho-chunk 128 --sobreposicao 32
    python run_indexador.py --sem-posicoes --sem-stemming --sem-stopwords

    # Estatísticas de um índice já construído
    python run_indexador.py --stats
"""

import argparse
import json
import os
import sys
import time

from indexador.config import IndexConfig
from indexador.construtor import ConstrutorIndice, documentos_analisados, gravar_cache, ler_cache


def build_config(args) -> IndexConfig:
    cfg = IndexConfig()
    for nome in ("entrada", "saida", "granularidade", "tamanho_chunk", "sobreposicao",
                 "documentos_por_bloco", "particoes", "processos"):
        valor = getattr(args, nome)
        if valor is not None:
            setattr(cfg, nome, valor)
    if args.sem_posicoes:
        cfg.posicoes = False
    if args.sem_stopwords:
        cfg.remover_stopwords = False
    if args.sem_stemming:
        cfg.stemming = False
    return cfg


def mb(n: int) -> str:
    return f"{n / 2**20:9.1f} MB"


def relatorio(meta: dict) -> str:
    cfg = meta["config"]
    t = meta["tempos_s"]
    tam = meta["tamanhos_bytes"]
    linhas = [
        "=" * 64,
        "ESTATISTICAS DO INDICE",
        "=" * 64,
        f"Granularidade:                 {cfg['granularidade']}"
        + (f" ({cfg['tamanho_chunk']} termos, sobreposicao {cfg['sobreposicao']})"
           if cfg["granularidade"] == "chunk" else ""),
        f"Stopwords / stemming / posicoes: {cfg['remover_stopwords']} / {cfg['stemming']} / {cfg['posicoes']}",
        f"Documentos (projetos):         {meta['n_documentos']}",
        f"Unidades indexadas:            {meta['n_unidades']}",
        f"Vocabulario (termos):          {meta['vocabulario']}",
        f"Postings (pares termo-unidade): {meta['postings']}",
        f"Ocorrencias (tokens):          {meta['ocorrencias']}",
        f"Maior lista (df):              {meta['maior_df']}",
        "Termos por campo:              "
        + ", ".join(f"{c} {n}" for c, n in meta["termos_por_campo"].items()),
        "Comprimento medio da unidade:  "
        + ", ".join(f"{c} {v:.1f}" for c, v in meta["comprimento_medio"].items()),
        "",
        f"Blocos SPIMI:                  {meta['n_blocos']} de {cfg['documentos_por_bloco']} documentos",
        f"Tempo analise + blocos:        {t['analise_e_blocos']:.1f} s",
        f"Tempo da fusao:                {t['fusao']:.1f} s",
        f"Tempo total:                   {t['total']:.1f} s",
        f"Memoria de pico (principal):   {meta['memoria_pico_mb']:.0f} MB"
        f" (fim dos blocos {meta.get('memoria_blocos_mb', 0):.0f} MB, fim da fusao {meta.get('memoria_fusao_mb', 0):.0f} MB)",
        "",
        "--- tamanho em disco -------------------------------------------",
    ]
    for nome in ("postings", "posicoes", "lexico", "documentos", "comprimentos", "unidades"):
        if nome in tam:
            linhas.append(f"{nome + ':':31s}{mb(tam[nome])}")
    linhas += [
        f"{'Indice invertido (3 primeiros):':31s}{mb(meta['indice_invertido_bytes'])}"
        f"  em {cfg['particoes']} particao(oes)",
        f"{'Listas sem compressao:':31s}{mb(meta['listas_sem_compressao_bytes'])}",
        f"{'Total:':31s}{mb(sum(tam.values()))}",
        "=" * 64,
    ]
    return "\n".join(linhas)


def main() -> int:
    p = argparse.ArgumentParser(description="Indexador de projetos de software livre")
    p.add_argument("--entrada", help="JSONL do coletor (padrão data/projetos.jsonl)")
    p.add_argument("--saida", help="pasta do índice (padrão data/indice)")
    p.add_argument("--granularidade", choices=("documento", "campo", "chunk"))
    p.add_argument("--tamanho-chunk", dest="tamanho_chunk", type=int)
    p.add_argument("--sobreposicao", type=int)
    p.add_argument("--sem-posicoes", action="store_true")
    p.add_argument("--sem-stopwords", action="store_true")
    p.add_argument("--sem-stemming", action="store_true")
    p.add_argument("--documentos-por-bloco", dest="documentos_por_bloco", type=int)
    p.add_argument("--particoes", type=int, help="buckets do índice final")
    p.add_argument("--processos", type=int, help="processos (0 = todos os núcleos; 1 = sem paralelismo)")
    p.add_argument("--limite", type=int, default=0, help="indexar só os N primeiros projetos")
    p.add_argument("--gravar-cache", help="grava os documentos já analisados neste arquivo")
    p.add_argument("--usar-cache", help="lê os documentos já analisados deste arquivo")
    p.add_argument("--so-analise", action="store_true",
                   help="só analisa e grava o cache (mede o tempo do pré-processamento)")
    p.add_argument("--stats", action="store_true", help="só mostrar as estatísticas do índice")
    args = p.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    cfg = build_config(args)
    if args.stats:
        with open(os.path.join(cfg.saida, "meta.json"), encoding="utf-8") as f:
            print(relatorio(json.load(f)))
        return 0

    if args.usar_cache:
        docs = ler_cache(args.usar_cache, args.limite)
    else:
        docs = documentos_analisados(cfg, args.limite)
    if args.gravar_cache:
        docs = gravar_cache(args.gravar_cache, docs)

    if args.so_analise:
        inicio = time.perf_counter()
        n = sum(1 for _ in docs)
        print(json.dumps({"documentos": n, "tempo_s": round(time.perf_counter() - inicio, 2)}))
        return 0

    meta = ConstrutorIndice(cfg).construir(docs)
    print(relatorio(meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
