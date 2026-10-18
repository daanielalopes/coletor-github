"""
Busca ranqueada simples, usada nesta etapa só para validar o índice e medir
o tempo de consulta de cada configuração (seção 5 do relatório).

O modelo de recuperação definitivo, com a calibração dos pesos, os filtros
e a avaliação com julgamentos de relevância, é a etapa 3 (seção 7).

- granularidade "documento": BM25;
- granularidade "campo": BM25F (Robertson e Zaragoza, 2009): a frequência
  de cada campo é normalizada pelo comprimento do campo, ponderada pelo peso
  do campo e somada antes da saturação;
- granularidade "chunk": BM25 em cada unidade; a nota do projeto é a da sua
  melhor unidade (MaxP).
"""

import math
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from .indice import Indice

K1 = 1.2
B = 0.75
# Pesos provisórios dos campos no BM25F, a calibrar na etapa 3.
PESOS = {"nome": 3.0, "descricao": 2.0, "rotulos": 2.0, "readme": 1.0, "texto": 1.0}


class Buscador:
    def __init__(self, indice: Indice, k1: float = K1, b: float = B, pesos: Dict[str, float] = None):
        self.indice = indice
        self.k1 = k1
        self.b = b
        pesos = pesos or PESOS
        self.pesos = [pesos.get(c, 1.0) for c in indice.campos]
        nf = indice.nf
        n = max(1, indice.n_unidades)
        comps = indice.comprimentos
        self.medio = [max(1e-9, sum(comps[f::nf]) / n) for f in range(nf)]

    def idf(self, df: int) -> float:
        n = self.indice.n_unidades
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def buscar(self, consulta: str, k: int = 10) -> List[Tuple[int, float]]:
        """Devolve [(docid, nota)], do mais relevante para o menos."""
        idx = self.indice
        nf = idx.nf
        comps = idx.comprimentos
        notas: Dict[int, float] = defaultdict(float)
        for termo, qtf in Counter(idx.termos_da_consulta(consulta)).items():
            unidades, tfs = idx.postings(termo)
            if not unidades:
                continue
            idf = self.idf(len(unidades)) * qtf
            for u, linha in zip(unidades, tfs):
                base = u * nf
                tf = 0.0
                for f in range(nf):
                    if linha[f]:
                        norm = 1 - self.b + self.b * comps[base + f] / self.medio[f]
                        tf += self.pesos[f] * linha[f] / norm
                notas[u] += idf * tf / (self.k1 + tf)
        if idx.unidade_doc is not None:   # chunk: nota do projeto = melhor unidade
            por_doc: Dict[int, float] = {}
            for u, nota in notas.items():
                d = idx.unidade_doc[u]
                if nota > por_doc.get(d, 0.0):
                    por_doc[d] = nota
            notas = por_doc
        return sorted(notas.items(), key=lambda x: -x[1])[:k]
