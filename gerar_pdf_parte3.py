#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera o relatório final da Parte 3 (recuperação, ranking e interface) em PDF,
formatado conforme a ABNT, usando apenas a biblioteca padrão do Python.

Normas aplicadas (formatação):
- Fonte serifada (Times-Roman), corpo 12.
- Espaçamento entre linhas 1,5 no texto; citação longa e referências em 1,0.
- Margens: esquerda e superior 3 cm; direita e inferior 2 cm (ABNT NBR 14724).
- Recuo da primeira linha do parágrafo: 1,25 cm.
- Títulos de seção numerados (NBR 6024), em negrito.
- Folha de rosto, sumário com paginação e referências (NBR 6023).
- Citações no texto no sistema autor-data (NBR 10520).

Saída: evidencias/relatorio_parte3_abnt.pdf
"""

import zlib

# ---------------------------------------------------------------------------
# Unidades: 1 pt = 1/72 pol; 1 cm = 28.3465 pt
# ---------------------------------------------------------------------------
CM = 28.3464567
PAGE_W = 21.0 * CM          # A4 retrato
PAGE_H = 29.7 * CM
MARGIN_L = 3.0 * CM
MARGIN_R = 2.0 * CM
MARGIN_T = 3.0 * CM
MARGIN_B = 2.0 * CM
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

FONT_REGULAR = "F1"   # Times-Roman
FONT_BOLD = "F2"      # Times-Bold
FONT_ITALIC = "F3"    # Times-Italic

BODY_SIZE = 12
BODY_LEADING = 12 * 1.5     # espaçamento 1,5
SINGLE_LEADING = 12 * 1.16  # espaçamento simples (citação longa / referências)
INDENT = 1.25 * CM          # recuo da primeira linha

# ---------------------------------------------------------------------------
# Métrica das fontes-núcleo (Times) — larguras (Adobe Font Metrics, /1000)
# Carregamos tabelas compactas para medir a largura das linhas e justificar.
# ---------------------------------------------------------------------------
# Largura por caractere para Times-Roman (AFM oficial), em milésimos de em.
TIMES_ROMAN_W = {
    ' ': 250, '!': 333, '"': 408, '#': 500, '$': 500, '%': 833, '&': 778,
    "'": 180, '(': 333, ')': 333, '*': 500, '+': 564, ',': 250, '-': 333,
    '.': 250, '/': 278, '0': 500, '1': 500, '2': 500, '3': 500, '4': 500,
    '5': 500, '6': 500, '7': 500, '8': 500, '9': 500, ':': 278, ';': 278,
    '<': 564, '=': 564, '>': 564, '?': 444, '@': 921, 'A': 722, 'B': 667,
    'C': 667, 'D': 722, 'E': 611, 'F': 556, 'G': 722, 'H': 722, 'I': 333,
    'J': 389, 'K': 722, 'L': 611, 'M': 889, 'N': 722, 'O': 722, 'P': 556,
    'Q': 722, 'R': 667, 'S': 556, 'T': 611, 'U': 722, 'V': 722, 'W': 944,
    'X': 722, 'Y': 722, 'Z': 611, '[': 333, '\\': 278, ']': 333, '^': 469,
    '_': 500, '`': 333, 'a': 444, 'b': 500, 'c': 444, 'd': 500, 'e': 444,
    'f': 333, 'g': 500, 'h': 500, 'i': 278, 'j': 278, 'k': 500, 'l': 278,
    'm': 778, 'n': 500, 'o': 500, 'p': 500, 'q': 500, 'r': 333, 's': 389,
    't': 278, 'u': 500, 'v': 500, 'w': 722, 'x': 500, 'y': 500, 'z': 444,
    '{': 480, '|': 200, '}': 480, '~': 541,
}
# Times-Bold (AFM oficial)
TIMES_BOLD_W = {
    ' ': 250, '!': 333, '"': 555, '#': 500, '$': 500, '%': 1000, '&': 833,
    "'": 278, '(': 333, ')': 333, '*': 500, '+': 570, ',': 250, '-': 333,
    '.': 250, '/': 278, '0': 500, '1': 500, '2': 500, '3': 500, '4': 500,
    '5': 500, '6': 500, '7': 500, '8': 500, '9': 500, ':': 333, ';': 333,
    '<': 570, '=': 570, '>': 570, '?': 500, '@': 930, 'A': 722, 'B': 667,
    'C': 722, 'D': 722, 'E': 667, 'F': 611, 'G': 778, 'H': 778, 'I': 389,
    'J': 500, 'K': 778, 'L': 667, 'M': 944, 'N': 722, 'O': 778, 'P': 611,
    'Q': 778, 'R': 722, 'S': 556, 'T': 667, 'U': 722, 'V': 722, 'W': 1000,
    'X': 722, 'Y': 722, 'Z': 667, '[': 333, '\\': 278, ']': 333, '^': 581,
    '_': 500, '`': 333, 'a': 500, 'b': 556, 'c': 444, 'd': 556, 'e': 444,
    'f': 333, 'g': 500, 'h': 556, 'i': 278, 'j': 333, 'k': 556, 'l': 278,
    'm': 833, 'n': 556, 'o': 500, 'p': 556, 'q': 556, 'r': 444, 's': 389,
    't': 333, 'u': 556, 'v': 500, 'w': 722, 'x': 500, 'y': 500, 'z': 444,
    '{': 394, '|': 220, '}': 394, '~': 520,
}
TIMES_ITALIC_W = dict(TIMES_ROMAN_W)  # aproximação suficiente para medir

# Acentos latinos mais comuns -> largura da letra-base (medição aproximada boa)
_ACCENT_BASE = {
    'á':'a','à':'a','â':'a','ã':'a','ä':'a','é':'e','ê':'e','è':'e','ë':'e',
    'í':'i','î':'i','ì':'i','ï':'i','ó':'o','ô':'o','õ':'o','ò':'o','ö':'o',
    'ú':'u','û':'u','ù':'u','ü':'u','ç':'c','ñ':'n',
    'Á':'A','À':'A','Â':'A','Ã':'A','É':'E','Ê':'E','Í':'I','Ó':'O','Ô':'O',
    'Õ':'O','Ú':'U','Ç':'C',
}


def char_width(ch, size, bold=False, italic=False):
    table = TIMES_BOLD_W if bold else (TIMES_ITALIC_W if italic else TIMES_ROMAN_W)
    if ch in table:
        w = table[ch]
    elif ch in _ACCENT_BASE:
        w = table.get(_ACCENT_BASE[ch], 500)
    else:
        w = 500
    return w / 1000.0 * size


def text_width(s, size, bold=False, italic=False):
    return sum(char_width(c, size, bold, italic) for c in s)


# ---------------------------------------------------------------------------
# Codificação de texto para o PDF.
# Usamos WinAnsiEncoding (Latin-1) nas fontes; convertemos a string para
# bytes latin-1 e escapamos os caracteres especiais do PDF.
# ---------------------------------------------------------------------------
def pdf_escape(s):
    out = []
    for ch in s:
        try:
            b = ch.encode('latin-1')
        except UnicodeEncodeError:
            b = b'?'
        c = b.decode('latin-1')
        if c in ('(', ')', '\\'):
            out.append('\\' + c)
        else:
            out.append(c)
    return ''.join(out)


# ---------------------------------------------------------------------------
# Modelo do documento: lista de "blocos" que depois são paginados.
# Cada bloco vira uma ou mais linhas. Tipos:
#   h1/h2/h3 : título de seção (numerado pelo chamador)
#   p        : parágrafo justificado, com recuo na 1a linha
#   pq       : citação longa (recuo 4 cm, corpo 10, simples, sem aspas)
#   ref      : referência (sem recuo 1a linha; recuo deslocado opcional)
#   bullet   : item de lista com marcador
#   space    : espaço vertical
#   image    : imagem (arquivo, largura em cm)
#   caption  : legenda centralizada
#   keep     : evita quebra entre este bloco e o próximo
# ---------------------------------------------------------------------------

class PDFDoc:
    def __init__(self):
        self.pages = []            # cada página = lista de operações de conteúdo
        self.cur = None            # operações da página atual
        self.y = 0.0               # cursor vertical (do topo pra baixo)
        self.page_no = 0
        self.images = []           # (name, width_px, height_px, rgb_bytes)
        self.first_numbered = None  # página onde começa a numeração visível
        self._pending_targets = {}  # rótulos de seção -> página (para sumário)

    # -- controle de páginas -------------------------------------------------
    def new_page(self):
        self.cur = []
        self.pages.append(self.cur)
        self.page_no += 1
        self.y = PAGE_H - MARGIN_T

    def _ensure_space(self, h):
        if self.y - h < MARGIN_B:
            self.new_page()

    # -- primitivas de desenho ----------------------------------------------
    def _draw_text(self, x, y, s, size, font=FONT_REGULAR, char_space=0.0):
        txt = pdf_escape(s)
        cs = f"{char_space:.3f} Tc " if char_space else ""
        self.cur.append(
            f"BT /{font} {size} Tf {cs}1 0 0 1 {x:.2f} {y:.2f} Tm ({txt}) Tj ET"
        )

    def _draw_runs(self, x, y, runs, size, char_space=0.0):
        """runs: lista de (texto, font). Desenha em sequência a partir de x."""
        cx = x
        for text, font in runs:
            if text:
                self._draw_text(cx, y, text, size, font, char_space)
                bold = (font == FONT_BOLD)
                italic = (font == FONT_ITALIC)
                w = text_width(text, size, bold, italic)
                cx += w + char_space * len(text)

    # -- quebra de linha em palavras ----------------------------------------
    @staticmethod
    def _wrap(words_widths, max_w, space_w, first_indent=0.0):
        """Recebe [(palavra,largura)]; devolve linhas [(palavras, larg_total)]."""
        lines = []
        cur = []
        cur_w = 0.0
        indent = first_indent
        for w, ww in words_widths:
            add = ww if not cur else ww + space_w
            if cur and cur_w + add + indent > max_w:
                lines.append((cur, cur_w))
                cur = [(w, ww)]
                cur_w = ww
                indent = 0.0
            else:
                if cur:
                    cur_w += space_w + ww
                else:
                    cur_w += ww
                cur.append((w, ww))
        if cur:
            lines.append((cur, cur_w))
        return lines


def _runs_from_markup(s):
    """Converte **negrito** e *itálico* simples em runs (texto, fonte)."""
    runs = []
    i = 0
    n = len(s)
    mode = FONT_REGULAR
    buf = []

    def flush():
        if buf:
            runs.append((''.join(buf), mode))
            buf.clear()

    while i < n:
        if s.startswith('**', i):
            flush()
            mode = FONT_REGULAR if mode == FONT_BOLD else FONT_BOLD
            i += 2
        elif s[i] == '*' and not s.startswith('**', i):
            flush()
            mode = FONT_REGULAR if mode == FONT_ITALIC else FONT_ITALIC
            i += 1
        else:
            buf.append(s[i])
            i += 1
    flush()
    return runs


def _plain(s):
    return s.replace('**', '').replace('*', '')


# ---------------------------------------------------------------------------
# Layout de alto nível: recebe os blocos e escreve nas páginas.
# ---------------------------------------------------------------------------
class Report:
    def __init__(self):
        self.doc = PDFDoc()
        self.toc = []  # (nivel, numero, titulo, pagina)

    # ---- títulos -----------------------------------------------------------
    def heading(self, level, number, title, space_before=True):
        d = self.doc
        size = {1: 13, 2: 12, 3: 12}[level]
        leading = size * 1.5
        need = leading + (BODY_LEADING if space_before else 0) + 2
        d._ensure_space(need + leading)  # garante o título + ao menos 1 linha
        if space_before and d.y < PAGE_H - MARGIN_T - 1:
            d.y -= BODY_LEADING
        label = f"{number}  {title}" if number else title
        # registra no sumário (página atual)
        self.toc.append((level, number, title, d.page_no))
        d._draw_text(MARGIN_L, d.y - size, label, size, FONT_BOLD)
        d.y -= leading
        d.y -= size * 0.35

    def unnumbered_heading(self, title, center=False, size=13):
        d = self.doc
        leading = size * 1.5
        d._ensure_space(leading * 2)
        if center:
            w = text_width(title, size, bold=True)
            x = MARGIN_L + (CONTENT_W - w) / 2
        else:
            x = MARGIN_L
        d._draw_text(x, d.y - size, title, size, FONT_BOLD)
        d.y -= leading
        d.y -= size * 0.35

    # ---- parágrafo justificado --------------------------------------------
    def paragraph(self, text, justify=True, indent=INDENT, size=BODY_SIZE,
                  leading=BODY_LEADING):
        d = self.doc
        runs = _runs_from_markup(text)
        # separa em palavras preservando a fonte de cada pedaço
        words = []  # (lista de runs da palavra, largura)
        space_w = char_width(' ', size)
        # transforma runs em tokens de palavra com fonte
        tokens = []
        for rtext, rfont in runs:
            parts = rtext.split(' ')
            for k, part in enumerate(parts):
                if part == '' and k == 0:
                    tokens.append((' ', None))  # espaço inicial de junção
                if part:
                    tokens.append((part, rfont))
                if k < len(parts) - 1:
                    tokens.append((' ', None))
        # agrupa tokens em palavras (sequências sem espaço)
        cur_word = []
        cur_w = 0.0
        for tok, font in tokens:
            if font is None:  # espaço
                if cur_word:
                    words.append((cur_word, cur_w))
                    cur_word = []
                    cur_w = 0.0
            else:
                bold = font == FONT_BOLD
                italic = font == FONT_ITALIC
                ww = text_width(tok, size, bold, italic)
                cur_word.append((tok, font))
                cur_w += ww
        if cur_word:
            words.append((cur_word, cur_w))

        # quebra em linhas respeitando o recuo da primeira
        ww_pairs = [(w, wd) for (w, wd) in words]
        lines = PDFDoc._wrap(ww_pairs, CONTENT_W, space_w, first_indent=indent)

        for li, (line_words, line_w) in enumerate(lines):
            d._ensure_space(leading)
            is_first = (li == 0)
            is_last = (li == len(lines) - 1)
            x0 = MARGIN_L + (indent if is_first else 0.0)
            avail = CONTENT_W - (indent if is_first else 0.0)
            n_sp = len(line_words) - 1
            if justify and not is_last and n_sp > 0:
                extra = (avail - line_w) / n_sp
            else:
                extra = 0.0
            cx = x0
            yb = d.y - size
            for wi, (wruns, wwd) in enumerate(line_words):
                for (tok, font) in wruns:
                    d._draw_text(cx, yb, tok, size, font)
                    bold = font == FONT_BOLD
                    italic = font == FONT_ITALIC
                    cx += text_width(tok, size, bold, italic)
                if wi < n_sp:
                    cx += space_w + extra
            d.y -= leading

    def quote(self, text):
        """Citação longa: recuo 4 cm à esquerda, corpo 10, espaçamento simples."""
        d = self.doc
        size = 10
        leading = size * 1.16
        left = MARGIN_L + 4.0 * CM
        width = PAGE_W - MARGIN_R - left
        space_w = char_width(' ', size)
        words = [(w, text_width(w, size)) for w in text.split()]
        lines = PDFDoc._wrap(words, width, space_w, first_indent=0.0)
        d._ensure_space(leading)
        for words_line, line_w in lines:
            d._ensure_space(leading)
            cx = left
            yb = d.y - size
            for i, (w, ww) in enumerate(words_line):
                d._draw_text(cx, yb, w, size, FONT_REGULAR)
                cx += ww + (space_w if i < len(words_line) - 1 else 0)
            d.y -= leading

    def bullet(self, text, size=BODY_SIZE):
        d = self.doc
        leading = BODY_LEADING
        marker = "\u2013"  # travessão curto (en dash) como marcador
        bx = MARGIN_L + 0.6 * CM
        tx = MARGIN_L + 1.1 * CM
        width = PAGE_W - MARGIN_R - tx
        runs = _runs_from_markup(text)
        # medir palavras com fonte
        words = []
        space_w = char_width(' ', size)
        for rtext, rfont in runs:
            parts = rtext.split(' ')
            for k, part in enumerate(parts):
                if part:
                    bold = rfont == FONT_BOLD
                    italic = rfont == FONT_ITALIC
                    words.append(((part, rfont), text_width(part, size, bold, italic)))
        ww_pairs = [((wtok,), wd) if False else (wtok, wd) for (wtok, wd) in words]
        lines = PDFDoc._wrap([((w,), wd) for (w, wd) in words], width, space_w)
        d._ensure_space(leading)
        first = True
        for line_words, line_w in lines:
            d._ensure_space(leading)
            yb = d.y - size
            if first:
                d._draw_text(bx, yb, marker, size, FONT_REGULAR)
                first = False
            cx = tx
            nsp = len(line_words) - 1
            for i, (wtuple, wd) in enumerate(line_words):
                tok, font = wtuple[0]
                d._draw_text(cx, yb, tok, size, font)
                bold = font == FONT_BOLD
                italic = font == FONT_ITALIC
                cx += text_width(tok, size, bold, italic)
                if i < nsp:
                    cx += space_w
            d.y -= leading

    def reference(self, text):
        """Referência ABNT: espaçamento simples, sem recuo, espaço entre itens."""
        d = self.doc
        size = BODY_SIZE
        leading = SINGLE_LEADING
        runs = _runs_from_markup(text)
        words = []
        space_w = char_width(' ', size)
        for rtext, rfont in runs:
            for part in rtext.split(' '):
                if part:
                    bold = rfont == FONT_BOLD
                    italic = rfont == FONT_ITALIC
                    words.append(((part, rfont), text_width(part, size, bold, italic)))
        lines = PDFDoc._wrap([((w,), wd) for (w, wd) in words], CONTENT_W, space_w)
        d._ensure_space(leading)
        for line_words, line_w in lines:
            d._ensure_space(leading)
            cx = MARGIN_L
            yb = d.y - size
            nsp = len(line_words) - 1
            for i, (wtuple, wd) in enumerate(line_words):
                tok, font = wtuple[0]
                d._draw_text(cx, yb, tok, size, font)
                bold = font == FONT_BOLD
                cx += text_width(tok, size, bold, font == FONT_ITALIC)
                if i < nsp:
                    cx += space_w
            d.y -= leading
        d.y -= size * 0.5  # espaço entre referências

    def vspace(self, pts):
        self.doc._ensure_space(pts)
        self.doc.y -= pts

    def center_line(self, text, size=BODY_SIZE, bold=False):
        d = self.doc
        leading = size * 1.5
        d._ensure_space(leading)
        font = FONT_BOLD if bold else FONT_REGULAR
        w = text_width(text, size, bold=bold)
        x = MARGIN_L + (CONTENT_W - w) / 2
        d._draw_text(x, d.y - size, text, size, font)
        d.y -= leading


# ---------------------------------------------------------------------------
# Imagem: lê um PNG via stdlib (zlib) e converte para XObject RGB.
# Suporta PNG truecolor (8 bits) e truecolor+alpha; aplica alpha sobre branco.
# ---------------------------------------------------------------------------
import struct


def load_png_rgb(path):
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', "nao e PNG"
    pos = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos+4])[0]
        ctype = data[pos+4:pos+8]
        chunk = data[pos+8:pos+8+length]
        pos += 12 + length
        if ctype == b'IHDR':
            width, height, bit_depth, color_type = struct.unpack('>IIBB', chunk[:10])
        elif ctype == b'IDAT':
            idat += chunk
        elif ctype == b'IEND':
            break
    raw = zlib.decompress(bytes(idat))
    if color_type == 2:
        channels = 3
    elif color_type == 6:
        channels = 4
    else:
        raise ValueError(f"PNG color_type {color_type} nao suportado")
    stride = width * channels
    out = bytearray(width * height * 3)
    prev = bytearray(stride)
    p = 0
    oi = 0

    def paeth(a, b, c):
        pp = a + b - c
        pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    for _row in range(height):
        ft = raw[p]; p += 1
        cur = bytearray(raw[p:p+stride]); p += stride
        bpp = channels
        for i in range(stride):
            a = cur[i-bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i-bpp] if i >= bpp else 0
            x = cur[i]
            if ft == 0:
                v = x
            elif ft == 1:
                v = x + a
            elif ft == 2:
                v = x + b
            elif ft == 3:
                v = x + ((a + b) >> 1)
            elif ft == 4:
                v = x + paeth(a, b, c)
            else:
                v = x
            cur[i] = v & 0xFF
        # emite RGB (compondo alpha sobre branco, se houver)
        if channels == 3:
            for px in range(width):
                out[oi] = cur[px*3]; out[oi+1] = cur[px*3+1]; out[oi+2] = cur[px*3+2]
                oi += 3
        else:
            for px in range(width):
                r, g, bb, al = cur[px*4], cur[px*4+1], cur[px*4+2], cur[px*4+3]
                if al == 255:
                    out[oi], out[oi+1], out[oi+2] = r, g, bb
                else:
                    out[oi] = (r*al + 255*(255-al))//255
                    out[oi+1] = (g*al + 255*(255-al))//255
                    out[oi+2] = (bb*al + 255*(255-al))//255
                oi += 3
        prev = cur
    return width, height, bytes(out)


# ===========================================================================
#  MONTAGEM DO RELATÓRIO
# ===========================================================================
def build():
    rep = Report()
    d = rep.doc

    # ----------------------------- FOLHA DE ROSTO --------------------------
    # Espelha o modelo da capa da Parte 1 (PUC Minas), com o ano 2026.
    d.new_page()
    autores = [
        "Camila de Paula Rodrigues",
        "Daniela da Silva Lopes",
        "Luísa Ferreira Marques",
        "Luisa Sapori",
        "Thiago Lacerda Santos Barbosa",
    ]
    # instituição, no topo
    d.y = PAGE_H - MARGIN_T - 1.2 * CM
    rep.center_line("PONTIFÍCIA UNIVERSIDADE CATÓLICA DE MINAS GERAIS",
                    size=12, bold=True)
    rep.center_line("INSTITUTO DE CIÊNCIAS EXATAS E INFORMÁTICA", size=12)
    # autores
    d.y = PAGE_H * 0.70
    for a in autores:
        rep.center_line(a, size=12)
    # título e subtítulo ao centro
    d.y = PAGE_H * 0.52
    rep.center_line("COLETOR GITHUB", size=12, bold=True)
    rep.vspace(2)
    rep.center_line("Sistema de Recuperação da Informação: Coletor, Indexação "
                    "e Recuperação de Repositórios do GitHub", size=12)
    # natureza do trabalho (bloco recuado à direita, padrão ABNT)
    d.y = PAGE_H * 0.36
    nat = ("Trabalho apresentado no curso de graduação da Pontifícia "
           "Universidade Católica de Minas Gerais, no curso de Sistemas de "
           "Informação")
    _justified_block(rep, nat, left=MARGIN_L + CONTENT_W * 0.5, size=12,
                     leading=SINGLE_LEADING)
    rep.vspace(SINGLE_LEADING)
    _justified_block(rep, "Professor: Pedro Felipe Alves de Oliveira",
                     left=MARGIN_L + CONTENT_W * 0.5, size=12,
                     leading=SINGLE_LEADING)
    # local e data no rodapé
    d.y = MARGIN_B + 2.2 * CM
    rep.center_line("Belo Horizonte", size=12)
    rep.center_line("2026", size=12)

    # ------------------------------- SUMÁRIO -------------------------------
    # Reservamos a página do sumário; preenchemos no fim (precisamos das
    # páginas de cada seção). As ~27 entradas cabem em uma página A4.
    d.new_page()
    sumario_page_index = len(d.pages) - 1
    sumario_y_start = PAGE_H - MARGIN_T

    # ------------------------------- CORPO ---------------------------------
    d.new_page()
    body_first_page = d.page_no  # primeira página numerada

    # 1 INTRODUÇÃO
    rep.heading(1, "1", "INTRODUÇÃO", space_before=False)
    rep.paragraph(
        "A Recuperação da Informação (RI) tem como objetivo permitir que "
        "usuários localizem documentos relevantes dentro de grandes coleções "
        "de dados. Este relatório consolida as três etapas do trabalho prático "
        "da disciplina, que, em conjunto, constroem um sistema de busca "
        "vertical sobre projetos de software livre: a coleta das páginas, a "
        "representação e indexação dos documentos e a recuperação com "
        "ranqueamento por relevância, apresentada ao usuário por uma interface "
        "gráfica.")
    rep.paragraph(
        "O sistema é composto por três partes ligadas por arquivos em disco, "
        "sem banco de dados compartilhado. O coletor baixa o HTML das páginas "
        "públicas do GitHub e do SourceForge, segue os links e exporta o "
        "arquivo projetos.jsonl, com um projeto por linha. O indexador lê esse "
        "arquivo, pré-processa o texto e grava um índice invertido com o "
        "método SPIMI, postings comprimidas por gaps e Variable Byte, posições "
        "e frequência por campo. A recuperação e a interface leem o índice, "
        "ordenam os documentos por BM25/BM25F e exibem o resultado ao usuário "
        "por linha de comando e por uma interface gráfica web.")
    rep.paragraph(
        "Todo o código foi escrito em Python. O indexador, a recuperação e a "
        "interface funcionam apenas com a biblioteca padrão da linguagem, o "
        "que simplifica a instalação e permite executar o sistema em qualquer "
        "máquina que tenha o interpretador, inclusive sem acesso à internet. O "
        "texto está organizado em três blocos, correspondentes às três "
        "entregas: o coletor (seção 2), a representação e indexação (seção 3) "
        "e a recuperação, o ranqueamento e a interface (seções 4 a 6), "
        "seguidos da integração entre as partes e da conclusão.")

    # ====================================================================
    # PARTE 1 — COLETOR
    # ====================================================================
    rep.heading(1, "2", "PARTE 1: COLETA DAS PÁGINAS")
    rep.paragraph(
        "A primeira etapa implementa o coletor, responsável por adquirir e "
        "armazenar os documentos que formam a coleção das fases posteriores. "
        "Cada documento corresponde a um projeto público, ou seja, um "
        "repositório do GitHub ou um projeto do SourceForge, com uma parte "
        "textual, formada por nome, descrição, resumo e README, e campos "
        "estruturados como linguagem, licença, tópicos, estrelas e número de "
        "downloads.")

    rep.heading(2, "2.1", "Problema e fonte de dados")
    rep.paragraph(
        "O GitHub e o SourceForge estão entre as plataformas de hospedagem de "
        "projetos de software livre mais conhecidas e se complementam: o "
        "GitHub reúne a maior parte dos projetos novos e ativos, enquanto o "
        "SourceForge guarda muitos projetos clássicos e programas prontos para "
        "baixar. Como os projetos estão distribuídos em mais de uma "
        "plataforma, encontrar aqueles que atendem a uma necessidade torna-se "
        "trabalhoso. Surge daí um problema clássico de RI: dada uma "
        "necessidade de informação em linguagem natural, recuperar as páginas "
        "de projeto mais relevantes, reunindo em uma única coleção o conteúdo "
        "de ambas as plataformas. A fonte de dados são as páginas HTML "
        "públicas de github.com e sourceforge.net, as mesmas que um usuário vê "
        "no navegador; a coleta não utiliza API, pois cada página é baixada e "
        "o seu DOM é interpretado pelo próprio coletor.")

    rep.heading(2, "2.2", "Tipo de coletor e arquitetura")
    rep.paragraph(
        "O coletor é um crawler de HTML vertical e focado: limita-se ao "
        "domínio de software livre e, dentro dos dois sites, só segue links "
        "que levam a páginas de projeto ou de listagem, selecionados pelo "
        "padrão da URL com expressões regulares. Entre as propriedades de "
        "coleta discutidas em aula, o projeto prioriza o volume e a qualidade "
        "dos documentos; quanto à atualização, não há revisitação, pois cada "
        "URL é visitada uma única vez, o que é suficiente para formar uma "
        "coleção estática a ser indexada nas etapas seguintes.")
    rep.paragraph(
        "O coletor reproduz o laço estudado em aula: uma fila de URLs por "
        "domínio, um conjunto de URLs conhecidas para deduplicação, a leitura "
        "do robots.txt, o download com GET, a extração dos campos e dos links "
        "e o enfileiramento apenas dos links novos que passam no filtro. Cada "
        "site tem a sua fila, consumida por uma thread, de modo que os dois "
        "são coletados em paralelo, com no máximo uma requisição por vez a "
        "cada site. O estado completo é mantido em um banco SQLite, usado só "
        "para a fila e a retomada, e o HTML bruto é guardado em blocos "
        "comprimidos; a saída é o arquivo projetos.jsonl.")

    rep.heading(2, "2.3", "Boas maneiras e tolerância a falhas")
    rep.paragraph(
        "Toda requisição se identifica por um User-Agent próprio, respeita o "
        "robots.txt de cada site, lido com a biblioteca protego, e mantém ao "
        "menos um segundo de espera entre requisições ao mesmo domínio. Em "
        "respostas 429 (excesso de requisições) ou 503 (indisponível), o "
        "coletor aplica espera exponencial e, se o limite persistir, coloca "
        "aquele tipo de página em pausa sem perder a URL. O estado em disco "
        "permite retomar a coleta do ponto em que parou; durante a coleta "
        "final, esse mecanismo absorveu as respostas 429 recebidas do GitHub "
        "e as três URLs bloqueadas pelo robots.txt foram respeitadas.")

    rep.heading(2, "2.4", "Critério de parada e resultados da coleta")
    rep.paragraph(
        "A execução de cada site é encerrada quando atinge a meta de páginas "
        "de projeto salvas, quando a fila se esgota ou por interrupção manual. "
        "O critério principal foi a obtenção de mais de 50.000 documentos, "
        "atendendo ao requisito de escala. A coleta final reuniu 52.000 "
        "projetos, 26.000 de cada site, o que superou a meta. A tabela 1 "
        "resume a execução.")
    rep.vspace(4)
    _table(rep, "Tabela 1 \u2013 Resumo da coleta.",
           [
               ("Métrica", "Valor"),
               ("Projetos coletados", "52.000"),
               ("Páginas baixadas (total)", "60.511"),
               ("Erros (total)", "122"),
               ("Volume baixado (sem gzip)", "15,2 GB"),
               ("Preenchimento do nome", "100%"),
               ("Preenchimento do dono", "100%"),
               ("Preenchimento da descrição", "99,5%"),
           ],
           "Fonte: elaborado pelos autores (2026).")
    rep.paragraph(
        "Ao final da coleta, a fronteira do GitHub ainda continha mais de 150 "
        "mil URLs na fila, o que mostra que o critério de parada foi a meta de "
        "projetos, e não a falta de URLs a visitar. Os projetos foram "
        "exportados para o arquivo projetos.jsonl, com um projeto por linha, "
        "que é a entrada da etapa de indexação.")

    # ====================================================================
    # PARTE 2 — REPRESENTAÇÃO E INDEXAÇÃO
    # ====================================================================
    rep.heading(1, "3", "PARTE 2: REPRESENTAÇÃO E INDEXAÇÃO")
    rep.paragraph(
        "A segunda etapa transforma os 52.000 projetos coletados em um índice "
        "invertido próprio, gravado em arquivos, sem o uso de qualquer banco "
        "de dados. A entrada projetos.jsonl é lida linha a linha e o índice é "
        "um conjunto de arquivos binários e de texto em formato definido pelos "
        "autores, escritos e lidos pelo próprio programa.")

    rep.heading(2, "3.1", "Documento, campos e pré-processamento")
    rep.paragraph(
        "O documento continua sendo a página de um projeto. Como os dois sites "
        "têm campos diferentes, o texto é reunido em quatro campos comuns: "
        "nome, descrição, rótulos e README. A coleção é muito desequilibrada: "
        "um projeto do GitHub tem, em média, cerca de 939 termos, quase todos "
        "do README, contra 44 termos de um projeto do SourceForge. Esse "
        "desequilíbrio é o principal motivo para estudar granularidades "
        "diferentes na representação.")
    rep.paragraph(
        "O pré-processamento abrange a limpeza dos dados, que remove URLs, "
        "etiquetas HTML residuais, emojis, caracteres invisíveis, entidades e "
        "hashes, e a análise léxica. O analisador trata termos técnicos com "
        "símbolos, convertendo \u201cC++\u201d em cpp e \u201cC#\u201d em "
        "csharp, tokeniza letras e dígitos de qualquer alfabeto, quebra "
        "compostos e camelCase no nome, transforma sequências de ideogramas em "
        "bigramas, passa tudo para minúsculas sem acento, remove stopwords de "
        "inglês e português e aplica o stemmer Snowball (Porter2). A consulta "
        "passa exatamente pelo mesmo analisador, de modo a cair no mesmo "
        "vocabulário do índice.")

    rep.heading(2, "3.2", "Leis de Zipf e de Heaps")
    rep.paragraph(
        "A coleção obedece às leis empíricas vistas em aula. Pela lei de Zipf, "
        "a frequência de um termo cai com a sua posição no ranking de "
        "frequência, com inclinação próxima de \u22121,26 em escala log-log. A "
        "cauda é enorme: cerca de 64,9% do vocabulário são termos que aparecem "
        "em um único documento, como nomes de projetos, identificadores de "
        "código e palavras de outras línguas. Pela lei de Heaps, o vocabulário "
        "cresce com o número de tokens segundo um expoente estimado em 0,72, "
        "acima do usual de textos comuns em inglês, porque os READMEs contêm "
        "muito código e termos em várias línguas.")

    rep.heading(2, "3.3", "Construção e compressão do índice")
    rep.paragraph(
        "O índice é construído com o método SPIMI (Single-Pass In-Memory "
        "Indexing): processos auxiliares analisam os documentos em paralelo, o "
        "processo principal acumula as postings em blocos, grava cada bloco "
        "ordenado em disco e, ao final, funde os blocos por fusão de k vias. "
        "Assim, a memória da construção depende do tamanho do bloco, e não do "
        "tamanho da coleção. Cada termo é distribuído em uma de dezesseis "
        "partições pela função crc32, o que permite carregar apenas o léxico "
        "da partição consultada.")
    rep.paragraph(
        "As listas são comprimidas com diferenças (gaps) entre docids "
        "consecutivos, cada número codificado em Variable Byte, como no "
        "capítulo 5 de Manning, Raghavan e Schütze (2008). Cada entrada guarda "
        "o gap do docid, uma máscara de um byte indicando em quais campos o "
        "termo aparece e a frequência por campo; as posições ficam em arquivo "
        "separado, lido apenas quando a consulta precisa delas. A compressão "
        "reduz as listas de postings e posições a 36% do tamanho que teriam "
        "sem compressão.")

    rep.heading(2, "3.4", "Decisão de granularidade e números do índice")
    rep.paragraph(
        "Foram comparadas três granularidades: por documento (todos os campos "
        "juntos), por campo (frequência de cada campo separada na posting) e "
        "por chunk (o README dividido em janelas, com a nota do projeto dada "
        "pela melhor janela). A granularidade por campo foi escolhida por ser "
        "a menor representação que preserva a informação de campo, necessária "
        "ao BM25F da etapa seguinte, já que o nome e os rótulos de um projeto "
        "são sinais muito mais fortes de relevância do que uma linha qualquer "
        "do README. Os números do índice escolhido aparecem na tabela 2.")
    rep.vspace(4)
    _table(rep, "Tabela 2 \u2013 Números do índice escolhido (granularidade "
                "por campo).",
           [
               ("Métrica", "Valor"),
               ("Documentos (projetos)", "52.000"),
               ("Vocabulário (termos)", "779.148"),
               ("Postings (pares termo-unidade)", "9.783.738"),
               ("Ocorrências (tokens)", "25.575.077"),
               ("Tempo total de indexação", "97,8 s"),
               ("Memória de pico", "216 MB"),
               ("Postings e posições (comprimidas)", "66,8 MB"),
               ("Postings e posições (sem compressão)", "183,6 MB"),
           ],
           "Fonte: elaborado pelos autores (2026).")

    # ====================================================================
    # PARTE 3 — RECUPERAÇÃO, RANKING E INTERFACE
    # ====================================================================
    rep.heading(1, "4", "PARTE 3: RECUPERAÇÃO PELO ÍNDICE INVERTIDO")
    rep.paragraph(
        "A recuperação está implementada na classe Indice, do módulo "
        "indexador/indice.py. O ponto central da avaliação é que a busca "
        "consulta o índice invertido, e não faz uma varredura dos documentos "
        "nem uma busca simplificada à parte. Para cada termo da consulta, o "
        "sistema executa os passos a seguir.")
    rep.paragraph(
        "**Análise idêntica à da indexação.** A consulta passa pelo mesmo "
        "analisador usado na indexação, de modo que a expressão \u201cC++\u201d "
        "vira o termo cpp e \u201cmachine learning\u201d vira machin learn. "
        "Isso garante que a consulta caia no mesmo vocabulário do índice.")
    rep.paragraph(
        "**Léxico por partição.** O léxico é dividido em dezesseis partições "
        "pela função crc32 do termo. Apenas a partição do termo pedido é "
        "carregada, de forma que não é necessário ler o vocabulário inteiro, "
        "com 779.148 termos no índice completo, para responder a uma consulta.")
    rep.paragraph(
        "**Leitura direcionada das postings.** A entrada do léxico guarda o "
        "deslocamento e o tamanho da lista de cada termo. O sistema posiciona "
        "o ponteiro do arquivo com a operação seek e lê apenas os bytes "
        "daquele termo, decodificando os gaps em Variable Byte para "
        "reconstruir as unidades e as frequências por campo. As posições ficam "
        "em um arquivo separado e só são lidas quando a consulta precisa delas, "
        "como em uma busca por frase.")
    rep.paragraph(
        "Essa é a definição de recuperação por índice invertido: da consulta "
        "vai-se direto às listas de documentos de cada termo, sem examinar os "
        "documentos que não contêm os termos. O comando de inspeção de termo, "
        "disponível tanto na linha de comando quanto na interface, mostra a "
        "entrada lida do índice para cada termo, o que torna visível a origem "
        "dos resultados. O teste automatizado confirma, termo a termo, que as "
        "listas recuperadas coincidem com um índice calculado por força bruta, "
        "o que comprova a correção da recuperação.")

    # 5 RANKING POR RELEVÂNCIA
    rep.heading(1, "5", "RANKING POR RELEVÂNCIA (BM25 E BM25F)")
    rep.paragraph(
        "O ranqueamento está na classe Buscador, do módulo "
        "indexador/busca.py. Adotou-se a família BM25, proposta por Robertson "
        "e Spärck Jones, hoje o modelo probabilístico padrão de recuperação, "
        "com a extensão BM25F descrita por Robertson e Zaragoza (2009), que "
        "atribui pesos diferentes aos campos de um documento.")

    rep.heading(2, "5.1", "Importância do termo (IDF)")
    rep.paragraph(
        "A importância de um termo diminui conforme cresce o número de "
        "documentos em que ele ocorre. Utiliza-se o IDF probabilístico do "
        "BM25, definido pela equação:")
    rep.vspace(2)
    _formula(rep, "idf(t) = log( 1 + (N \u2212 df(t) + 0,5) / (df(t) + 0,5) )")
    rep.paragraph(
        "em que N é o número de unidades indexadas e df(t) é o número de "
        "unidades em que o termo ocorre. A soma de um antes do logaritmo evita "
        "valores negativos de IDF para termos muito comuns, com df maior que "
        "N/2, problema clássico da fórmula original do BM25.")

    rep.heading(2, "5.2", "Saturação da frequência")
    rep.paragraph(
        "A frequência de um termo no documento contribui com retornos "
        "decrescentes: a décima ocorrência vale menos que a segunda. O BM25 "
        "modela esse efeito pela expressão:")
    rep.vspace(2)
    _formula(rep, "peso = tf \u00b7 (k1 + 1) / (tf + k1),  com k1 = 1,2")
    rep.paragraph(
        "Na implementação usa-se a forma equivalente idf \u00b7 tf / (k1 + tf), "
        "pois a constante (k1 + 1) é um fator comum que não altera a "
        "ordenação. O valor k1 = 1,2 é o usual da literatura.")

    rep.heading(2, "5.3", "Normalização por comprimento e pesos de campo")
    rep.paragraph(
        "Documentos longos tendem a ter frequências maiores apenas por serem "
        "longos. O BM25 corrige isso normalizando pelo comprimento da unidade "
        "em relação ao comprimento médio, pela expressão:")
    rep.vspace(2)
    _formula(rep, "norm = 1 \u2212 b + b \u00b7 (comprimento / comprimento_médio),  com b = 0,75")
    rep.paragraph(
        "No BM25F, usado na granularidade por campo, cada campo é normalizado "
        "pelo seu próprio comprimento médio, ponderado pelo peso do campo e "
        "somado antes da saturação, conforme as equações:")
    rep.vspace(2)
    _formula(rep, "tf_f = \u03a3 (peso_campo \u00b7 tf_campo / norm_campo)")
    _formula(rep, "nota(d) = \u03a3 idf(t) \u00b7 qtf(t) \u00b7 tf_f / (k1 + tf_f)")
    rep.paragraph(
        "em que qtf(t) é o número de vezes que o termo aparece na própria "
        "consulta. Somar por campo antes da saturação é o que distingue o "
        "BM25F de simplesmente ranquear cada campo à parte: um termo que "
        "aparece no nome e na descrição conta de forma conjunta, com os "
        "respectivos pesos. Os pesos provisórios adotados foram três para o "
        "nome, dois para a descrição, dois para os rótulos e um para o README, "
        "refletindo o fato de que o nome e a descrição de um projeto são "
        "sinais mais fortes de relevância do que o texto longo do README.")

    rep.heading(2, "5.4", "Granularidades de indexação")
    rep.paragraph(
        "O sistema admite três granularidades. Na granularidade por campo, "
        "padrão, há uma unidade por projeto com a frequência de cada campo "
        "separada, o que corresponde ao BM25F. Na granularidade por "
        "documento, há uma unidade por projeto com todos os campos reunidos, "
        "o que corresponde ao BM25 clássico. Na granularidade por chunk, o "
        "README é dividido em janelas e a nota do projeto é a da sua melhor "
        "janela, estratégia conhecida como max passage, útil para READMEs "
        "longos.")

    # 6 INTERFACE COM O USUÁRIO
    rep.heading(1, "6", "INTERFACE COM O USUÁRIO")
    rep.paragraph(
        "O trabalho pede uma interface gráfica para o usuário. Optou-se por "
        "uma interface web servida pelo módulo interface/app.py, por três "
        "razões. Primeiro, ela não tem dependências externas, pois usa apenas "
        "o módulo http.server da biblioteca padrão, dispensando a instalação "
        "de frameworks como Flask ou Django. Segundo, é acessível, pois abre "
        "no navegador, em qualquer sistema operacional, sem instalação de "
        "cliente. Terceiro, é aberta, pois todo o código é próprio e está no "
        "repositório.")
    rep.paragraph(
        "O ponto mais importante do ponto de vista da avaliação é que a "
        "interface não possui busca própria. No início, o servidor carrega uma "
        "instância de Indice e uma de Buscador, as mesmas classes usadas pela "
        "busca de linha de comando, e toda consulta é atendida pelo método "
        "Buscador.buscar. Os endpoints disponíveis são a página HTML, a rota "
        "de busca, a rota de inspeção de termo e a rota de estatísticas do "
        "índice. O teste automatizado da interface verifica que a lista de "
        "URLs devolvida pela rota de busca é idêntica, na mesma ordem, à do "
        "Buscador chamado diretamente, o que comprova que a camada de "
        "apresentação não faz uma busca diferente ou simplificada.")
    rep.paragraph(
        "A cada consulta, a interface mostra os resultados ranqueados, com "
        "posição, nota, nome com link, site de origem, linguagem, licença, "
        "número de estrelas e um trecho da descrição. Mostra ainda os termos "
        "em que a consulta foi analisada, cada um com o seu df e cf no índice, "
        "e, ao clicar em um termo, exibe o detalhe da sua entrada no índice "
        "invertido, com a partição, o df, o cf e as primeiras postings. A "
        "figura 1 apresenta uma captura real da interface para a consulta "
        "\u201cmachine learning\u201d sobre o índice de amostra.")

    # figura
    rep.vspace(4)
    _image_centered(rep, "evidencias/interface/busca_machine_learning.png",
                    max_w_cm=13.0)
    _caption(rep, "Figura 1 \u2013 Interface web de busca para a consulta "
                  "\u201cmachine learning\u201d.")
    _caption(rep, "Fonte: elaborado pelos autores (2026).", small=True)

    # 7 INTEGRAÇÃO E TESTES
    rep.heading(1, "7", "INTEGRAÇÃO ENTRE AS PARTES E TESTES")
    rep.paragraph(
        "As três partes se integram por arquivos em disco, o que as mantém "
        "desacopladas e permite testar cada uma de forma isolada. O coletor "
        "exporta o arquivo projetos.jsonl; o indexador lê esse arquivo e "
        "unifica os campos do GitHub e do SourceForge em quatro campos comuns, "
        "nome, descrição, rótulos e README, gravando a pasta do índice; a "
        "busca lê essa pasta e ordena os resultados. A linha de comando e a "
        "interface web são duas camadas finas sobre o mesmo par de classes "
        "Indice e Buscador.")
    rep.paragraph(
        "A suíte de testes é executada com o utilitário unittest. Ela cobre a "
        "compressão Variable Byte, o analisador de texto, o índice comparado "
        "com um cálculo por força bruta nas três granularidades, o "
        "comportamento do ranqueamento BM25F e a equivalência entre a "
        "interface web e o Buscador. Nesta máquina, a suíte foi concluída em "
        "menos de um segundo, com vinte e oito testes bem-sucedidos e quatro "
        "ignorados, estes últimos por dependerem de dados ou de um pacote "
        "externo opcional. O teste de maior valor para esta etapa é o que "
        "garante, de forma automática, que a interface utiliza o mecanismo de "
        "busca do próprio sistema, e não uma busca à parte.")

    # 8 DECISÕES DE PROJETO E MELHORIAS
    rep.heading(1, "8", "DECISÕES DE PROJETO E MELHORIAS APÓS A ENTREGA PARCIAL")
    rep.heading(2, "8.1", "BM25F em vez de modelo vetorial")
    rep.paragraph(
        "Considerou-se o modelo vetorial com TF-IDF e similaridade do cosseno, "
        "mas optou-se pelo BM25F. A vantagem é que o BM25 satura a frequência, "
        "sem premiar a repetição exagerada de termos, e normaliza o "
        "comprimento de maneira controlada pelo parâmetro b; o BM25F ainda "
        "concede peso por campo, essencial neste domínio, pois o nome e a "
        "descrição de um projeto importam muito mais do que o README. A "
        "desvantagem é a existência de três parâmetros a calibrar, a saber "
        "k1, b e os pesos de campo; adotaram-se os valores usuais da "
        "literatura e pesos provisórios, deixando a calibração com "
        "julgamentos de relevância como trabalho futuro.")

    rep.heading(2, "8.2", "Interface web sem framework")
    rep.paragraph(
        "Cogitou-se o uso de Flask ou Streamlit, mas optou-se pelo módulo "
        "http.server da biblioteca padrão. A vantagem é não acrescentar "
        "nenhuma dependência, com instalação trivial e execução em qualquer "
        "máquina. A desvantagem é a ausência de recursos prontos de um "
        "framework, como rotas e templates; como a interface é pequena, com "
        "uma página e quatro endpoints, essa ausência não pesou.")

    rep.heading(2, "8.3", "Stemmer opcional para portabilidade")
    rep.paragraph(
        "Na entrega parcial, o indexador dependia obrigatoriamente do pacote "
        "externo snowballstemmer. Em uma máquina sem internet, o sistema não "
        "funcionava. Para corrigir, implementou-se o algoritmo Porter2 em "
        "Python puro, e o analisador passou a usá-lo automaticamente quando o "
        "pacote não está instalado, emitindo um aviso. Assim, o sistema "
        "inteiro passou a funcionar apenas com a biblioteca padrão. O stemmer "
        "interno coincide com o pacote na quase totalidade das palavras; "
        "quando o pacote está presente, ele continua sendo usado, por ser um "
        "pouco mais rápido.")

    rep.heading(2, "8.4", "Testes de ranqueamento e de interface")
    rep.paragraph(
        "A entrega parcial testava o índice, isto é, a leitura das postings, "
        "mas não o ranqueamento nem a camada de apresentação. Nesta etapa "
        "acrescentou-se um conjunto de testes que verifica o comportamento do "
        "BM25F, incluindo o peso de campo, a saturação e o IDF, e que garante "
        "que a interface web devolve exatamente o resultado do Buscador.")

    # 7 RESULTADOS
    rep.heading(1, "9", "RESULTADOS E NÚMEROS DO SISTEMA")
    rep.paragraph(
        "O tamanho do índice completo, cujos números principais constam da "
        "tabela 2, evidencia o efeito da compressão: o índice invertido ocupa "
        "91,8 MB, contra 183,6 MB que ocuparia sem compressão, e o índice "
        "total em disco soma 118,7 MB, incluindo o léxico, os metadados e os "
        "comprimentos. A maior lista de postings, do termo mais frequente, tem "
        "30.228 entradas. Cada consulta ao índice completo lê apenas os bytes "
        "dos termos pedidos, graças ao léxico por partição e à leitura "
        "direcionada descrita na seção 4.")
    rep.paragraph(
        "Para a demonstração desta revisão, utilizou-se também um índice de "
        "amostra com 100 projetos, no qual cada consulta é respondida em cerca "
        "de um milissegundo. Nesse índice, a consulta \u201cstatic site "
        "generator\u201d coloca em primeiro lugar um projeto que contém os três "
        "termos, dois deles no nome e na descrição, à frente de projetos que "
        "trazem apenas um dos termos de forma isolada, o que é exatamente o "
        "efeito esperado do BM25F com maior peso para nome e descrição.")

    # 10 CONCLUSÃO
    rep.heading(1, "10", "CONCLUSÃO")
    rep.paragraph(
        "O sistema cobre o ciclo completo de recuperação da informação: "
        "coleta, indexação com índice invertido comprimido, recuperação "
        "direcionada pelo índice, ranqueamento por BM25 e BM25F e apresentação "
        "ao usuário por linha de comando e por uma interface gráfica web. A "
        "recuperação é comprovadamente feita pelo índice invertido, tanto "
        "pelos testes contra força bruta quanto pela exibição das postings na "
        "própria interface, e a interface utiliza o mesmo mecanismo de busca "
        "do sistema, o que é garantido por teste automatizado. As melhorias "
        "feitas após a entrega parcial, o stemmer opcional e os testes de "
        "ranqueamento e de interface, aumentaram a portabilidade do sistema e "
        "a confiança em seu funcionamento.")

    # REFERÊNCIAS
    rep.heading(1, "", "REFERÊNCIAS", space_before=True)
    refs = [
        "MANNING, Christopher D.; RAGHAVAN, Prabhakar; SCHÜTZE, Hinrich. "
        "**Introduction to information retrieval.** Cambridge: Cambridge "
        "University Press, 2008.",

        "ROBERTSON, Stephen; ZARAGOZA, Hugo. The probabilistic relevance "
        "framework: BM25 and beyond. **Foundations and Trends in Information "
        "Retrieval**, v. 3, n. 4, p. 333\u2013389, 2009.",

        "ROBERTSON, Stephen E.; WALKER, Steve; JONES, Susan; HANCOCK-BEAULIEU, "
        "Micheline M.; GATFORD, Mike. Okapi at TREC-3. In: TEXT RETRIEVAL "
        "CONFERENCE (TREC-3), 1994, Gaithersburg. **Proceedings** [...]. "
        "Gaithersburg: NIST, 1995. p. 109\u2013126.",

        "PORTER, Martin F. **The English (Porter2) stemming algorithm.** "
        "Snowball, 2002. Disponível em: "
        "http://snowballstem.org/algorithms/english/stemmer.html. "
        "Acesso em: 2026.",

        "HEAPS, Harold S. **Information retrieval: computational and "
        "theoretical aspects.** New York: Academic Press, 1978.",

        "PYTHON SOFTWARE FOUNDATION. **http.server \u2014 HTTP servers.** "
        "Python 3 documentation. Disponível em: "
        "https://docs.python.org/3/library/http.server.html. Acesso em: 2025.",
    ]
    rep.vspace(4)
    for r in refs:
        rep.reference(r)

    # ------------------------- NUMERAÇÃO DAS PÁGINAS -----------------------
    # ABNT: conta a partir da folha de rosto, imprime a partir da introdução.
    # Folha de rosto = pág 1 (não impressa); sumário = pág 2 (não impressa);
    # corpo começa na pág 3 (impressa).
    _paginate(d, first_printed_page=body_first_page)

    # ------------------------------ SUMÁRIO --------------------------------
    _render_sumario(d, rep.toc, sumario_page_index, sumario_y_start)

    return d


# ------------------ auxiliares de layout de alto nível ---------------------
def _justified_block(rep, text, left, size, leading):
    d = rep.doc
    width = PAGE_W - MARGIN_R - left
    space_w = char_width(' ', size)
    words = [(w, text_width(w, size)) for w in text.split()]
    lines = PDFDoc._wrap(words, width, space_w)
    for li, (words_line, line_w) in enumerate(lines):
        is_last = li == len(lines) - 1
        n_sp = len(words_line) - 1
        extra = (width - line_w) / n_sp if (not is_last and n_sp > 0) else 0.0
        cx = left
        yb = d.y - size
        for i, (w, ww) in enumerate(words_line):
            d._draw_text(cx, yb, w, size, FONT_REGULAR)
            cx += ww
            if i < n_sp:
                cx += space_w + extra
        d.y -= leading


def _formula(rep, text):
    """Fórmula centralizada, em itálico, espaçamento simples."""
    d = rep.doc
    size = 12
    leading = size * 1.5
    d._ensure_space(leading)
    w = text_width(text, size, italic=True)
    x = MARGIN_L + (CONTENT_W - w) / 2
    d._draw_text(x, d.y - size, text, size, FONT_ITALIC)
    d.y -= leading


def _image_centered(rep, path, max_w_cm):
    d = rep.doc
    w_px, h_px, rgb = load_png_rgb(path)
    name = f"Im{len(d.images)+1}"
    d.images.append((name, w_px, h_px, rgb))
    max_w = max_w_cm * CM
    scale = min(max_w / w_px, 1.0) if w_px else 1.0
    draw_w = w_px * scale
    draw_h = h_px * scale
    # limita altura ao espaço útil
    if draw_h > (PAGE_H - MARGIN_T - MARGIN_B):
        s2 = (PAGE_H - MARGIN_T - MARGIN_B) / draw_h
        draw_w *= s2
        draw_h *= s2
    d._ensure_space(draw_h + 4)
    x = MARGIN_L + (CONTENT_W - draw_w) / 2
    y = d.y - draw_h
    d.cur.append(
        f"q {draw_w:.2f} 0 0 {draw_h:.2f} {x:.2f} {y:.2f} cm /{name} Do Q"
    )
    d.y -= draw_h + 4


def _caption(rep, text, small=False):
    d = rep.doc
    size = 10 if not small else 10
    leading = size * 1.2
    d._ensure_space(leading)
    w = text_width(text, size)
    # quebra se não couber
    if w <= CONTENT_W:
        x = MARGIN_L + (CONTENT_W - w) / 2
        d._draw_text(x, d.y - size, text, size, FONT_REGULAR)
        d.y -= leading
    else:
        space_w = char_width(' ', size)
        words = [(wd, text_width(wd, size)) for wd in text.split()]
        for words_line, lw in PDFDoc._wrap(words, CONTENT_W, space_w):
            d._ensure_space(leading)
            x = MARGIN_L + (CONTENT_W - lw) / 2
            cx = x
            yb = d.y - size
            for i, (wd, ww) in enumerate(words_line):
                d._draw_text(cx, yb, wd, size, FONT_REGULAR)
                cx += ww + (space_w if i < len(words_line)-1 else 0)
            d.y -= leading


def _table(rep, title, rows, source):
    """Tabela simples de duas colunas, no padrão ABNT (traços horizontais)."""
    d = rep.doc
    size = 11
    leading = size * 1.4
    col1 = CONTENT_W * 0.62
    # título acima da tabela
    _caption(rep, title, small=True)
    d.y -= 2
    top = d.y
    d._ensure_space(leading * (len(rows) + 1) + 10)
    top = d.y
    # linha superior
    def hline(yy):
        d.cur.append(f"0.6 w {MARGIN_L:.2f} {yy:.2f} m "
                     f"{MARGIN_L+CONTENT_W:.2f} {yy:.2f} l S")
    hline(d.y)
    d.y -= 4
    for idx, (c1, c2) in enumerate(rows):
        d._ensure_space(leading)
        yb = d.y - size
        font1 = FONT_BOLD if idx == 0 else FONT_REGULAR
        font2 = FONT_BOLD if idx == 0 else FONT_REGULAR
        d._draw_text(MARGIN_L + 2, yb, c1, size, font1)
        d._draw_text(MARGIN_L + col1, yb, c2, size, font2)
        d.y -= leading
        if idx == 0:
            d.y -= 1
            hline(d.y + leading*0.15)
            d.y -= 2
    d.y -= 2
    hline(d.y)
    d.y -= 4
    _caption(rep, source, small=True)


def _paginate(d, first_printed_page):
    """Escreve o número no canto superior direito a partir da página indicada."""
    size = 10
    for i, ops in enumerate(d.pages):
        page_number = i + 1  # contagem ABNT inclui folha de rosto
        if page_number < first_printed_page:
            continue
        num = str(page_number)
        w = text_width(num, size)
        x = PAGE_W - MARGIN_R - w
        y = PAGE_H - (2.0 * CM) + 6  # a 2 cm do topo
        ops.append(
            f"BT /{FONT_REGULAR} {size} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm "
            f"({pdf_escape(num)}) Tj ET"
        )


def _render_sumario(d, toc, page_index, y_start):
    """Preenche a(s) página(s) reservada(s) do sumário com os títulos e as
    páginas. Quando o conteúdo não cabe na primeira página reservada, segue na
    página seguinte (também reservada na montagem)."""
    size = 12
    leading = size * 1.5
    cur_index = page_index
    ops = d.pages[cur_index]
    # título SUMÁRIO centralizado
    title = "SUMÁRIO"
    w = text_width(title, 13, bold=True)
    x = MARGIN_L + (CONTENT_W - w) / 2
    y = y_start
    ops.append(
        f"BT /{FONT_BOLD} 13 Tf 1 0 0 1 {x:.2f} {y - 13:.2f} Tm "
        f"({pdf_escape(title)}) Tj ET"
    )
    y -= leading * 2
    for level, number, ttl, pg in toc:
        # quebra para a próxima página reservada se faltar espaço
        if y - leading < MARGIN_B and cur_index + 1 < len(d.pages):
            cur_index += 1
            ops = d.pages[cur_index]
            y = y_start
        label = f"{number}  {ttl}" if number else ttl
        font = FONT_BOLD if level == 1 and number else FONT_REGULAR
        indent = 0.0 if level == 1 else (0.8 * CM if level == 2 else 1.6 * CM)
        page_str = str(pg)
        lead_w = text_width(label, size, bold=(font == FONT_BOLD))
        pg_w = text_width(page_str, size)
        xa = MARGIN_L + indent
        xb = MARGIN_L + CONTENT_W
        yb = y - size
        ops.append(
            f"BT /{font} {size} Tf 1 0 0 1 {xa:.2f} {yb:.2f} Tm "
            f"({pdf_escape(label)}) Tj ET"
        )
        # pontilhado
        dot = "."
        dot_w = text_width(dot, size)
        start = xa + lead_w + 4
        end = xb - pg_w - 4
        if end > start:
            ndots = int((end - start) / dot_w)
            dots = "." * max(ndots, 0)
            ops.append(
                f"BT /{FONT_REGULAR} {size} Tf 1 0 0 1 {start:.2f} {yb:.2f} Tm "
                f"({pdf_escape(dots)}) Tj ET"
            )
        ops.append(
            f"BT /{FONT_REGULAR} {size} Tf 1 0 0 1 {xb - pg_w:.2f} {yb:.2f} Tm "
            f"({pdf_escape(page_str)}) Tj ET"
        )
        y -= leading


# ---------------------------------------------------------------------------
# Serialização do PDF (objetos, fontes, imagens, páginas).
# ---------------------------------------------------------------------------
def write_pdf(doc, out_path):
    objects = []  # cada item: bytes do corpo do objeto (sem "n 0 obj")

    def add(obj_bytes):
        objects.append(obj_bytes)
        return len(objects)  # número do objeto (1-based)

    # Fontes (núcleo, WinAnsiEncoding)
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman "
             b"/Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Bold "
             b"/Encoding /WinAnsiEncoding >>")
    f3 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Italic "
             b"/Encoding /WinAnsiEncoding >>")

    # Imagens -> XObjects
    img_obj = {}
    for (name, w_px, h_px, rgb) in doc.images:
        comp = zlib.compress(rgb, 9)
        body = (b"<< /Type /XObject /Subtype /Image /Width " +
                str(w_px).encode() + b" /Height " + str(h_px).encode() +
                b" /ColorSpace /DeviceRGB /BitsPerComponent 8 "
                b"/Filter /FlateDecode /Length " + str(len(comp)).encode() +
                b" >>\nstream\n" + comp + b"\nendstream")
        img_obj[name] = add(body)

    # Páginas: primeiro reservamos números para Pages e Catalog
    # Criamos os content streams e page dicts.
    page_obj_nums = []
    content_obj_nums = []

    # Precisamos do número do objeto Pages antes de criar as páginas (Parent).
    # Estratégia: criamos placeholders e corrigimos depois é complexo;
    # em vez disso, calculamos os números: Pages será o próximo objeto após
    # todos os conteúdos e páginas. Mais simples: criar Pages por último e
    # referenciar seu número calculado.
    n_pages = len(doc.pages)
    # content streams
    for ops in doc.pages:
        stream = ("\n".join(ops)).encode('latin-1', 'replace')
        comp = zlib.compress(stream, 9)
        body = (b"<< /Filter /FlateDecode /Length " + str(len(comp)).encode() +
                b" >>\nstream\n" + comp + b"\nendstream")
        content_obj_nums.append(add(body))

    # número do objeto Pages (criado depois das páginas)
    pages_obj_num = len(objects) + n_pages + 1

    # page dicts
    for i, ops in enumerate(doc.pages):
        res_fonts = (f"/F1 {f1} 0 R /F2 {f2} 0 R /F3 {f3} 0 R")
        xobjs = ""
        if doc.images:
            parts = " ".join(f"/{nm} {img_obj[nm]} 0 R" for (nm, *_r) in doc.images)
            xobjs = f" /XObject << {parts} >>"
        body = (
            f"<< /Type /Page /Parent {pages_obj_num} 0 R "
            f"/MediaBox [0 0 {PAGE_W:.2f} {PAGE_H:.2f}] "
            f"/Resources << /Font << {res_fonts} >>{xobjs} >> "
            f"/Contents {content_obj_nums[i]} 0 R >>"
        ).encode('latin-1')
        page_obj_nums.append(add(body))

    # Pages
    kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
    pages_body = (f"<< /Type /Pages /Count {n_pages} /Kids [ {kids} ] >>").encode()
    assert add(pages_body) == pages_obj_num, "numeracao do Pages divergiu"

    # Catalog
    catalog = add(f"<< /Type /Catalog /Pages {pages_obj_num} 0 R >>".encode())

    # Monta o arquivo com tabela xref
    out = bytearray()
    out += b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0] * (len(objects) + 1)
    for num in range(1, len(objects) + 1):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode()
        out += objects[num - 1]
        out += b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects)+1}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, len(objects) + 1):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += b"trailer\n"
    out += f"<< /Size {len(objects)+1} /Root {catalog} 0 R >>\n".encode()
    out += b"startxref\n"
    out += f"{xref_pos}\n".encode()
    out += b"%%EOF\n"

    with open(out_path, 'wb') as f:
        f.write(out)
    return len(out)


if __name__ == "__main__":
    import os
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    doc = build()
    size = write_pdf(doc, "evidencias/relatorio_parte3_abnt.pdf")
    print(f"PDF gerado: evidencias/relatorio_parte3_abnt.pdf  ({size} bytes, "
          f"{len(doc.pages)} páginas)")
