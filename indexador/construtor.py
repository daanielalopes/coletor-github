"""
Construção do índice invertido com o SPIMI (Single-Pass In-Memory Indexing).

Visão geral (seção 4 do relatório):

1. Análise em paralelo: processos auxiliares leem as linhas do JSONL e
   devolvem os termos de cada campo (analisador.py). O processo principal
   recebe os documentos na ordem do arquivo e só monta o índice. Há um
   limite de lotes pendentes, para a análise não encher a memória quando
   corre mais rápido que a indexação.

2. Blocos (SPIMI): o processo principal monta em memória um dicionário
   termo -> postings já comprimidas (bytearray), sem ordenar nada durante a
   leitura. A cada `documentos_por_bloco` documentos, os termos do bloco são
   ordenados e gravados num arquivo temporário (_blocos/bloco_0001.run), e
   a memória é liberada.

3. Fusão: os blocos são lidos em paralelo, em ordem alfabética de termo
   (fusão de k vias com heapq), e as postings de cada termo são concatenadas
   na ordem dos blocos, que é a ordem dos docids. Cada termo vai para uma
   das `particoes` (bucket = crc32(termo) mod particoes).

Arquivos do índice (pasta `saida`):

    postings_000.bin    para cada termo: unidades e frequências (VB + gaps)
    posicoes_000.bin    posições de cada ocorrência (VB + gaps), separadas
                        das postings para que a consulta sem frase não
                        precise ler nem decodificar as posições
    lexico_000.tsv      termo, df, cf e onde estão as listas do termo
    documentos.jsonl    metadados de cada projeto (url, site, linguagem...)
    comprimentos.bin    número de termos de cada unidade em cada campo
    unidades.bin        docid de cada unidade (só na granularidade chunk)
    meta.json           configuração, estatísticas, tempos e tamanhos

Formato de uma entrada da lista de postings de um termo:

    gap da unidade (VB) | máscara de campos (1 byte, só na granularidade
    "campo") | tf de cada campo presente (VB)

e na lista de posições, para cada entrada e cada campo presente, as tf
posições do termo naquele campo, como gaps (VB).
"""

import heapq
import json
import marshal
import os
import shutil
import struct
import time
import zlib
from array import array
from collections import deque
from itertools import groupby
from multiprocessing import Pool
from operator import itemgetter
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from . import vbyte
from .analisador import Analisador
from .config import CAMPOS, IndexConfig
from .documentos import campos_texto, ler_linhas, metadados, projeto

# Intervalo de posições entre um campo e o seguinte quando os campos são
# juntados numa unidade só (granularidade "documento" e cabeçalho do chunk),
# para que uma consulta por frase não case uma frase partida entre dois campos.
INTERVALO_CAMPOS = 100

CABECALHO_RUN = struct.Struct("<HIIIII")   # tamanho do termo, df, cf, última unidade, bytes das postings, bytes das posições

Documento = Tuple[dict, Dict[str, List[str]]]   # (metadados, termos de cada campo)


# ----------------------------------------------------------------------
# Análise dos documentos (em paralelo)
# ----------------------------------------------------------------------
_analisador: Optional[Analisador] = None


def criar_analisador(cfg: IndexConfig) -> Analisador:
    return Analisador(
        remover_stopwords=cfg.remover_stopwords, stemming=cfg.stemming,
        tamanho_min=cfg.tamanho_min_token, tamanho_max=cfg.tamanho_max_token,
        max_digitos=cfg.max_digitos,
    )


def _iniciar_processo(cfg_dict: dict) -> None:
    global _analisador
    _analisador = criar_analisador(IndexConfig(**cfg_dict))


def analisar_linha(analisador: Analisador, linha: str) -> Documento:
    proj = projeto(linha)
    campos = campos_texto(proj)
    return metadados(proj), {c: analisador.analisar(campos[c], c) for c in CAMPOS}


def _analisar_lote(linhas: List[str]) -> List[Documento]:
    return [analisar_linha(_analisador, linha) for linha in linhas]


def _lotes(linhas: Iterable[str], tamanho: int) -> Iterator[List[str]]:
    lote = []
    for linha in linhas:
        lote.append(linha)
        if len(lote) >= tamanho:
            yield lote
            lote = []
    if lote:
        yield lote


def documentos_analisados(cfg: IndexConfig, limite: int = 0) -> Iterator[Documento]:
    """Lê o JSONL e devolve (metadados, termos por campo) na ordem do arquivo."""
    linhas = ler_linhas(cfg.entrada, limite)
    processos = (cfg.processos or os.cpu_count() or 1) - 1   # um núcleo fica com a indexação
    if processos < 1:
        analisador = criar_analisador(cfg)
        for linha in linhas:
            yield analisar_linha(analisador, linha)
        return
    with Pool(processos, initializer=_iniciar_processo, initargs=(cfg.to_dict(),)) as pool:
        pendentes: deque = deque()
        for lote in _lotes(linhas, cfg.lote_processos):
            pendentes.append(pool.apply_async(_analisar_lote, (lote,)))
            if len(pendentes) >= 3 * processos:
                yield from pendentes.popleft().get()
        while pendentes:
            yield from pendentes.popleft().get()


def gravar_cache(caminho: str, docs: Iterable[Documento]) -> Iterator[Documento]:
    """Repassa os documentos e grava uma cópia já analisada (para os experimentos)."""
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    with open(caminho + ".tmp", "wb") as f:
        for doc in docs:
            marshal.dump(doc, f)
            yield doc
    os.replace(caminho + ".tmp", caminho)


def ler_cache(caminho: str, limite: int = 0) -> Iterator[Documento]:
    with open(caminho, "rb") as f:
        n = 0
        while not limite or n < limite:
            try:
                yield marshal.load(f)
            except EOFError:
                return
            n += 1


# ----------------------------------------------------------------------
# Granularidade: de um documento para as suas unidades
# ----------------------------------------------------------------------
Segmento = Tuple[int, List[str], int]   # (índice do campo, termos, posição inicial)


def unidades(cfg: IndexConfig, termos: Dict[str, List[str]]) -> List[List[Segmento]]:
    if cfg.granularidade == "campo":
        return [[(i, termos[c], 0) for i, c in enumerate(CAMPOS)]]

    def juntos(campos) -> List[Segmento]:
        segs, inicio = [], 0
        for c in campos:
            segs.append((0, termos[c], inicio))
            inicio += len(termos[c]) + INTERVALO_CAMPOS
        return segs

    if cfg.granularidade == "documento":
        return [juntos(CAMPOS)]

    # chunk: o cabeçalho é uma unidade e o README é cortado em janelas
    resultado = [juntos(("nome", "descricao", "rotulos"))]
    readme = termos["readme"]
    passo = cfg.tamanho_chunk - cfg.sobreposicao
    inicio = 0
    while inicio < len(readme):
        resultado.append([(0, readme[inicio:inicio + cfg.tamanho_chunk], inicio)])
        if inicio + cfg.tamanho_chunk >= len(readme):
            break
        inicio += passo
    return resultado


# ----------------------------------------------------------------------
# Construtor
# ----------------------------------------------------------------------
def memoria_pico_mb() -> float:
    try:
        import psutil
        info = psutil.Process().memory_info()
        pico = getattr(info, "peak_wset", None) or info.rss
        return pico / 2**20
    except ImportError:
        import resource   # Linux/Mac: ru_maxrss em KB (Linux) ou bytes (Mac)
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def memoria_atual_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 2**20
    except ImportError:
        return 0.0


class ConstrutorIndice:
    def __init__(self, cfg: IndexConfig):
        cfg.validar()
        self.cfg = cfg
        self.campos = cfg.campos()
        self.nf = len(self.campos)
        self.pasta = cfg.saida
        self.pasta_blocos = os.path.join(self.pasta, "_blocos")

        self.bloco: Dict[str, list] = {}   # termo -> [postings, posições, última unidade, df, cf]
        self.blocos: List[str] = []
        self.n_docs = 0
        self.n_unidades = 0
        self.n_tfs = 0                      # frequências gravadas (para o tamanho sem compressão)
        self.comprimentos = array("I")      # n_unidades x nf
        self.unidade_doc = array("I")
        self.tempos: Dict[str, float] = {}
        self.vocabulario_por_bloco: List[int] = []
        # Memória do processo no fim de cada bloco (o momento de maior uso
        # na fase de blocos) e no fim da fusão, medidas separadamente porque
        # o pico do processo inteiro mistura as duas fases.
        self.memoria_blocos_mb = 0.0
        self.memoria_fusao_mb = 0.0

    # ---------------------------- entrada ----------------------------
    def construir(self, docs: Iterable[Documento]) -> dict:
        if os.path.isdir(self.pasta):
            shutil.rmtree(self.pasta)
        os.makedirs(self.pasta_blocos)
        inicio = time.perf_counter()
        with open(os.path.join(self.pasta, "documentos.jsonl"), "w", encoding="utf-8") as fdoc:
            for meta, termos in docs:
                meta = dict(meta, id=self.n_docs)
                fdoc.write(json.dumps(meta, ensure_ascii=False) + "\n")
                for segs in unidades(self.cfg, termos):
                    self._adicionar_unidade(segs)
                self.n_docs += 1
                if self.n_docs % self.cfg.documentos_por_bloco == 0:
                    self._gravar_bloco()
        if self.bloco:
            self._gravar_bloco()
        self.tempos["analise_e_blocos"] = time.perf_counter() - inicio

        t = time.perf_counter()
        estat = self._fundir()
        self.tempos["fusao"] = time.perf_counter() - t
        self._gravar_tabelas()
        shutil.rmtree(self.pasta_blocos)
        self.tempos["total"] = time.perf_counter() - inicio
        return self._gravar_meta(estat)

    def _adicionar_unidade(self, segs: List[Segmento]) -> None:
        uid = self.n_unidades
        self.n_unidades += 1
        self.unidade_doc.append(self.n_docs)
        nf = self.nf
        comp = [0] * nf
        bloco = self.bloco
        cod = vbyte.codificar
        posicoes = self.cfg.posicoes

        # termo -> posições em cada campo
        ocorr: Dict[str, list] = {}
        if nf == 1:
            for _, termos, base in segs:
                comp[0] += len(termos)
                for p, t in enumerate(termos, base):
                    lst = ocorr.get(t)
                    if lst is None:
                        ocorr[t] = [p]
                    else:
                        lst.append(p)
        else:
            for f, termos, base in segs:
                comp[f] += len(termos)
                for p, t in enumerate(termos, base):
                    porcampo = ocorr.get(t)
                    if porcampo is None:
                        porcampo = ocorr[t] = [None] * nf
                    lst = porcampo[f]
                    if lst is None:
                        porcampo[f] = [p]
                    else:
                        lst.append(p)
        self.comprimentos.extend(comp)

        for t, valor in ocorr.items():
            e = bloco.get(t)
            if e is None:
                e = bloco[t] = [bytearray(), bytearray(), 0, 0, 0]
            out = e[0]
            out += cod(uid - e[2])
            e[2] = uid
            listas = [valor] if nf == 1 else valor
            if nf > 1:
                mascara = 0
                for f in range(nf):
                    if listas[f]:
                        mascara |= 1 << f
                out.append(mascara)
            tf_total = 0
            for lst in listas:
                if lst:
                    out += cod(len(lst))
                    tf_total += len(lst)
                    self.n_tfs += 1
                    if posicoes:
                        pb = e[1]
                        anterior = 0
                        for p in lst:
                            pb += cod(p - anterior)
                            anterior = p
            e[3] += 1
            e[4] += tf_total

    # ---------------------------- blocos ----------------------------
    def _gravar_bloco(self) -> None:
        self.memoria_blocos_mb = max(self.memoria_blocos_mb, memoria_atual_mb())
        caminho = os.path.join(self.pasta_blocos, f"bloco_{len(self.blocos) + 1:04d}.run")
        with open(caminho, "wb") as f:
            for termo in sorted(self.bloco):
                post, pos, ultima, df, cf = self.bloco[termo]
                tb = termo.encode("utf-8")
                f.write(CABECALHO_RUN.pack(len(tb), df, cf, ultima, len(post), len(pos)))
                f.write(tb)
                f.write(post)
                f.write(pos)
        self.vocabulario_por_bloco.append(len(self.bloco))
        self.blocos.append(caminho)
        self.bloco = {}

    @staticmethod
    def _ler_bloco(caminho: str) -> Iterator[tuple]:
        with open(caminho, "rb", buffering=1 << 20) as f:
            tam = CABECALHO_RUN.size
            while True:
                cab = f.read(tam)
                if not cab:
                    return
                nt, df, cf, ultima, npost, npos = CABECALHO_RUN.unpack(cab)
                termo = f.read(nt).decode("utf-8")
                yield termo, df, cf, ultima, f.read(npost), f.read(npos)

    # ---------------------------- fusão ----------------------------
    def _fundir(self) -> dict:
        P = self.cfg.particoes
        limite_buffer = max(1 << 16, (16 << 20) // P)   # ~16 MB em buffers no total
        buf_post = [bytearray() for _ in range(P)]
        buf_pos = [bytearray() for _ in range(P)]
        lexico: List[List[str]] = [[] for _ in range(P)]
        off_post = [0] * P
        off_pos = [0] * P
        nomes = [self._nome_particao(b) for b in range(P)]
        for b in range(P):   # cria os arquivos vazios
            for prefixo in ("postings", "posicoes"):
                open(os.path.join(self.pasta, f"{prefixo}_{nomes[b]}.bin"), "wb").close()

        def descarregar(b: int) -> None:
            for prefixo, buf in (("postings", buf_post[b]), ("posicoes", buf_pos[b])):
                if buf:
                    with open(os.path.join(self.pasta, f"{prefixo}_{nomes[b]}.bin"), "ab") as f:
                        f.write(buf)
                    buf.clear()

        vocabulario = postings = ocorrencias = maior_df = 0
        cod = vbyte.codificar
        leitores = [self._ler_bloco(c) for c in self.blocos]
        for termo, grupo in groupby(heapq.merge(*leitores, key=itemgetter(0)), key=itemgetter(0)):
            b = zlib.crc32(termo.encode("utf-8")) % P
            bp, bq = buf_post[b], buf_pos[b]
            ini_post, ini_pos = off_post[b] + len(bp), off_pos[b] + len(bq)
            df = cf = ultima = 0
            for _, d, c, u, post, pos in grupo:
                # A primeira unidade de cada bloco está gravada como número
                # absoluto; ao emendar os blocos, vira gap em relação à
                # última unidade do bloco anterior.
                primeira, k = vbyte.decodificar(post, 0)
                bp += cod(primeira - ultima)
                bp += memoryview(post)[k:]
                bq += pos
                df += d
                cf += c
                ultima = u
            n_post = off_post[b] + len(bp) - ini_post
            n_pos = off_pos[b] + len(bq) - ini_pos
            lexico[b].append(f"{termo}\t{df}\t{cf}\t{ini_post}\t{n_post}\t{ini_pos}\t{n_pos}\n")
            vocabulario += 1
            postings += df
            ocorrencias += cf
            maior_df = max(maior_df, df)
            if len(bp) + len(bq) > limite_buffer:
                off_post[b] += len(bp)
                off_pos[b] += len(bq)
                descarregar(b)
        self.memoria_fusao_mb = memoria_atual_mb()
        for b in range(P):
            descarregar(b)
            with open(os.path.join(self.pasta, f"lexico_{nomes[b]}.tsv"), "w", encoding="utf-8") as f:
                f.writelines(lexico[b])
        return {"vocabulario": vocabulario, "postings": postings,
                "ocorrencias": ocorrencias, "maior_df": maior_df}

    def _nome_particao(self, b: int) -> str:
        return f"{b:03d}"

    # ---------------------------- tabelas e meta ----------------------------
    def _gravar_tabelas(self) -> None:
        with open(os.path.join(self.pasta, "comprimentos.bin"), "wb") as f:
            self.comprimentos.tofile(f)
        if self.cfg.granularidade == "chunk":
            with open(os.path.join(self.pasta, "unidades.bin"), "wb") as f:
                self.unidade_doc.tofile(f)

    def _gravar_meta(self, estat: dict) -> dict:
        nf = self.nf
        totais = [sum(self.comprimentos[i::nf]) for i in range(nf)]
        tamanhos: Dict[str, int] = {}
        for nome in sorted(os.listdir(self.pasta)):
            grupo = nome.split("_")[0].split(".")[0]
            tamanhos[grupo] = tamanhos.get(grupo, 0) + os.path.getsize(os.path.join(self.pasta, nome))
        indice_invertido = sum(tamanhos.get(k, 0) for k in ("postings", "posicoes", "lexico"))
        # Tamanho das mesmas listas sem compressão: cada número em 4 bytes
        # (unidade, frequências, posições) e 1 byte por máscara.
        sem_compressao = 4 * (estat["postings"] + self.n_tfs) + (estat["postings"] if nf > 1 else 0)
        if self.cfg.posicoes:
            sem_compressao += 4 * estat["ocorrencias"]
        meta = {
            "config": self.cfg.to_dict(),
            "campos": list(self.campos),
            "n_documentos": self.n_docs,
            "n_unidades": self.n_unidades,
            "termos_por_campo": dict(zip(self.campos, totais)),
            "comprimento_medio": {c: totais[i] / max(1, self.n_unidades) for i, c in enumerate(self.campos)},
            **estat,
            "n_blocos": len(self.blocos),
            "vocabulario_por_bloco": self.vocabulario_por_bloco,
            "tempos_s": {k: round(v, 2) for k, v in self.tempos.items()},
            "memoria_pico_mb": round(memoria_pico_mb(), 1),
            "memoria_blocos_mb": round(self.memoria_blocos_mb, 1),
            "memoria_fusao_mb": round(self.memoria_fusao_mb, 1),
            "tamanhos_bytes": tamanhos,
            "indice_invertido_bytes": indice_invertido,
            "listas_sem_compressao_bytes": sem_compressao,
        }
        with open(os.path.join(self.pasta, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta
