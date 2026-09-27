"""
Parser / extrator de conteúdo.

Duas responsabilidades:
  1. extract_film_links / extract_next_list_page: descoberta de URLs
     (usadas pelo crawler para expandir a fronteira a partir das listagens).
  2. parse_film: extração dos metadados de UMA página de filme.

Estratégia de extração de metadados: o Letterboxd embute um bloco
JSON-LD (schema.org/Movie) em <script type="application/ld+json">. Ele é
a fonte mais estável e estruturada. Usamos o HTML como fallback para os
campos que não estão no JSON-LD (sinopse, tagline, duração).
"""

import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# /film/{slug}/ e possíveis sufixos (crew, genres...). Capturamos a raiz.
_FILM_HREF_RE = re.compile(r"^/film/([^/]+)/?$")


# Preferimos o parser 'lxml' (rápido e tolerante). Caso não esteja
# instalado, caímos para o 'html.parser' embutido na biblioteca padrão,
# de modo que o coletor funcione sem dependências binárias adicionais.
try:
    import lxml  # noqa: F401
    _PARSER = "lxml"
except ImportError:  # pragma: no cover
    _PARSER = "html.parser"


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, _PARSER)


def canonical_film_url(base_url: str, href: str) -> Optional[str]:
    """Normaliza um href em uma URL canônica de filme, ou None."""
    path = urlparse(href).path
    m = _FILM_HREF_RE.match(path)
    if not m:
        return None
    slug = m.group(1)
    return urljoin(base_url, f"/film/{slug}/")


def slug_from_url(url: str) -> Optional[str]:
    m = re.search(r"/film/([^/]+)/?", urlparse(url).path)
    return m.group(1) if m else None


def extract_film_links(html: str, base_url: str) -> List[str]:
    """Extrai todas as URLs canônicas de filme presentes numa página."""
    soup = _soup(html)
    urls = set()

    # Nas listagens, cada poster costuma ter data-film-slug / data-target-link.
    for el in soup.select("[data-film-slug], [data-target-link]"):
        slug = el.get("data-film-slug")
        if slug:
            urls.add(urljoin(base_url, f"/film/{slug}/"))
        target = el.get("data-target-link")
        if target:
            cu = canonical_film_url(base_url, target)
            if cu:
                urls.add(cu)

    # Fallback: qualquer <a href="/film/...">.
    for a in soup.find_all("a", href=True):
        cu = canonical_film_url(base_url, a["href"])
        if cu:
            urls.add(cu)

    return list(urls)


def extract_next_list_page(html: str, current_url: str, base_url: str
                           ) -> Optional[str]:
    """Descobre a URL da PRÓXIMA página de uma listagem paginada."""
    soup = _soup(html)

    # Link explícito de "próxima página".
    nxt = soup.select_one("a.next")
    if nxt and nxt.get("href"):
        return urljoin(base_url, nxt["href"])

    # Fallback: incrementar /page/N/ na própria URL.
    m = re.search(r"/page/(\d+)/?$", current_url)
    if m:
        n = int(m.group(1)) + 1
        return re.sub(r"/page/\d+/?$", f"/page/{n}/", current_url)
    # Primeira página sem sufixo -> /page/2/
    if not current_url.rstrip("/").endswith("/page"):
        return current_url.rstrip("/") + "/page/2/"
    return None


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def parse_film(html: str, url: str) -> Optional[Dict]:
    """Extrai os metadados de uma página de filme. Retorna dict ou None."""
    soup = _soup(html)
    data: Dict = {"url": url, "slug": slug_from_url(url)}

    # ---------- 1) JSON-LD (schema.org/Movie) ----------
    ld = _extract_jsonld_movie(soup)
    if ld:
        data["title"] = ld.get("name")
        data["poster_url"] = ld.get("image")

        directors = ld.get("director")
        if directors:
            if isinstance(directors, list):
                data["director"] = ", ".join(
                    d.get("name", "") for d in directors if isinstance(d, dict)
                ).strip(", ")
            elif isinstance(directors, dict):
                data["director"] = directors.get("name")

        actors = ld.get("actors") or []
        if isinstance(actors, dict):
            actors = [actors]
        data["cast"] = [a.get("name") for a in actors
                        if isinstance(a, dict) and a.get("name")]

        genres = ld.get("genre")
        if genres:
            data["genres"] = genres if isinstance(genres, list) else [genres]

        countries = ld.get("countryOfOrigin")
        if countries:
            if isinstance(countries, dict):
                countries = [countries]
            data["countries"] = [
                c.get("name") for c in countries
                if isinstance(c, dict) and c.get("name")
            ] if isinstance(countries, list) else []

        agg = ld.get("aggregateRating")
        if isinstance(agg, dict):
            data["rating_avg"] = _to_float(agg.get("ratingValue"))
            data["rating_count"] = _to_int(agg.get("ratingCount"))

        date_published = ld.get("datePublished") or ""
        ym = re.match(r"(\d{4})", str(date_published))
        if ym:
            data["year"] = int(ym.group(1))

    # ---------- 2) Fallbacks no HTML ----------
    if not data.get("title"):
        h1 = soup.select_one("h1.headline-1, h1.filmtitle, section.film-header h1")
        if h1:
            data["title"] = h1.get_text(strip=True)

    if not data.get("year"):
        yr = soup.select_one("a[href*='/films/year/'], small.number a")
        if yr:
            m = re.search(r"(\d{4})", yr.get_text())
            if m:
                data["year"] = int(m.group(1))

    # Sinopse (o texto principal do documento p/ o RI).
    synopsis = None
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        synopsis = meta_desc["content"].strip()
    if not synopsis:
        div = soup.select_one("div.truncate, div.review div, section.film-header + div")
        if div:
            synopsis = div.get_text(" ", strip=True)
    data["synopsis"] = synopsis

    # Tagline
    tag = soup.select_one("h4.tagline, .tagline")
    if tag:
        data["tagline"] = tag.get_text(strip=True)

    # Duração (runtime) — normalmente em texto tipo "104 mins".
    footer_text = soup.get_text(" ", strip=True)
    rt = re.search(r"(\d{1,4})\s*mins", footer_text)
    if rt:
        data["runtime_min"] = int(rt.group(1))

    # Idiomas (via links de details).
    langs = [a.get_text(strip=True)
             for a in soup.select("a[href*='/films/language/']")]
    if langs:
        data["languages"] = sorted(set(langs))

    # Se não conseguimos nem título, considera falha de parsing.
    if not data.get("title"):
        logger.debug("Sem título extraível: %s", url)
        return None

    return data


def _extract_jsonld_movie(soup: BeautifulSoup) -> Optional[Dict]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        # O Letterboxd às vezes envolve o JSON em comentários CDATA.
        raw = raw.strip()
        raw = re.sub(r"^/\*.*?\*/", "", raw, flags=re.DOTALL).strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        candidates = obj if isinstance(obj, list) else [obj]
        for c in candidates:
            if isinstance(c, dict) and c.get("@type") in ("Movie", "Film"):
                return c
    return None


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None
