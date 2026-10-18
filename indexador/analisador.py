"""
Análise léxica, remoção de stopwords e stemming.

Etapas, na ordem (a mesma do relatório, seção 3):

1. limpeza (limpeza.py);
2. termos técnicos com símbolos: c++ -> cpp, c# -> csharp, f# -> fsharp,
   .net -> dotnet, asp.net -> aspnet, objective-c -> objectivec e
   xxx.js -> xxxjs (node.js, vue.js...). Sem essa regra, "c++" e "c#" virariam
   "c", e "node.js" viraria "node" + "js". Os nomes escolhidos são os mesmos
   dos tópicos do GitHub (cpp, csharp, dotnet, nodejs);
3. tokenização: sequências de letras e dígitos (de qualquer alfabeto),
   unidas por - _ . ou apóstrofo, formam um token composto, que é quebrado
   nas partes: "tcp-server" -> tcp, server; "num_workers" -> num, workers.
   No campo nome também quebramos camelCase e guardamos a forma unida:
   "FileWizardAI" -> filewizardai, file, wizard, ai. Fora do nome não
   quebramos camelCase, porque "JavaScript" viraria "java" + "script";
4. ideogramas (chinês, japonês, coreano) não têm espaço entre as palavras:
   viram bigramas de caracteres (o mesmo que o CJKAnalyzer do Lucene);
5. normalização: minúsculas (casefold) e remoção de acentos;
6. filtros: tokens com menos de 2 caracteres (exceto "c" e "r", nomes de
   linguagens), com mais de 25 (hashes, base64) e números com mais de 4
   dígitos (ids, telefones; anos e versões ficam);
7. stopwords em inglês e português (stopwords.py);
8. stemming Snowball para inglês (Porter2), só em palavras ASCII sem dígitos
   e fora dos termos técnicos da etapa 2.

As etapas 5 a 8 dependem só do token, então o resultado de cada token é
guardado num cache: o vocabulário é muito menor que o número de tokens.
"""

import re
import unicodedata
from typing import Dict, Iterator, List, Optional

import snowballstemmer

from .limpeza import limpar
from .stopwords import STOPWORDS

TERMOS_ESPECIAIS = [
    # c++ pode vir colado à versão: C++17 -> cpp 17
    (re.compile(r"(?<![\w+])c\+\+(?![a-z_+])", re.IGNORECASE), " cpp "),
    (re.compile(r"(?<![\w#])c#(?![\w#])", re.IGNORECASE), " csharp "),
    (re.compile(r"(?<![\w#])f#(?![\w#])", re.IGNORECASE), " fsharp "),
    (re.compile(r"\basp\.net\b", re.IGNORECASE), " aspnet "),
    (re.compile(r"(?<![\w.])\.net\b", re.IGNORECASE), " dotnet "),
    (re.compile(r"\bobjective-c\b", re.IGNORECASE), " objectivec "),
    (re.compile(r"\b([a-z0-9]+)\.js\b", re.IGNORECASE), r" \1js "),
]

# Letras e dígitos de qualquer alfabeto ([^\W_]), unidos por - _ . '
TOKEN = re.compile(r"[^\W_]+(?:['._-][^\W_]+)*")
SEPARADORES = re.compile(r"['._-]")
CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+|[^\W\d_]+")
IDEOGRAMAS = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]+")

CURTOS = frozenset({"c", "r"})
# Termos técnicos que o stemmer estragaria: "nodejs" -> "nodej", "macos" ->
# "maco" e, pior, "ios" -> "io", que se confundiria com I/O.
SEM_STEM = frozenset({"cpp", "csharp", "fsharp", "dotnet", "aspnet", "objectivec",
                      "ios", "macos", "ipados", "tvos", "watchos", "visionos"})
MAX_CACHE = 400_000


def sem_acento(t: str) -> str:
    if t.isascii():
        return t
    decomposto = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in decomposto if not unicodedata.combining(ch))
    # O NFKD também decompõe as sílabas do coreano; o NFC as junta de novo.
    return unicodedata.normalize("NFC", t)


class Analisador:
    def __init__(self, remover_stopwords: bool = True, stemming: bool = True,
                 tamanho_min: int = 2, tamanho_max: int = 25, max_digitos: int = 4):
        self.remover_stopwords = remover_stopwords
        self.stemmer = snowballstemmer.stemmer("english") if stemming else None
        self.tamanho_min = tamanho_min
        self.tamanho_max = tamanho_max
        self.max_digitos = max_digitos
        self._cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Etapas 1 a 4: limpeza e tokenização (a caixa original é mantida)
    # ------------------------------------------------------------------
    def tokens(self, texto: str, campo: Optional[str] = None) -> Iterator[str]:
        texto = limpar(texto)
        for padrao, troca in TERMOS_ESPECIAIS:
            texto = padrao.sub(troca, texto)
        compostos = campo == "nome"
        for m in TOKEN.finditer(texto):
            token = m.group()
            partes = SEPARADORES.split(token)
            if compostos:
                pecas = [p for parte in partes for p in CAMEL.findall(parte)]
                if len(pecas) > 1:
                    yield "".join(pecas)
                partes = pecas
            for parte in partes:
                if IDEOGRAMAS.search(parte):
                    yield from self._ideogramas(parte)
                else:
                    yield parte

    @staticmethod
    def _ideogramas(parte: str) -> Iterator[str]:
        fim = 0
        for m in IDEOGRAMAS.finditer(parte):
            if m.start() > fim:
                yield parte[fim:m.start()]
            seq = m.group()
            if len(seq) == 1:
                yield seq
            else:
                for i in range(len(seq) - 1):
                    yield seq[i:i + 2]
            fim = m.end()
        if fim < len(parte):
            yield parte[fim:]

    # ------------------------------------------------------------------
    # Etapas 5 a 8: normalização, filtros, stopwords e stemming
    # ------------------------------------------------------------------
    def normalizar(self, token: str) -> str:
        """Etapas 5 e 6. Devolve "" se o token for descartado."""
        t = sem_acento(token.casefold())
        n = len(t)
        if n > self.tamanho_max:
            return ""
        if n < self.tamanho_min and t.isascii() and t not in CURTOS:
            return ""
        if t.isdigit() and n > self.max_digitos:
            return ""
        return t

    def termo(self, token: str) -> str:
        """Etapas 5 a 8 para um token. Devolve "" se ele for descartado."""
        chave = token
        final = self._cache.get(chave)
        if final is not None:
            return final
        t = self.normalizar(token)
        if t and self.remover_stopwords and t in STOPWORDS:
            t = ""
        if t and self.stemmer is not None and self._stemavel(t):
            t = self.stemmer.stemWord(t)
        if len(self._cache) >= MAX_CACHE:
            self._cache.clear()
        self._cache[chave] = t
        return t

    @staticmethod
    def _stemavel(t: str) -> bool:
        return t.isascii() and t.isalpha() and t not in SEM_STEM and not t.endswith("js")

    def analisar(self, texto: str, campo: Optional[str] = None) -> List[str]:
        """Texto -> lista de termos do índice, na ordem do texto."""
        if not texto:
            return []
        termo = self.termo
        return [t for t in map(termo, self.tokens(texto, campo)) if t]

    # ------------------------------------------------------------------
    # Versão por etapas, usada só nos experimentos (seção 3 do relatório)
    # ------------------------------------------------------------------
    def etapas(self, texto: str, campo: Optional[str] = None) -> Dict[str, List[str]]:
        """Devolve a saída de cada etapa, para medir o efeito de cada uma."""
        tokens = list(self.tokens(texto, campo)) if texto else []
        normalizados = [t for t in map(self.normalizar, tokens) if t]
        sem_stop = [t for t in normalizados if t not in STOPWORDS]
        stems = [self.stemmer.stemWord(t) if self.stemmer and self._stemavel(t) else t
                 for t in sem_stop]
        return {
            "bruto": texto.split() if texto else [],
            "tokens": tokens,
            "normalizados": normalizados,
            "sem_stopwords": sem_stop,
            "stems": stems,
        }
