#!/usr/bin/env python3
"""
Consulta ao índice pela linha de comando (validação da etapa 2).

Exemplos:
    python buscar.py "password manager linux"
    python buscar.py "biblioteca python para ler pdf" --k 5
    python buscar.py --termo python          # df, cf e o início da lista de postings
    python buscar.py --indice data/indice_teste "markdown editor"
"""

import argparse
import sys
import time

from indexador.busca import Buscador
from indexador.indice import Indice


def main() -> int:
    p = argparse.ArgumentParser(description="Busca no índice de projetos")
    p.add_argument("consulta", nargs="?", default="")
    p.add_argument("--indice", default="data/indice")
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--termo", help="mostrar a entrada do léxico e as postings de um termo")
    args = p.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    indice = Indice(args.indice)
    if args.termo:
        termos = indice.termos_da_consulta(args.termo) or [args.termo]
        for t in termos:
            e = indice.entrada(t)
            if e is None:
                print(f"{t}: não está no índice")
                continue
            df, cf, *_ = e
            unidades, tfs = indice.postings(t)
            print(f"termo '{t}' (partição {indice.particao(t)}): df={df} cf={cf}")
            print(f"  campos: {indice.campos}")
            for u, linha in list(zip(unidades, tfs))[:10]:
                doc = indice.documentos[indice.doc_da_unidade(u)]
                print(f"  unidade {u:7d}  tf={linha}  {doc['url']}")
        return 0

    inicio = time.perf_counter()
    resultados = Buscador(indice).buscar(args.consulta, args.k)
    ms = (time.perf_counter() - inicio) * 1000
    print(f"consulta: {args.consulta!r} -> termos {indice.termos_da_consulta(args.consulta)}  ({ms:.0f} ms)")
    for i, (docid, nota) in enumerate(resultados, 1):
        d = indice.documentos[docid]
        print(f"{i:2d}. {nota:6.2f}  [{d['site']:11s}] {d['nome']}  {d['url']}")
        if d.get("trecho"):
            print(f"              {d['trecho'][:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
