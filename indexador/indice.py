"""
Leitura do índice gravado pelo construtor.

O léxico de cada partição só é carregado quando uma consulta usa um termo
daquela partição. As postings e as posições são lidas do disco com seek, só
os bytes do termo pedido.
"""

import json
import os
import zlib
from array import array
from typing import Dict, List, Optional, Tuple

from . import vbyte
from .construtor import criar_analisador
from .config import IndexConfig

EntradaLexico = Tuple[int, int, int, int, int, int]   # df, cf, offset/bytes das postings, offset/bytes das posições


class Indice:
    def __init__(self, pasta: str, carregar_documentos: bool = True):
        self.pasta = pasta
        with open(os.path.join(pasta, "meta.json"), encoding="utf-8") as f:
            self.meta = json.load(f)
        self.cfg = IndexConfig(**self.meta["config"])
        self.campos: List[str] = self.meta["campos"]
        self.nf = len(self.campos)
        self.n_documentos: int = self.meta["n_documentos"]
        self.n_unidades: int = self.meta["n_unidades"]
        self.particoes = self.cfg.particoes
        self.analisador = criar_analisador(self.cfg)
        self._lexicos: Dict[int, Dict[str, EntradaLexico]] = {}
        self._arquivos: Dict[Tuple[str, int], object] = {}

        self.comprimentos = array("I")
        with open(os.path.join(pasta, "comprimentos.bin"), "rb") as f:
            self.comprimentos.frombytes(f.read())
        self.unidade_doc: Optional[array] = None
        if self.cfg.granularidade == "chunk":
            self.unidade_doc = array("I")
            with open(os.path.join(pasta, "unidades.bin"), "rb") as f:
                self.unidade_doc.frombytes(f.read())
        self.documentos: List[dict] = []
        if carregar_documentos:
            with open(os.path.join(pasta, "documentos.jsonl"), encoding="utf-8") as f:
                self.documentos = [json.loads(linha) for linha in f]

    def fechar(self) -> None:
        for f in self._arquivos.values():
            f.close()
        self._arquivos.clear()

    # ---------------------------- léxico ----------------------------
    def particao(self, termo: str) -> int:
        return zlib.crc32(termo.encode("utf-8")) % self.particoes

    def lexico(self, b: int) -> Dict[str, EntradaLexico]:
        lex = self._lexicos.get(b)
        if lex is None:
            lex = {}
            with open(os.path.join(self.pasta, f"lexico_{b:03d}.tsv"), encoding="utf-8") as f:
                for linha in f:
                    termo, *nums = linha.rstrip("\n").split("\t")
                    lex[termo] = tuple(map(int, nums))
            self._lexicos[b] = lex
        return lex

    def carregar_lexico_inteiro(self) -> int:
        for b in range(self.particoes):
            self.lexico(b)
        return sum(len(lex) for lex in self._lexicos.values())

    def entrada(self, termo: str) -> Optional[EntradaLexico]:
        return self.lexico(self.particao(termo)).get(termo)

    def _ler(self, prefixo: str, b: int, offset: int, n: int) -> bytes:
        f = self._arquivos.get((prefixo, b))
        if f is None:
            f = self._arquivos[(prefixo, b)] = open(os.path.join(self.pasta, f"{prefixo}_{b:03d}.bin"), "rb")
        f.seek(offset)
        return f.read(n)

    # ---------------------------- postings ----------------------------
    def postings(self, termo: str) -> Tuple[List[int], List[Tuple[int, ...]]]:
        """Devolve (unidades, frequências por campo) do termo, já analisado."""
        e = self.entrada(termo)
        if e is None:
            return [], []
        df, _, off, n, _, _ = e
        buf = self._ler("postings", self.particao(termo), off, n)
        unidades: List[int] = []
        tfs: List[Tuple[int, ...]] = []
        nf = self.nf
        dec = vbyte.decodificar
        pos = 0
        uid = 0
        for _ in range(df):
            gap, pos = dec(buf, pos)
            uid += gap
            unidades.append(uid)
            if nf == 1:
                tf, pos = dec(buf, pos)
                tfs.append((tf,))
            else:
                mascara = buf[pos]
                pos += 1
                linha = [0] * nf
                for f in range(nf):
                    if mascara & (1 << f):
                        linha[f], pos = dec(buf, pos)
                tfs.append(tuple(linha))
        return unidades, tfs

    def posicoes(self, termo: str) -> List[List[List[int]]]:
        """Para cada entrada das postings, as posições do termo em cada campo."""
        e = self.entrada(termo)
        if e is None or not self.cfg.posicoes:
            return []
        _, tfs = self.postings(termo)
        _, _, _, _, off, n = e
        numeros = vbyte.decodificar_tudo(self._ler("posicoes", self.particao(termo), off, n))
        resultado, i = [], 0
        for linha in tfs:
            porcampo = []
            for tf in linha:
                atual, lst = 0, []
                for gap in numeros[i:i + tf]:
                    atual += gap
                    lst.append(atual)
                porcampo.append(lst)
                i += tf
            resultado.append(porcampo)
        return resultado

    def comprimento(self, unidade: int, campo: int = 0) -> int:
        return self.comprimentos[unidade * self.nf + campo]

    def doc_da_unidade(self, unidade: int) -> int:
        return unidade if self.unidade_doc is None else self.unidade_doc[unidade]

    def termos_da_consulta(self, consulta: str) -> List[str]:
        return self.analisador.analisar(consulta)
