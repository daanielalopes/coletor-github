"""
Stemmer Porter2 (English Snowball) em Python puro, sem dependências.

Este módulo é usado como alternativa ao pacote ``snowballstemmer`` quando ele
não está instalado, para que o sistema continue a funcionar numa máquina só
com a biblioteca padrão (ver seção de instalação do README). O algoritmo é o
Porter2/English Snowball de Martin Porter (https://snowballstem.org/algorithms/english/stemmer.html);
a implementação segue o mesmo algoritmo do pacote, de modo que o resultado
coincide com ``snowballstemmer`` na grande maioria das palavras.

Interface compatível com o pacote:

    stemmer("english").stemWord(palavra) -> raiz
"""

from typing import List

VOGAIS = frozenset("aeiouy")
DOUBLE = ("bb", "dd", "ff", "gg", "mm", "nn", "pp", "rr", "tt")
VALID_LI = frozenset("cdeghkmnrt")

EXCECOES = {
    "skis": "ski", "skies": "sky", "dying": "die", "lying": "lie", "tying": "tie",
    "idly": "idl", "gently": "gentl", "ugly": "ugli", "early": "earli",
    "only": "onli", "singly": "singl",
    "sky": "sky", "news": "news", "howe": "howe", "atlas": "atlas", "cosmos": "cosmos",
    "bias": "bias", "andes": "andes",
}
EXCECOES2 = frozenset((
    "inning", "outing", "canning", "herring", "earring", "proceed", "exceed", "succeed",
))


def _is_vogal(palavra: str, i: int) -> bool:
    return palavra[i] in VOGAIS


def _region(palavra: str, inicio: int) -> int:
    """Região depois da primeira consoante que vem logo após uma vogal.

    (Definição de R1/R2 do Porter2.) Devolve a posição logo após essa
    consoante, a partir de `inicio`.
    """
    n = len(palavra)
    for i in range(inicio + 1, n):
        if not _is_vogal(palavra, i) and _is_vogal(palavra, i - 1):
            return i + 1
    return n


def _r1(palavra: str) -> int:
    # Exceção do Porter2: gener, commun, arsen começam R1 depois do prefixo.
    for pref in ("gener", "commun", "arsen"):
        if palavra.startswith(pref):
            return len(pref)
    return _region(palavra, 0)


def _is_short_syllable(palavra: str, i: int) -> bool:
    if i == 0:
        return False
    if i == 1:
        return _is_vogal(palavra, 0) and not _is_vogal(palavra, 1)
    # vogal, consoante (não w, x, Y), e a consoante não precedida de vogal
    if (_is_vogal(palavra, i - 2) and not _is_vogal(palavra, i - 1)
            and palavra[i - 1] not in "wxY"):
        return True
    return False


def _is_short(palavra: str, r1: int) -> bool:
    return r1 >= len(palavra) and _is_short_syllable(palavra, len(palavra))


def _termina(palavra: str, sufixos) -> str:
    for s in sufixos:
        if palavra.endswith(s):
            return s
    return ""


class _Porter2:
    def stemWord(self, palavra: str) -> str:
        palavra = palavra.lower()
        if len(palavra) <= 2:
            return palavra
        if palavra in EXCECOES:
            return EXCECOES[palavra]
        if palavra in EXCECOES2:
            return palavra

        # marca Y consonantal com Y maiúsculo
        chars: List[str] = list(palavra)
        if chars[0] == "y":
            chars[0] = "Y"
        for i in range(1, len(chars)):
            if chars[i] == "y" and _is_vogal("".join(chars), i - 1):
                chars[i] = "Y"
        p = "".join(chars)

        # remove apóstrofo inicial
        if p.startswith("'"):
            p = p[1:]

        p = self._passo0(p)
        p = self._passo1a(p)
        if p in EXCECOES2:
            return p.lower()
        p = self._passo1b(p)
        p = self._passo1c(p)
        p = self._passo2(p)
        p = self._passo3(p)
        p = self._passo4(p)
        p = self._passo5(p)
        return p.lower()

    # R1 e R2 são recalculados sobre a palavra corrente. Como os passos só
    # removem/trocam sufixos, as posições continuam válidas; recalcular evita
    # ter de propagar índices por todos os passos.
    def _regioes(self, p: str):
        r1 = _r1(p)
        return r1, _region(p, r1)

    def _passo0(self, p: str) -> str:
        for s in ("'s'", "'s", "'"):
            if p.endswith(s):
                return p[: -len(s)]
        return p

    def _passo1a(self, p: str) -> str:
        if p.endswith("sses"):
            return p[:-4] + "ss"
        if p.endswith(("ied", "ies")):
            return p[:-3] + ("i" if len(p) - 3 > 1 else "ie")
        if p.endswith("ss"):
            return p
        if p.endswith("us"):
            return p
        if p.endswith("s"):
            # remove s se houver vogal antes do penúltimo
            if any(_is_vogal(p, i) for i in range(len(p) - 2)):
                return p[:-1]
        return p

    def _passo1b(self, p: str) -> str:
        r1, _ = self._regioes(p)
        suf = _termina(p, ("eedly", "eed"))
        if suf:
            if len(p) - len(suf) >= r1:
                return p[: -len(suf)] + "ee"
            return p
        suf = _termina(p, ("ingly", "edly", "ing", "ed"))
        if suf:
            base = p[: -len(suf)]
            if any(_is_vogal(base, i) for i in range(len(base))):
                if base.endswith(("at", "bl", "iz")):
                    return base + "e"
                if base.endswith(DOUBLE):
                    return base[:-1]
                if _is_short(base, _r1(base)):
                    return base + "e"
                return base
        return p

    def _passo1c(self, p: str) -> str:
        if len(p) > 2 and p[-1] in "yY" and not _is_vogal(p, len(p) - 2):
            return p[:-1] + "i"
        return p

    def _passo2(self, p: str) -> str:
        r1, _ = self._regioes(p)
        pares = [
            ("ational", "ate"), ("fulness", "ful"), ("ousness", "ous"),
            ("iveness", "ive"), ("ization", "ize"), ("tional", "tion"),
            ("biliti", "ble"), ("lessli", "less"), ("entli", "ent"),
            ("ousli", "ous"), ("fulli", "ful"), ("iviti", "ive"),
            ("aliti", "al"), ("ation", "ate"), ("alism", "al"),
            ("enci", "ence"), ("anci", "ance"), ("abli", "able"),
            ("izer", "ize"), ("ator", "ate"), ("alli", "al"), ("bli", "ble"),
        ]
        for suf, rep in pares:
            if p.endswith(suf):
                if len(p) - len(suf) >= r1:
                    return p[: -len(suf)] + rep
                return p
        if p.endswith("ogi"):
            base = p[:-1]
            if len(p) - 1 >= r1 and base.endswith("log"):
                return base
            return p
        if p.endswith("li"):
            base = p[:-2]
            if len(base) >= r1 and base and base[-1] in VALID_LI:
                return base
            return p
        return p

    def _passo3(self, p: str) -> str:
        r1, r2 = self._regioes(p)
        pares = [
            ("ational", "ate"), ("tional", "tion"), ("alize", "al"),
            ("icate", "ic"), ("iciti", "ic"), ("ical", "ic"),
            ("ful", ""), ("ness", ""),
        ]
        for suf, rep in pares:
            if p.endswith(suf):
                if len(p) - len(suf) >= r1:
                    return p[: -len(suf)] + rep
                return p
        if p.endswith("ative") and len(p) - 5 >= r2:
            return p[:-5]
        return p

    def _passo4(self, p: str) -> str:
        _, r2 = self._regioes(p)
        sufixos = ("ement", "ance", "ence", "able", "ible", "ment",
                   "ant", "ent", "ism", "ate", "iti", "ous", "ive", "ize",
                   "al", "er", "ic")
        for suf in sufixos:   # já ordenados do mais longo p/ o mais curto por grupo
            if p.endswith(suf):
                if len(p) - len(suf) >= r2:
                    return p[: -len(suf)]
                return p
        if p.endswith("ion"):
            base = p[:-3]
            if len(base) >= r2 and base and base[-1] in "st":
                return base
            return p
        return p

    def _passo5(self, p: str) -> str:
        r1, r2 = self._regioes(p)
        if p.endswith("e"):
            base = p[:-1]
            if len(base) >= r2:
                return base
            if len(base) >= r1 and not _is_short_syllable(base, len(base)):
                return base
            return p
        if p.endswith("l") and len(p) >= 2 and p[-2] == "l" and len(p) - 1 >= r2:
            return p[:-1]
        return p


def stemmer(lang: str = "english") -> _Porter2:
    """Compatível com snowballstemmer.stemmer("english")."""
    return _Porter2()
