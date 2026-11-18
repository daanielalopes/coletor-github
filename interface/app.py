#!/usr/bin/env python3
"""
Interface gráfica (web) do sistema de recuperação (Parte 3).

É um servidor HTTP escrito só com a biblioteca padrão do Python
(http.server), sem nenhum framework externo, para não acrescentar
dependências e rodar em qualquer máquina. O frontend são arquivos estáticos
(HTML, CSS e JS) na pasta `interface/static/`, servidos pelo próprio servidor.
A interface **consulta o mesmo índice invertido** usado na linha de comando:
carrega a classe `Indice` (leitura do índice no disco) e o `Buscador`
(ranqueamento BM25/BM25F) e não tem nenhuma busca própria, simplificada ou
paralela.

Para deixar isso visível ao usuário, cada resposta de busca inclui, além do
ranking, a entrada do léxico de cada termo da consulta (partição, df e cf) e
é possível abrir o detalhe de um termo com as primeiras postings lidas do
índice (o mesmo que `buscar.py --termo`).

Uso:
    python -m interface.app --indice data/indice --porta 8000
    # abra http://localhost:8000 no navegador
"""

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from indexador.busca import Buscador
from indexador.indice import Indice

# Estado global (carregado uma vez na inicialização do servidor).
INDICE: Indice = None
BUSCADOR: Buscador = None

# Pasta dos arquivos estáticos do frontend (HTML, CSS, JS).
PASTA_ESTATICA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# Tipos MIME por extensão (só os usados pelo frontend).
TIPOS_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


# ----------------------------------------------------------------------
# Lógica de busca: usa exatamente o Indice + Buscador do sistema
# ----------------------------------------------------------------------
def termos_da_consulta(consulta: str):
    """Termos da consulta já analisados (mesma análise do indexador)."""
    return INDICE.termos_da_consulta(consulta)


def entradas_lexico(termos):
    """Para cada termo distinto, a entrada do índice invertido (prova de uso)."""
    saida = []
    vistos = set()
    for t in termos:
        if t in vistos:
            continue
        vistos.add(t)
        e = INDICE.entrada(t)
        if e is None:
            saida.append({"termo": t, "no_indice": False, "particao": INDICE.particao(t)})
        else:
            df, cf = e[0], e[1]
            saida.append({"termo": t, "no_indice": True, "particao": INDICE.particao(t),
                          "df": df, "cf": cf})
    return saida


def buscar(consulta: str, k: int):
    inicio = time.perf_counter()
    resultados = BUSCADOR.buscar(consulta, k)
    ms = (time.perf_counter() - inicio) * 1000
    termos = termos_da_consulta(consulta)
    itens = []
    for docid, nota in resultados:
        d = INDICE.documentos[docid]
        itens.append({
            "nota": round(nota, 3),
            "nome": d.get("nome", ""),
            "url": d.get("url", ""),
            "site": d.get("site", ""),
            "linguagem": d.get("linguagem", ""),
            "estrelas": d.get("estrelas"),
            "licenca": d.get("licenca", ""),
            "trecho": d.get("trecho", ""),
        })
    return {
        "consulta": consulta,
        "termos": termos,
        "lexico": entradas_lexico(termos),
        "ms": round(ms, 1),
        "total": len(itens),
        "resultados": itens,
    }


def detalhe_termo(termo: str, limite: int = 15):
    """Entrada do léxico e primeiras postings de um termo, lidas do índice."""
    termos = termos_da_consulta(termo) or [termo]
    saida = []
    for t in termos:
        e = INDICE.entrada(t)
        if e is None:
            saida.append({"termo": t, "no_indice": False})
            continue
        df, cf = e[0], e[1]
        unidades, tfs = INDICE.postings(t)
        posts = []
        for u, linha in list(zip(unidades, tfs))[:limite]:
            d = INDICE.documentos[INDICE.doc_da_unidade(u)]
            posts.append({"unidade": u, "tf": list(linha),
                          "nome": d.get("nome", ""), "url": d.get("url", "")})
        saida.append({"termo": t, "no_indice": True, "particao": INDICE.particao(t),
                      "df": df, "cf": cf, "campos": INDICE.campos, "postings": posts})
    return {"consulta": termo, "termos": saida}


def info():
    m = INDICE.meta
    return {
        "n_documentos": INDICE.n_documentos,
        "n_unidades": INDICE.n_unidades,
        "vocabulario": m.get("vocabulario"),
        "postings": m.get("postings"),
        "ocorrencias": m.get("ocorrencias"),
        "granularidade": INDICE.cfg.granularidade,
        "campos": INDICE.campos,
        "stemming": INDICE.cfg.stemming,
        "stopwords": INDICE.cfg.remover_stopwords,
        "particoes": INDICE.particoes,
    }


# ----------------------------------------------------------------------
# Arquivos estáticos do frontend (interface/static/)
# ----------------------------------------------------------------------
def caminho_estatico(nome: str):
    """Resolve o caminho de um arquivo dentro de PASTA_ESTATICA.

    Devolve None se o arquivo escapar da pasta (proteção contra path
    traversal como '../') ou se não existir.
    """
    nome = nome.lstrip("/")
    destino = os.path.normpath(os.path.join(PASTA_ESTATICA, nome))
    if os.path.commonpath([destino, PASTA_ESTATICA]) != PASTA_ESTATICA:
        return None
    if not os.path.isfile(destino):
        return None
    return destino


class Handler(BaseHTTPRequestHandler):
    def _enviar(self, codigo: int, corpo: bytes, tipo: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, dados: dict, codigo: int = 200) -> None:
        self._enviar(codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    def _arquivo_estatico(self, nome: str) -> bool:
        """Envia um arquivo estático. Devolve False se não existir."""
        caminho = caminho_estatico(nome)
        if caminho is None:
            return False
        ext = os.path.splitext(caminho)[1].lower()
        tipo = TIPOS_MIME.get(ext, "application/octet-stream")
        with open(caminho, "rb") as f:
            corpo = f.read()
        self._enviar(200, corpo, tipo)
        return True

    def do_GET(self) -> None:
        url = urlparse(self.path)
        rota = url.path
        params = parse_qs(url.query)
        try:
            if rota in ("/", "/index.html"):
                if not self._arquivo_estatico("index.html"):
                    self._enviar(500, b"index.html nao encontrado em interface/static/",
                                 "text/plain; charset=utf-8")
            elif rota.startswith("/static/"):
                if not self._arquivo_estatico(rota[len("/static/"):]):
                    self._enviar(404, b"nao encontrado", "text/plain; charset=utf-8")
            elif rota == "/api/info":
                self._json(info())
            elif rota == "/api/buscar":
                consulta = (params.get("q", [""])[0] or "").strip()
                try:
                    k = max(1, min(50, int(params.get("k", ["10"])[0])))
                except ValueError:
                    k = 10
                if not consulta:
                    self._json({"erro": "consulta vazia"}, 400)
                else:
                    self._json(buscar(consulta, k))
            elif rota == "/api/termo":
                termo = (params.get("t", [""])[0] or "").strip()
                if not termo:
                    self._json({"erro": "termo vazio"}, 400)
                else:
                    self._json(detalhe_termo(termo))
            else:
                self._enviar(404, b"nao encontrado", "text/plain; charset=utf-8")
        except BrokenPipeError:
            pass
        except Exception as exc:   # erro não previsto: devolve JSON em vez de 500 cru
            self._json({"erro": f"{type(exc).__name__}: {exc}"}, 500)

    def log_message(self, formato, *args) -> None:
        # log enxuto no stderr
        sys.stderr.write("%s - %s\n" % (self.address_string(), formato % args))


def main() -> int:
    p = argparse.ArgumentParser(description="Interface web de busca (Parte 3)")
    p.add_argument("--indice", default="data/indice", help="pasta do índice (padrão data/indice)")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()

    global INDICE, BUSCADOR
    if not os.path.isdir(args.indice):
        print(f"ERRO: índice não encontrado em '{args.indice}'.", file=sys.stderr)
        print("Construa o índice antes: python run_indexador.py", file=sys.stderr)
        return 1
    print(f"Carregando o índice de '{args.indice}'…", file=sys.stderr)
    INDICE = Indice(args.indice)
    BUSCADOR = Buscador(INDICE)
    print(f"Índice carregado: {INDICE.n_documentos} projetos, "
          f"vocabulário {INDICE.meta.get('vocabulario')} termos.", file=sys.stderr)

    servidor = ThreadingHTTPServer((args.host, args.porta), Handler)
    url = f"http://{args.host}:{args.porta}"
    print(f"\nInterface de busca em {url}  (Ctrl+C para parar)\n", file=sys.stderr)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando…", file=sys.stderr)
    finally:
        servidor.server_close()
        INDICE.fechar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
