#!/usr/bin/env python3
"""
Experimentos da etapa de indexação (seções 3 e 5 do relatório).

    python experimentos_indexacao.py preprocessamento   # efeito de cada etapa no vocabulário
    python experimentos_indexacao.py analise            # tempo da análise e caches por variante
    python experimentos_indexacao.py configuracoes      # constrói e mede cada representação
    python experimentos_indexacao.py zipf_heaps         # leis de Zipf e Heaps, termos mais comuns
    python experimentos_indexacao.py graficos           # gera os PNGs a partir dos JSONs
    python experimentos_indexacao.py tudo

Os resultados vão para evidencias/indexacao/. Os índices dos experimentos
são construídos em data/experimentos/ e apagados depois de medidos (use
--manter para guardá-los).

Para medir só a construção do índice, sem repetir a análise do texto a cada
configuração, a análise é feita uma vez por variante de pré-processamento
(com e sem stopwords, com e sem stemming) e gravada num cache; cada
configuração é construída a partir do cache num processo separado, para que
a memória de pico de uma não contamine a da outra.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from multiprocessing import Pool

from indexador.busca import Buscador
from indexador.config import CAMPOS, IndexConfig
from indexador.construtor import ler_cache, _lotes
from indexador.documentos import campos_texto, ler_linhas, projeto
from indexador.indice import Indice

RAIZ = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(RAIZ, "evidencias", "indexacao")
PASTA_EXP = os.path.join(RAIZ, "data", "experimentos")
PASTA_CACHE = os.path.join(PASTA_EXP, "cache")
INDICE_PRINCIPAL = os.path.join(RAIZ, "data", "indice")
PY = sys.executable

# Consultas usadas para medir o tempo de busca. São necessidades de
# informação típicas do sistema, em inglês e algumas em português.
CONSULTAS = [
    "password manager linux", "python library to read pdf", "markdown editor",
    "c++ game engine", "video editor", "ftp client windows", "backup tool",
    "machine learning framework", "web server written in rust", "music player",
    "image compression", "kubernetes monitoring dashboard", "chess engine",
    "javascript charting library", "screen recorder", "pdf to text converter",
    "emulator for nintendo games", "static site generator", "vpn server",
    "database migration tool", "speech recognition", "android file manager",
    "terminal emulator", "3d modeling software", "accounting software small business",
    "editor de video", "gerenciador de senhas", "biblioteca para graficos",
    "compilador", "jogo de xadrez",
]

VARIANTES = {   # nome do cache -> (remover_stopwords, stemming)
    "stop1_stem1": (True, True),
    "stop0_stem1": (False, True),
    "stop1_stem0": (True, False),
    "stop0_stem0": (False, False),
}

BASE = {"granularidade": "campo", "posicoes": True, "documentos_por_bloco": 10000,
        "particoes": 16, "cache": "stop1_stem1"}

CONFIGURACOES = [
    # (grupo, nome, alterações em relação à BASE)
    ("granularidade", "documento", {"granularidade": "documento"}),
    ("granularidade", "campo", {}),
    ("granularidade", "chunk_64", {"granularidade": "chunk", "tamanho_chunk": 64}),
    ("granularidade", "chunk_128", {"granularidade": "chunk", "tamanho_chunk": 128}),
    ("granularidade", "chunk_256", {"granularidade": "chunk", "tamanho_chunk": 256}),
    ("granularidade", "chunk_512", {"granularidade": "chunk", "tamanho_chunk": 512}),
    ("granularidade", "chunk_128_sobrep_32", {"granularidade": "chunk", "tamanho_chunk": 128, "sobreposicao": 32}),
    ("granularidade", "chunk_256_sobrep_64", {"granularidade": "chunk", "tamanho_chunk": 256, "sobreposicao": 64}),
    ("posicoes", "documento_sem_posicoes", {"granularidade": "documento", "posicoes": False}),
    ("posicoes", "campo_sem_posicoes", {"posicoes": False}),
    ("preprocessamento", "sem_stopwords", {"cache": "stop0_stem1"}),
    ("preprocessamento", "sem_stemming", {"cache": "stop1_stem0"}),
    ("preprocessamento", "sem_stopwords_sem_stemming", {"cache": "stop0_stem0"}),
    ("blocos", "bloco_2000", {"documentos_por_bloco": 2000}),
    ("blocos", "bloco_5000", {"documentos_por_bloco": 5000}),
    ("blocos", "bloco_20000", {"documentos_por_bloco": 20000}),
    ("blocos", "bloco_60000", {"documentos_por_bloco": 60000}),
    ("particoes", "particoes_1", {"particoes": 1}),
    ("particoes", "particoes_64", {"particoes": 64}),
    ("particoes", "particoes_256", {"particoes": 256}),
]


def salvar_json(nome: str, dados) -> None:
    os.makedirs(SAIDA, exist_ok=True)
    with open(os.path.join(SAIDA, nome), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def ler_json(nome: str):
    with open(os.path.join(SAIDA, nome), encoding="utf-8") as f:
        return json.load(f)


def caminho_cache(variante: str) -> str:
    return os.path.join(PASTA_CACHE, f"analise_{variante}.marshal")


# ----------------------------------------------------------------------
# 1. Efeito de cada etapa do pré-processamento
# ----------------------------------------------------------------------
ETAPAS = ("bruto", "tokens", "normalizados", "sem_stopwords", "stems")


def _etapas_lote(linhas):
    from indexador.analisador import Analisador
    a = Analisador()
    contagem = defaultdict(int)            # (site, etapa) -> tokens
    vocab = {e: set() for e in ETAPAS}
    vocab_site = {(s, e): set() for s in ("github", "sourceforge") for e in ETAPAS}
    for linha in linhas:
        proj = projeto(linha)
        site = proj["site"]
        for campo, texto in campos_texto(proj).items():
            for etapa, termos in a.etapas(texto, campo).items():
                contagem[(site, etapa)] += len(termos)
                vocab[etapa].update(termos)
                vocab_site[(site, etapa)].update(termos)
    return dict(contagem), vocab, vocab_site


def preprocessamento(args) -> None:
    inicio = time.perf_counter()
    contagem = defaultdict(int)
    vocab = {e: set() for e in ETAPAS}
    vocab_site = defaultdict(set)
    with Pool(os.cpu_count()) as pool:
        for c, v, vs in pool.imap_unordered(_etapas_lote, _lotes(ler_linhas(args.entrada), 1000)):
            for k, n in c.items():
                contagem[k] += n
            for e in ETAPAS:
                vocab[e] |= v[e]
            for k, s in vs.items():
                vocab_site[k] |= s
    linhas = []
    for e in ETAPAS:
        linhas.append({
            "etapa": e,
            "tokens": sum(n for (s, et), n in contagem.items() if et == e),
            "vocabulario": len(vocab[e]),
            "tokens_github": contagem[("github", e)],
            "tokens_sourceforge": contagem[("sourceforge", e)],
            "vocabulario_github": len(vocab_site[("github", e)]),
            "vocabulario_sourceforge": len(vocab_site[("sourceforge", e)]),
        })
    salvar_json("preprocessamento.json", {"etapas": linhas, "tempo_s": round(time.perf_counter() - inicio, 1)})
    for l in linhas:
        print(f"{l['etapa']:15s} tokens {l['tokens']:>11,}  vocabulário {l['vocabulario']:>10,}")


# ----------------------------------------------------------------------
# 2. Tempo da análise (e caches para as configurações)
# ----------------------------------------------------------------------
def rodar(cmd) -> str:
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"falhou: {' '.join(cmd)}\n{r.stderr}")
    return r.stdout


def analise(args) -> None:
    resultados = {}
    # Paralelismo: os 10.000 primeiros projetos com 1 processo e com todos.
    for processos in (1, 0):
        saida = rodar([PY, "run_indexador.py", "--so-analise", "--limite", "10000",
                       "--processos", str(processos)])
        resultados[f"10000_docs_processos_{processos or os.cpu_count()}"] = json.loads(saida.strip().splitlines()[-1])
        print(processos, resultados)
    for variante, (stop, stem) in VARIANTES.items():
        cmd = [PY, "run_indexador.py", "--so-analise", "--gravar-cache", caminho_cache(variante)]
        if not stop:
            cmd.append("--sem-stopwords")
        if not stem:
            cmd.append("--sem-stemming")
        r = json.loads(rodar(cmd).strip().splitlines()[-1])
        r["cache_bytes"] = os.path.getsize(caminho_cache(variante))
        resultados[variante] = r
        print(variante, r)
    resultados["nucleos"] = os.cpu_count()
    salvar_json("analise.json", resultados)


# ----------------------------------------------------------------------
# 3. Construção e medição de cada configuração
# ----------------------------------------------------------------------
def medir_consultas(pasta: str) -> dict:
    # Frio: um índice recém-aberto por consulta, sem léxico em memória.
    frio = []
    for q in CONSULTAS:
        idx = Indice(pasta, carregar_documentos=False)
        b = Buscador(idx)
        t = time.perf_counter()
        b.buscar(q)
        frio.append(time.perf_counter() - t)
        idx.fechar()
    # Quente: o mesmo índice para todas as consultas, depois de uma rodada.
    idx = Indice(pasta)
    b = Buscador(idx)
    for q in CONSULTAS:
        b.buscar(q)
    quente, top10, sf = [], {}, 0
    for q in CONSULTAS:
        t = time.perf_counter()
        r = b.buscar(q, 10)
        quente.append(time.perf_counter() - t)
        top10[q] = [d for d, _ in r]
        sf += sum(1 for d, _ in r if idx.documentos[d]["site"] == "sourceforge")
    idx.fechar()

    # Carga do léxico inteiro: tempo e memória
    import psutil
    proc = psutil.Process()
    idx = Indice(pasta, carregar_documentos=False)
    antes = proc.memory_info().rss
    t = time.perf_counter()
    idx.carregar_lexico_inteiro()
    carga = time.perf_counter() - t
    mem = (proc.memory_info().rss - antes) / 2**20
    idx.fechar()
    return {
        "consulta_fria_ms": round(1000 * sum(frio) / len(frio), 1),
        "consulta_quente_ms": round(1000 * sum(quente) / len(quente), 1),
        "carga_lexico_s": round(carga, 2),
        "memoria_lexico_mb": round(mem, 1),
        "sourceforge_no_top10_pct": round(100 * sf / (10 * len(CONSULTAS)), 1),
        "top10": top10,
    }


def configuracoes(args) -> None:
    arquivo = os.path.join(SAIDA, "configuracoes.json")
    resultados = ler_json("configuracoes.json") if os.path.exists(arquivo) and not args.refazer else {}
    for grupo, nome, alteracoes in CONFIGURACOES:
        if args.so and nome not in args.so:
            continue
        if nome in resultados and not args.refazer:
            continue
        cfg = dict(BASE, **alteracoes)
        pasta = os.path.join(PASTA_EXP, nome)
        cmd = [PY, "run_indexador.py", "--usar-cache", caminho_cache(cfg["cache"]), "--saida", pasta,
               "--granularidade", cfg["granularidade"],
               "--documentos-por-bloco", str(cfg["documentos_por_bloco"]),
               "--particoes", str(cfg["particoes"])]
        if cfg["granularidade"] == "chunk":
            cmd += ["--tamanho-chunk", str(cfg["tamanho_chunk"]), "--sobreposicao", str(cfg.get("sobreposicao", 0))]
        if not cfg["posicoes"]:
            cmd.append("--sem-posicoes")
        stop, stem = VARIANTES[cfg["cache"]]
        if not stop:
            cmd.append("--sem-stopwords")
        if not stem:
            cmd.append("--sem-stemming")
        print(f"[{grupo}] {nome} ...", flush=True)
        rodar(cmd)
        with open(os.path.join(pasta, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        consultas = medir_consultas(pasta)
        resultados[nome] = {"grupo": grupo, "alteracoes": alteracoes, "meta": meta, "consultas": consultas,
                            "n_arquivos": len(os.listdir(pasta))}
        print(f"    {meta['tempos_s']['total']} s, {meta['indice_invertido_bytes'] / 2**20:.1f} MB, "
              f"pico {meta['memoria_pico_mb']} MB, consulta {consultas['consulta_quente_ms']} ms", flush=True)
        salvar_json("configuracoes.json", resultados)
        if not args.manter:
            shutil.rmtree(pasta)

    # Sobreposição do top-10 de cada configuração com o da configuração base
    base = resultados.get("campo", {}).get("consultas", {}).get("top10")
    if base:
        for r in resultados.values():
            top = r["consultas"]["top10"]
            comum = [len(set(top[q]) & set(base[q])) / 10 for q in base if q in top]
            r["consultas"]["top10_em_comum_com_campo_pct"] = round(100 * sum(comum) / len(comum), 1)
        salvar_json("configuracoes.json", resultados)
    tabela_configuracoes(resultados)


def tabela_configuracoes(resultados: dict) -> None:
    colunas = ["grupo", "configuracao", "unidades", "vocabulario", "postings", "postings_mb", "posicoes_mb",
               "lexico_mb", "indice_mb", "sem_compressao_mb", "tempo_total_s", "tempo_fusao_s", "blocos",
               "memoria_pico_mb", "memoria_blocos_mb", "memoria_fusao_mb", "arquivos", "carga_lexico_s", "memoria_lexico_mb", "consulta_fria_ms",
               "consulta_quente_ms", "sourceforge_top10_pct", "top10_em_comum_pct"]
    with open(os.path.join(SAIDA, "configuracoes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(colunas)
        for nome, r in resultados.items():
            m, c, tam = r["meta"], r["consultas"], r["meta"]["tamanhos_bytes"]
            w.writerow([r["grupo"], nome, m["n_unidades"], m["vocabulario"], m["postings"],
                        round(tam.get("postings", 0) / 2**20, 1), round(tam.get("posicoes", 0) / 2**20, 1),
                        round(tam.get("lexico", 0) / 2**20, 1), round(m["indice_invertido_bytes"] / 2**20, 1),
                        round(m["listas_sem_compressao_bytes"] / 2**20, 1), m["tempos_s"]["total"],
                        m["tempos_s"]["fusao"], m["n_blocos"], m["memoria_pico_mb"], m.get("memoria_blocos_mb"),
                        m.get("memoria_fusao_mb"), r["n_arquivos"],
                        c["carga_lexico_s"], c["memoria_lexico_mb"], c["consulta_fria_ms"],
                        c["consulta_quente_ms"], c["sourceforge_no_top10_pct"],
                        c.get("top10_em_comum_com_campo_pct", "")])


# ----------------------------------------------------------------------
# 4. Zipf e Heaps
# ----------------------------------------------------------------------
def zipf_heaps(args) -> None:
    import numpy as np
    idx = Indice(INDICE_PRINCIPAL, carregar_documentos=False)
    idx.carregar_lexico_inteiro()
    entradas = [(t, e[0], e[1]) for lex in idx._lexicos.values() for t, e in lex.items()]
    cfs = np.array(sorted((cf for _, _, cf in entradas), reverse=True), dtype=float)
    ranks = np.arange(1, len(cfs) + 1)
    sel = (ranks >= 10) & (ranks <= 10000)
    inclinacao, intercepto = np.polyfit(np.log10(ranks[sel]), np.log10(cfs[sel]), 1)
    df_um = sum(1 for _, df, _ in entradas if df == 1)
    por_df = sorted(entradas, key=lambda x: -x[1])[:40]

    # Heaps: crescimento do vocabulário com o número de tokens, na ordem da coleção
    curvas = {}
    for variante in ("stop1_stem1", "stop0_stem0"):
        vistos, total, pontos, proximo = set(), 0, [], 100_000
        for _, termos in ler_cache(caminho_cache(variante)):
            for c in CAMPOS:
                lst = termos[c]
                vistos.update(lst)
                total += len(lst)
            if total >= proximo:
                pontos.append((total, len(vistos)))
                proximo = int(proximo * 1.15)
        pontos.append((total, len(vistos)))
        t = np.array([p[0] for p in pontos], dtype=float)
        v = np.array([p[1] for p in pontos], dtype=float)
        beta, logk = np.polyfit(np.log10(t), np.log10(v), 1)
        curvas[variante] = {"pontos": pontos, "beta": round(float(beta), 3), "k": round(float(10 ** logk), 1)}

    salvar_json("zipf_heaps.json", {
        "vocabulario": len(entradas),
        "termos_com_df_1": df_um,
        "termos_com_df_1_pct": round(100 * df_um / len(entradas), 1),
        "zipf_inclinacao": round(float(inclinacao), 3),
        "zipf_intercepto": round(float(intercepto), 3),
        "cf_por_rank": [[int(r), int(c)] for r, c in zip(ranks, cfs) if r <= 20 or r in (50, 100, 500, 1000, 5000, 10000, 50000, 100000, 500000) or r == len(cfs)],
        "mais_frequentes_df": [{"termo": t, "df": df, "cf": cf, "df_pct": round(100 * df / idx.n_documentos, 1)} for t, df, cf in por_df],
        "heaps": curvas,
    })
    print(f"Zipf: inclinação {inclinacao:.3f}; df=1: {100 * df_um / len(entradas):.1f}% do vocabulário")
    for v, c in curvas.items():
        print(f"Heaps {v}: V = {c['k']} * T^{c['beta']}")
    # pontos para o gráfico de Zipf (amostra log-espaçada)
    amostra = np.unique(np.logspace(0, np.log10(len(cfs)), 400).astype(int))
    salvar_json("zipf_pontos.json", [[int(r), int(cfs[r - 1])] for r in amostra])


# ----------------------------------------------------------------------
# 5. Gráficos
# ----------------------------------------------------------------------
COR1, COR2 = "#2a78d6", "#eb6834"         # azul e laranja da paleta de referência
TINTA, TINTA2, GRADE, FUNDO = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def _eixos(ax, titulo, x, y):
    ax.set_title(titulo, loc="left", color=TINTA, fontsize=11, fontweight="bold")
    ax.set_xlabel(x, color=TINTA2)
    ax.set_ylabel(y, color=TINTA2)
    ax.tick_params(colors=TINTA2, labelsize=9)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(GRADE)
    ax.grid(True, color=GRADE, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_facecolor(FUNDO)


def graficos(args) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": FUNDO})

    def salvar(fig, nome):
        fig.tight_layout()
        fig.savefig(os.path.join(SAIDA, nome), dpi=150)
        plt.close(fig)

    # Zipf
    pontos = ler_json("zipf_pontos.json")
    zh = ler_json("zipf_heaps.json")
    fig, ax = plt.subplots(figsize=(6.4, 4))
    ax.loglog([p[0] for p in pontos], [p[1] for p in pontos], color=COR1, linewidth=2)
    _eixos(ax, f"Lei de Zipf (inclinação {zh['zipf_inclinacao']})", "posição do termo (rank)", "frequência na coleção (cf)")
    salvar(fig, "zipf.png")

    # Heaps
    fig, ax = plt.subplots(figsize=(6.4, 4))
    rotulos = {"stop1_stem1": "com stopwords removidas e stemming", "stop0_stem0": "sem remoção e sem stemming"}
    for (variante, c), cor in zip(zh["heaps"].items(), (COR1, COR2)):
        t = [p[0] / 1e6 for p in c["pontos"]]
        v = [p[1] / 1e3 for p in c["pontos"]]
        ax.plot(t, v, color=cor, linewidth=2, label=f"{rotulos[variante]} (β = {c['beta']})")
        ax.annotate(f"{v[-1]:,.0f} mil", (t[-1], v[-1]), textcoords="offset points", xytext=(-4, 6),
                    ha="right", color=TINTA, fontsize=9)
    _eixos(ax, "Lei de Heaps: crescimento do vocabulário", "tokens lidos (milhões)", "termos distintos (mil)")
    ax.legend(frameon=False, fontsize=9, labelcolor=TINTA)
    salvar(fig, "heaps.png")

    # Pré-processamento: vocabulário em cada etapa
    pp = ler_json("preprocessamento.json")["etapas"]
    nomes = {"bruto": "texto bruto\n(espaços)", "tokens": "limpeza +\ntokenização", "normalizados": "minúsculas,\nacentos, filtros",
             "sem_stopwords": "sem\nstopwords", "stems": "stemming"}
    fig, ax = plt.subplots(figsize=(6.4, 4))
    xs = range(len(pp))
    vals = [l["vocabulario"] / 1e6 for l in pp]
    ax.bar(xs, vals, color=COR1, width=0.6)
    for x, v in zip(xs, vals):
        ax.annotate(f"{v:.2f} mi", (x, v), textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9, color=TINTA)
    ax.set_xticks(list(xs), [nomes[l["etapa"]] for l in pp])
    _eixos(ax, "Tamanho do vocabulário após cada etapa", "", "termos distintos (milhões)")
    ax.grid(axis="x", visible=False)
    salvar(fig, "preprocessamento_vocabulario.png")

    # Granularidade: tamanho do índice e tempo de consulta
    cfg = ler_json("configuracoes.json")
    gran = [(n, r) for n, r in cfg.items() if r["grupo"] == "granularidade"]
    rot = [n.replace("chunk_", "chunk ").replace("_sobrep_", "\nsobrep. ") for n, _ in gran]
    for nome_arq, titulo, eixo, valor in (
        ("granularidade_tamanho.png", "Tamanho do índice invertido por granularidade", "MB (postings + posições + léxico)",
         lambda r: r["meta"]["indice_invertido_bytes"] / 2**20),
        ("granularidade_consulta.png", "Tempo médio de consulta (índice já aberto)", "milissegundos",
         lambda r: r["consultas"]["consulta_quente_ms"]),
        ("granularidade_unidades.png", "Unidades indexadas por granularidade", "unidades (mil)",
         lambda r: r["meta"]["n_unidades"] / 1e3),
    ):
        fig, ax = plt.subplots(figsize=(7.2, 4))
        vals = [valor(r) for _, r in gran]
        ax.bar(range(len(vals)), vals, color=COR1, width=0.6)
        for x, v in enumerate(vals):
            ax.annotate(f"{v:,.0f}", (x, v), textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9, color=TINTA)
        ax.set_xticks(range(len(vals)), rot, fontsize=8)
        _eixos(ax, titulo, "", eixo)
        ax.grid(axis="x", visible=False)
        salvar(fig, nome_arq)

    # Blocos SPIMI: memória no fim da fase de blocos e pico do processo (mesma unidade, um eixo)
    blocos = sorted([(r["meta"]["config"]["documentos_por_bloco"], r) for r in cfg.values()
                     if r["grupo"] == "blocos" or r["alteracoes"] == {}], key=lambda x: x[0])
    fig, ax = plt.subplots(figsize=(6.4, 4))
    xs = [min(b, 52000) / 1e3 for b, _ in blocos]
    ys_bloco = [r["meta"]["memoria_blocos_mb"] for _, r in blocos]
    ys_pico = [r["meta"]["memoria_pico_mb"] for _, r in blocos]
    ax.plot(xs, ys_pico, color=COR2, linewidth=2, marker="o", markersize=7, label="pico do processo (blocos + fusão)")
    ax.plot(xs, ys_bloco, color=COR1, linewidth=2, marker="o", markersize=7, label="fim da fase de blocos")
    for x, y, (_, r) in zip(xs, ys_bloco, blocos):
        ax.annotate(f"{r['meta']['n_blocos']} bloco(s)", (x, y), textcoords="offset points",
                    xytext=(0, -16), ha="center", fontsize=8, color=TINTA2)
    ax.set_ylim(0, max(ys_pico) * 1.2)
    _eixos(ax, "SPIMI: memória x tamanho do bloco", "documentos por bloco (mil)", "memória do processo (MB)")
    ax.legend(frameon=False, fontsize=9, labelcolor=TINTA, loc="lower right")
    salvar(fig, "blocos_memoria.png")
    print("gráficos gravados em", SAIDA)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    p = argparse.ArgumentParser()
    p.add_argument("etapa", choices=("preprocessamento", "analise", "configuracoes", "zipf_heaps", "graficos", "tudo"))
    p.add_argument("--entrada", default=IndexConfig().entrada)
    p.add_argument("--manter", action="store_true", help="não apagar os índices dos experimentos")
    p.add_argument("--refazer", action="store_true", help="refazer configurações já medidas")
    p.add_argument("--so", nargs="*", help="só estas configurações")
    args = p.parse_args()
    os.makedirs(SAIDA, exist_ok=True)
    etapas = ("preprocessamento", "analise", "configuracoes", "zipf_heaps", "graficos") if args.etapa == "tudo" else (args.etapa,)
    for e in etapas:
        print(f"===== {e} =====", flush=True)
        globals()[e](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
