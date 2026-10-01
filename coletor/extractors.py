"""
Extração de links e de campos a partir do HTML baixado.

Os seletores foram escolhidos inspecionando páginas reais de cada tipo.
Sempre que possível eles se apoiam em marcações estáveis (ids, atributos
itemprop, metatags e títulos de seção) e não nas classes CSS geradas
automaticamente, que mudam a cada nova versão do site.

Os extratores de projeto devolvem None quando a página não tem as marcas de
uma página de projeto. Isso detecta páginas de erro servidas com código 200
(soft-404) e páginas do site que só parecem um projeto pela URL.
"""

import hashlib
import html as htmllib
import re
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

from .urls import normalize

RE_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
RE_NUMBER = re.compile(r"[\d.,]+\s*[kKmM]?")


def parse_html(content: bytes, encoding: Optional[str]) -> BeautifulSoup:
    text = content.decode(encoding or "utf-8", errors="replace")
    return BeautifulSoup(text, "lxml")


def clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def to_int(text: Optional[str]) -> Optional[int]:
    """Converte '54,368', '11.5k' ou '1.2m' em inteiro."""
    if not text:
        return None
    m = RE_NUMBER.search(text)
    if not m:
        return None
    raw = m.group(0).replace(" ", "").lower()
    mult = 1
    if raw.endswith("k"):
        mult, raw = 1000, raw[:-1]
    elif raw.endswith("m"):
        mult, raw = 1000000, raw[:-1]
    if mult == 1:
        raw = raw.replace(",", "").replace(".", "")
        return int(raw) if raw.isdigit() else None
    try:
        return int(float(raw.replace(",", "")) * mult)
    except ValueError:
        return None


def content_hash(*parts: Optional[str]) -> Optional[str]:
    """Hash do texto principal, usado para achar páginas duplicadas."""
    text = " ".join(p for p in parts if p)
    if len(text) < 200:
        # Texto curto demais: projetos diferentes podem coincidir por acaso.
        return None
    return hashlib.sha1(text.lower().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- links
def extract_links(soup: BeautifulSoup, base_url: str) -> List[str]:
    """Todos os links da página, já normalizados e sem repetição."""
    found = []
    for a in soup.find_all("a", href=True):
        found.append(a["href"])
    for link in soup.find_all("link", rel="next", href=True):
        found.append(link["href"])
    # Paginação do GitHub: o botão "Load more" é um formulário GET com um
    # campo escondido page=N. Montamos a URL que o formulário enviaria.
    for form in soup.find_all("form"):
        if (form.get("method") or "get").lower() != "get":
            continue
        page = form.find("input", attrs={"name": "page"})
        if page and page.get("value") and form.get("action"):
            sep = "&" if "?" in form["action"] else "?"
            found.append(f"{form['action']}{sep}page={page['value']}")

    out, seen = [], set()
    for href in found:
        url = normalize(href, base_url)
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def extract_sitemap_links(content: bytes) -> List[str]:
    """URLs listadas num sitemap XML (índice de sitemaps ou urlset)."""
    text = content.decode("utf-8", errors="replace")
    out = []
    for loc in RE_LOC.findall(text):
        url = normalize(htmllib.unescape(loc))
        if url:
            out.append(url)
    return out


# ---------------------------------------------------------------- GitHub
def extract_github_cards(soup: BeautifulSoup, base_url: str) -> Dict[str, Dict]:
    """
    Pistas tiradas dos cartões de repositório de uma página de tópico.

    A página do repositório carrega a barra de linguagens depois, via
    JavaScript, então a linguagem principal não vem no HTML dela. O cartão
    do repositório na página de tópico traz essa informação
    (itemprop="programmingLanguage"). Guardamos a pista e usamos quando a
    página do repositório for coletada.
    """
    hints = {}
    for art in soup.find_all("article"):
        h3 = art.find("h3")
        if not h3:
            continue
        links = h3.find_all("a", href=True)
        if not links:
            continue
        url = normalize(links[-1]["href"], base_url)
        lang = art.find(attrs={"itemprop": "programmingLanguage"})
        if url and lang:
            hints[url] = {"linguagem": clean(lang.get_text())}
    return hints


def _section(soup: BeautifulSoup, title: str):
    """Bloco da barra lateral cujo título (h2) é `title`."""
    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True) == title:
            return h2.parent
    return None


def extract_github_repo(soup: BeautifulSoup, url: str,
                        hint: Optional[Dict] = None,
                        readme_max_chars: int = 100000) -> Optional[Dict]:
    meta = soup.find("meta", attrs={"name": "octolytics-dimension-repository_nwo"})
    if not meta or "/" not in (meta.get("content") or ""):
        return None  # não é página de repositório (soft-404)
    nwo = meta["content"].strip()
    owner, name = nwo.split("/", 1)

    about = _section(soup, "About")

    description = None
    if about:
        p = about.find("p")
        if p:
            description = clean(p.get_text())
    if not description:
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content"):
            text = re.sub(
                r"\s*Contribute to \S+ development by creating an account on GitHub\.?$",
                "", og["content"])
            description = clean(text)

    topics = []
    scope = about or soup
    for a in scope.find_all("a", href=re.compile(r"^/topics/")):
        t = clean(a.get_text())
        if t and t not in topics:
            topics.append(t)

    # O link da licença aponta para "#<nome>-1-ov-file" e tem o texto
    # "MIT license", "Apache-2.0 license" etc. Quando o GitHub acha um arquivo
    # de licença mas não reconhece o tipo, o texto é só "License" (ou
    # "View license"); nesse caso guardamos "Other".
    license_name = None
    for scope in (about, soup):  # reserva: o mesmo link aparece nas abas do README
        if scope is None or license_name:
            continue
        for a in scope.find_all("a"):
            text = clean(a.get_text()) or ""
            href = a.get("href") or ""
            if re.search(r"-\d+-ov-file$", href) or (scope is about and text.lower().endswith("license")):
                lic = re.sub(r"\s*license$", "", text, flags=re.I).strip()
                license_name = lic if lic and lic.lower() != "view" else "Other"
                break

    def counter(elem_id: str, word: str) -> Optional[int]:
        el = soup.find(id=elem_id)
        if el is not None:
            value = to_int(el.get("title")) if el.get("title") else None
            if value is None:
                value = to_int(el.get_text())
            if value is not None:
                return value
        if about:
            for strong in about.find_all("strong"):
                tail = strong.parent.get_text(" ", strip=True).lower()
                if word in tail:
                    return to_int(strong.get_text())
        return None

    stars = counter("repo-stars-counter-star", "star")
    forks = counter("repo-network-counter", "fork")

    language = None
    el = soup.find(attrs={"itemprop": "programmingLanguage"})
    if el:
        language = clean(el.get_text())
    if not language:
        langs = _section(soup, "Languages")
        if langs:
            first = langs.find("li")
            if first:
                span = first.find("span")
                language = clean(span.get_text()) if span else None
    if not language and hint:
        language = hint.get("linguagem")

    readme = None
    art = soup.find("article", class_="markdown-body")
    if art:
        readme = clean(art.get_text(" "))
        if readme and len(readme) > readme_max_chars:
            readme = readme[:readme_max_chars]

    return {
        "chave": nwo.lower(),
        "url": f"https://github.com/{nwo}",
        "nome": name,
        "dono": owner,
        "descricao": description,
        "topicos": topics,
        "linguagem": language,
        "estrelas": stars,
        "forks": forks,
        "licenca": license_name,
        "readme": readme,
        "hash_conteudo": content_hash(description, readme),
    }


# ---------------------------------------------------------------- SourceForge
def _project_info(soup: BeautifulSoup, title: str):
    """Seção "project-info" cujo título (h3/h4) é `title`."""
    for sec in soup.find_all("section", class_="project-info"):
        head = sec.find(["h3", "h4"])
        if head and head.get_text(strip=True) == title:
            return sec
    return None


def extract_sourceforge_project(soup: BeautifulSoup, url: str) -> Optional[Dict]:
    og_url = soup.find("meta", attrs={"property": "og:url"})
    canonical = normalize(og_url["content"]) if og_url and og_url.get("content") else None
    m = re.search(r"sourceforge\.net/projects/([^/]+)/$", canonical or "")
    h1 = soup.find("h1", attrs={"itemprop": "name"})
    if not m or not h1:
        return None  # não é página de projeto (soft-404)
    key = m.group(1)

    description = None
    el = soup.find(attrs={"itemprop": "description"})
    if el:
        description = clean(el.get_text(" "))
    if not description:
        md = soup.find("meta", attrs={"name": "description"})
        if md and md.get("content"):
            description = clean(md["content"])

    # O resumo é o h2.summary do cabeçalho. Os div.summary da página são
    # anúncios de outros produtos e não podem ser usados.
    summary = None
    el = soup.find("h2", class_="summary")
    if el:
        summary = clean(el.get_text())

    categories = []
    for span in soup.find_all(attrs={"itemprop": "applicationCategory"}):
        c = clean(span.get_text())
        if c and c not in categories:
            categories.append(c)

    license_name = None
    sec = _project_info(soup, "License")
    if sec:
        sec.find(["h3", "h4"]).extract()
        license_name = clean(sec.get_text(" "))

    language = None
    sec = _project_info(soup, "Programming Language")
    if sec:
        langs = [clean(a.get_text()) for a in sec.find_all("a")]
        language = ", ".join(x for x in langs if x) or None

    downloads = None
    last_update = None
    for box in soup.find_all(class_="as-h2"):
        label = box.find(class_="label")
        if not label:
            continue
        name = label.get_text(strip=True).lower()
        if name.startswith("downloads"):
            label.extract()
            downloads = to_int(box.get_text(" "))
        elif name.startswith("last update"):
            t = box.find("time")
            if t:
                last_update = t.get("datetime") or clean(t.get_text())

    rating = None
    rating_count = None
    agg = soup.find(attrs={"itemprop": "aggregateRating"})
    if agg:
        rv = agg.find(attrs={"itemprop": "ratingValue"})
        if rv:
            try:
                rating = float(rv.get("content") or rv.get_text(strip=True))
            except ValueError:
                rating = None
        rc = agg.find(attrs={"itemprop": "ratingCount"})
        if rc:
            rating_count = to_int(rc.get("content") or rc.get_text())

    return {
        "chave": key,
        "url": canonical,
        "nome": clean(h1.get_text()),
        "descricao": description,
        "resumo": summary,
        "categorias": categories,
        "licenca": license_name,
        "linguagem": language,
        "downloads_semana": downloads,
        "nota": rating,
        "num_avaliacoes": rating_count,
        "ultima_atualizacao": last_update,
        "hash_conteudo": content_hash(summary, description),
    }
