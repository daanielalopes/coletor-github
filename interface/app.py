#!/usr/bin/env python3
"""
Interface gráfica (web) do sistema de recuperação (Parte 3).

É um servidor HTTP escrito só com a biblioteca padrão do Python
(http.server), sem nenhum framework externo, para não acrescentar
dependências e rodar em qualquer máquina. A interface **consulta o mesmo
índice invertido** usado na linha de comando: carrega a classe `Indice`
(leitura do índice no disco) e o `Buscador` (ranqueamento BM25/BM25F) e não
tem nenhuma busca própria, simplificada ou paralela.

Para deixar isso visível ao usuário, cada resposta de busca inclui, além do
ranking, a entrada do léxico de cada termo da consulta (partição, df e cf) e
é possível abrir o detalhe de um termo com as primeiras postings lidas do
índice (o mesmo que `buscar.py --termo`).

Uso:
    python -m interface.app --indice data/indice --porta 8000
    # abra http://localhost:8000 no navegador
"""

import argparse
import html
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
# Página HTML (servida na raiz)
# ----------------------------------------------------------------------
def pagina() -> str:
    return PAGINA_HTML


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

    def do_GET(self) -> None:
        url = urlparse(self.path)
        rota = url.path
        params = parse_qs(url.query)
        try:
            if rota in ("/", "/index.html"):
                self._enviar(200, pagina().encode("utf-8"), "text/html; charset=utf-8")
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


PAGINA_HTML = """<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Busca de Projetos de Software Livre</title>
<style>
  :root { --azul:#2563eb; --cinza:#64748b; --borda:#e2e8f0; --fundo:#f8fafc; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         color:#0f172a; background:var(--fundo); }
  header { background:#fff; border-bottom:1px solid var(--borda); padding:20px 24px; }
  h1 { margin:0; font-size:20px; }
  .sub { color:var(--cinza); font-size:13px; margin-top:4px; }
  main { max-width:900px; margin:0 auto; padding:24px; }
  .barra { display:flex; gap:8px; margin-bottom:12px; }
  input[type=text] { flex:1; padding:12px 14px; font-size:16px; border:1px solid var(--borda);
                     border-radius:8px; }
  select, button { padding:12px 14px; font-size:15px; border:1px solid var(--borda);
                   border-radius:8px; background:#fff; cursor:pointer; }
  button.primario { background:var(--azul); color:#fff; border-color:var(--azul); }
  .exemplos { font-size:13px; color:var(--cinza); margin-bottom:16px; }
  .exemplos a { color:var(--azul); cursor:pointer; margin-right:10px; text-decoration:none; }
  .meta { font-size:13px; color:var(--cinza); margin:8px 0 16px; }
  .termos { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:16px; }
  .chip { font-size:12px; padding:4px 8px; border-radius:999px; border:1px solid var(--borda);
          background:#fff; cursor:pointer; }
  .chip.vazio { color:#b91c1c; border-color:#fecaca; background:#fef2f2; }
  .chip b { color:var(--azul); }
  .res { background:#fff; border:1px solid var(--borda); border-radius:10px; padding:14px 16px;
         margin-bottom:10px; }
  .res .titulo { font-size:16px; font-weight:600; }
  .res .titulo a { color:var(--azul); text-decoration:none; }
  .res .nota { float:right; font-size:13px; color:#fff; background:var(--azul);
               padding:2px 8px; border-radius:6px; }
  .res .linha2 { font-size:12px; color:var(--cinza); margin:4px 0; display:flex; gap:10px; flex-wrap:wrap; }
  .res .trecho { font-size:14px; color:#334155; }
  .tag { background:var(--fundo); border:1px solid var(--borda); border-radius:6px; padding:1px 6px; }
  .vazio-res { color:var(--cinza); padding:20px; text-align:center; }
  #detalhe { background:#0f172a; color:#e2e8f0; border-radius:10px; padding:14px 16px;
             margin-top:8px; font-family: ui-monospace, Menlo, monospace; font-size:12px;
             white-space:pre-wrap; display:none; }
  footer { max-width:900px; margin:0 auto; padding:16px 24px; color:var(--cinza); font-size:12px; }
</style>
</head>
<body>
<header>
  <h1>🔎 Busca de Projetos de Software Livre</h1>
  <div class="sub" id="infoCorpus">carregando o índice…</div>
</header>
<main>
  <form class="barra" id="form">
    <input type="text" id="q" placeholder="ex.: machine learning, python web framework, game engine c++" autofocus>
    <select id="k">
      <option value="5">5</option>
      <option value="10" selected>10</option>
      <option value="20">20</option>
    </select>
    <button class="primario" type="submit">Buscar</button>
  </form>
  <div class="exemplos">
    Exemplos:
    <a data-q="machine learning">machine learning</a>
    <a data-q="python web framework">python web framework</a>
    <a data-q="linux terminal">linux terminal</a>
    <a data-q="password manager">password manager</a>
    <a data-q="game engine c++">game engine c++</a>
  </div>
  <div class="meta" id="meta"></div>
  <div class="termos" id="termos"></div>
  <div id="detalhe"></div>
  <div id="resultados"></div>
</main>
<footer>
  A interface consulta o índice invertido no disco (classe <code>Indice</code>) e ranqueia com
  BM25/BM25F (classe <code>Buscador</code>) — a mesma busca da linha de comando.
  Clique num termo para ver a sua entrada no índice (partição, df, cf e postings).
</footer>
<script>
const $ = s => document.querySelector(s);
function esc(t){ return (t||"").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

async function info(){
  try {
    const r = await fetch('/api/info'); const d = await r.json();
    $('#infoCorpus').textContent =
      `${d.n_documentos} projetos · vocabulário ${d.vocabulario} termos · `
      + `${d.postings} postings · granularidade "${d.granularidade}" · `
      + `stemming ${d.stemming?'on':'off'} · ${d.particoes} partições`;
  } catch(e){ $('#infoCorpus').textContent = 'índice não carregado'; }
}

async function detalhe(termo){
  const box = $('#detalhe');
  box.style.display = 'block';
  box.textContent = 'lendo postings de "'+termo+'" no índice…';
  const r = await fetch('/api/termo?t=' + encodeURIComponent(termo));
  const d = await r.json();
  let txt = '';
  for (const t of d.termos){
    if (!t.no_indice){ txt += `termo "${t.termo}": não está no índice\\n`; continue; }
    txt += `termo "${t.termo}"  partição ${t.particao}  df=${t.df}  cf=${t.cf}\\n`;
    txt += `campos: [${t.campos.join(', ')}]\\n`;
    for (const p of t.postings){
      txt += `  unidade ${p.unidade}  tf=${JSON.stringify(p.tf)}  ${p.nome}  ${p.url}\\n`;
    }
    txt += '\\n';
  }
  box.textContent = txt.trim() || 'sem dados';
  box.scrollIntoView({behavior:'smooth', block:'nearest'});
}

async function buscar(q, k){
  $('#resultados').innerHTML = '<div class="vazio-res">buscando…</div>';
  $('#termos').innerHTML = ''; $('#meta').textContent = ''; $('#detalhe').style.display='none';
  const r = await fetch('/api/buscar?q=' + encodeURIComponent(q) + '&k=' + k);
  const d = await r.json();
  if (d.erro){ $('#resultados').innerHTML = '<div class="vazio-res">'+esc(d.erro)+'</div>'; return; }

  $('#meta').textContent = `${d.total} resultado(s) em ${d.ms} ms · termos analisados da consulta:`;
  $('#termos').innerHTML = d.lexico.map(l =>
    l.no_indice
      ? `<span class="chip" data-t="${esc(l.termo)}"><b>${esc(l.termo)}</b> · df ${l.df} · cf ${l.cf}</span>`
      : `<span class="chip vazio" title="não está no índice">${esc(l.termo)} · ausente</span>`
  ).join('');
  document.querySelectorAll('#termos .chip[data-t]').forEach(c =>
    c.onclick = () => detalhe(c.getAttribute('data-t')));

  if (!d.resultados.length){
    $('#resultados').innerHTML = '<div class="vazio-res">Nenhum projeto encontrado para essa consulta.</div>';
    return;
  }
  $('#resultados').innerHTML = d.resultados.map((x,i) => {
    const estrelas = (x.estrelas!==null && x.estrelas!==undefined && x.estrelas!=='') ? `⭐ ${esc(''+x.estrelas)}` : '';
    const linha2 = [
      `<span class="tag">${esc(x.site)}</span>`,
      x.linguagem ? `<span class="tag">${esc(x.linguagem)}</span>` : '',
      x.licenca ? `<span class="tag">${esc(x.licenca)}</span>` : '',
      estrelas
    ].filter(Boolean).join(' ');
    return `<div class="res">
      <span class="nota">${x.nota.toFixed(2)}</span>
      <div class="titulo">${i+1}. <a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.nome||x.url)}</a></div>
      <div class="linha2">${linha2}</div>
      <div class="trecho">${esc(x.trecho||'')}</div>
    </div>`;
  }).join('');
}

$('#form').addEventListener('submit', e => {
  e.preventDefault();
  const q = $('#q').value.trim(); if (!q) return;
  buscar(q, $('#k').value);
});
document.querySelectorAll('.exemplos a').forEach(a =>
  a.onclick = () => { $('#q').value = a.getAttribute('data-q'); buscar(a.getAttribute('data-q'), $('#k').value); });
info();

// Consulta pela URL (?q=...&k=...): permite compartilhar um link de busca.
const url0 = new URLSearchParams(location.search);
if (url0.get('q')) {
  $('#q').value = url0.get('q');
  if (url0.get('k')) $('#k').value = url0.get('k');
  buscar(url0.get('q'), $('#k').value);
}
</script>
</body>
</html>"""


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
