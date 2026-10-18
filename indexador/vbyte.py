"""
Compressão Variable Byte (VB), como no capítulo 5 do livro do Manning.

Cada número é gravado em blocos de 7 bits, do mais significativo para o
menos significativo. O bit mais alto vale 1 só no último byte do número,
marcando onde ele termina. Números menores que 128 ocupam 1 byte, menores
que 16.384 ocupam 2 bytes, e assim por diante.

Nas postings gravamos as diferenças (gaps) entre docids consecutivos, e não
os docids: as diferenças são pequenas, principalmente nos termos frequentes,
e cabem em 1 ou 2 bytes. O mesmo vale para as posições dentro do documento.
"""

from typing import List, Tuple

# Os números pequenos são a imensa maioria (gaps, frequências, posições):
# a codificação deles é calculada uma vez só.
_TABELA_LIMITE = 1 << 14
_TABELA: List[bytes] = []


def _codificar_lento(n: int) -> bytes:
    if n < 0:
        raise ValueError(f"VB só codifica números >= 0: {n}")
    partes = [n & 127]
    n >>= 7
    while n:
        partes.append(n & 127)
        n >>= 7
    partes.reverse()
    partes[-1] |= 128
    return bytes(partes)


_TABELA = [_codificar_lento(n) for n in range(_TABELA_LIMITE)]


def codificar(n: int) -> bytes:
    if 0 <= n < _TABELA_LIMITE:
        return _TABELA[n]
    return _codificar_lento(n)


def codificar_lista(numeros) -> bytes:
    return b"".join(codificar(n) for n in numeros)


def decodificar(buf, pos: int = 0) -> Tuple[int, int]:
    """Lê um número a partir de `pos`. Devolve (número, posição seguinte)."""
    n = 0
    while True:
        b = buf[pos]
        pos += 1
        if b & 128:
            return (n << 7) | (b & 127), pos
        n = (n << 7) | b


def decodificar_tudo(buf) -> List[int]:
    numeros = []
    n = 0
    for b in buf:
        if b & 128:
            numeros.append((n << 7) | (b & 127))
            n = 0
        else:
            n = (n << 7) | b
    return numeros
