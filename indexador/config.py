"""
Configuração central do indexador.

Todos os hiperparâmetros da representação ficam aqui, para facilitar a
leitura e os experimentos do relatório (seção 5).
"""

from dataclasses import asdict, dataclass, field
from typing import Tuple

# Campos textuais de cada documento (ver documentos.py). A ordem define o bit
# de cada campo na máscara gravada nas postings (granularidade "campo").
CAMPOS: Tuple[str, ...] = ("nome", "descricao", "rotulos", "readme")


@dataclass
class IndexConfig:
    # -------------------- Entrada e saída --------------------
    entrada: str = "data/projetos.jsonl"
    saida: str = "data/indice"

    # -------------------- Pré-processamento --------------------
    remover_stopwords: bool = True
    stemming: bool = True              # Snowball (Porter2) para inglês
    tamanho_min_token: int = 2         # exceto os da lista curta (c, r)
    tamanho_max_token: int = 25        # mais que isso é hash, base64, lixo
    max_digitos: int = 4               # números puros com mais dígitos saem

    # -------------------- Representação --------------------
    # Unidade indexada:
    #   "documento": um projeto = uma unidade, todos os campos juntos;
    #   "campo":     um projeto = uma unidade, com a frequência de cada
    #                campo separada na posting (permite BM25F na etapa 3);
    #   "chunk":     o README é cortado em janelas de `tamanho_chunk` tokens
    #                (com `sobreposicao`); o cabeçalho (nome, descrição,
    #                rótulos) é mais uma unidade. Cada unidade aponta para o
    #                seu projeto.
    granularidade: str = "campo"
    tamanho_chunk: int = 256
    sobreposicao: int = 0
    posicoes: bool = True              # guardar as posições (consulta por frase)

    # -------------------- Construção (SPIMI) --------------------
    documentos_por_bloco: int = 10000  # tamanho do bloco em memória
    particoes: int = 16                # buckets do índice final (hash do termo)
    processos: int = 0                 # 0 = número de núcleos da máquina
    lote_processos: int = 200          # documentos por tarefa enviada a um processo

    def campos(self) -> Tuple[str, ...]:
        """Campos gravados nas postings: 4 na granularidade "campo", 1 nas outras."""
        return CAMPOS if self.granularidade == "campo" else ("texto",)

    def to_dict(self) -> dict:
        return asdict(self)

    def validar(self) -> None:
        if self.granularidade not in ("documento", "campo", "chunk"):
            raise ValueError(f"granularidade inválida: {self.granularidade}")
        if self.granularidade == "chunk" and not 0 <= self.sobreposicao < self.tamanho_chunk:
            raise ValueError("a sobreposição deve ser menor que o tamanho do chunk")
        if self.particoes < 1 or self.documentos_por_bloco < 1:
            raise ValueError("partições e documentos por bloco devem ser >= 1")
