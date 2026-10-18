"""
Limpeza do texto dos projetos, antes da análise léxica.

O texto vem do coletor (descrição, resumo e README extraídos do HTML). Na
inspeção do projetos.jsonl encontramos, nos 52 mil projetos: cerca de 86 mil
URLs, 32 mil restos de marcação HTML (<img>, <a href>, <details>...), 432
entidades HTML (&amp;, &#39;), 196 mil emojis e caracteres de largura zero
(U+200B, U+200D) no meio das palavras. Nada disso ajuda a busca: as URLs
geram termos como "githubusercontent" e "shields" em milhares de READMEs,
e os caracteres invisíveis partem palavras ao meio.

Os emojis e demais símbolos não precisam de regra: o analisador léxico só
aceita letras e dígitos.
"""

import html
import re
import unicodedata

URL = re.compile(r"(?:https?|ftp)://\S+|\bwww\.\S+", re.IGNORECASE)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Só etiquetas HTML conhecidas: um padrão genérico <...> apagaria texto útil
# de exemplos de código, como List<String>.
TAG = re.compile(
    r"</?(?:a|img|div|p|br|span|b|i|u|s|em|strong|code|pre|kbd|sub|sup|hr|h[1-6]"
    r"|table|thead|tbody|tr|td|th|ul|ol|li|dl|dt|dd|details|summary|picture|source"
    r"|video|audio|center|font|small|blockquote|figure|figcaption|svg|path)\b[^<>]{0,500}>",
    re.IGNORECASE,
)
INVISIVEIS = re.compile("[­​-‏ - ⁠-⁯﻿]")


def limpar(texto: str) -> str:
    """Devolve o texto sem entidades, URLs, e-mails, etiquetas e invisíveis."""
    if not texto:
        return ""
    if "&" in texto:
        texto = html.unescape(texto)
    # NFKC junta formas equivalentes: ligaduras (ﬁ -> fi), letras de largura
    # total do japonês (Ｐｙｔｈｏｎ -> Python), números sobrescritos.
    texto = unicodedata.normalize("NFKC", texto)
    texto = INVISIVEIS.sub("", texto)
    texto = URL.sub(" ", texto)
    if "@" in texto:
        texto = EMAIL.sub(" ", texto)
    if "<" in texto:
        texto = TAG.sub(" ", texto)
    return texto
