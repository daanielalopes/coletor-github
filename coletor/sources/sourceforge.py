"""
Fonte SOURCEFORGE — CRAWLER de HTML (segunda fonte de conteúdo).

Assim como no GitHub HTML, aqui NÃO há API: baixamos as páginas públicas do
site sourceforge.net e extraímos os dados fazendo o parsing do DOM.

Documento: um PROJETO do SourceForge (análogo a um repositório). O
"proprietário" é o próprio projeto/mantenedor.

ESCALA: o diretório do SourceForge (/directory/) é paginado (?page=N) e pode
ser segmentado por diversas facetas (sistema operacional, categoria, etc.).
Particionamos por FACETA para gerar muitas listagens disjuntas e, somando as
páginas de cada faceta, superar 50 mil projetos.
"""

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from ._util import clean_text, parse_compact_number
from .base import Source


class SourceForgeSource(Source):
    name = "sourceforge"
    site_base = "https://sourceforge.net"

    # Facetas de sistema operacional usadas para particionar o diretório.
    # Cada uma é uma listagem disjunta e paginável -> ajuda na escala.
    _OS_FACETS = [
        "windows", "mac", "linux", "bsd", "solaris", "android",
        "cross-platform-1", "os-portable", "handhelds", "modern_oses",
    ]
    # Facetas de categoria (tópico) — ampliam ainda mais a cobertura.
    _CATEGORY_FACETS = [
        "development", "internet", "system", "multimedia", "games",
        "science-engineering", "business", "education", "communications",
        "security-utilities", "audiovideo", "graphics", "office",
        "database", "networking", "text-editors", "desktop", "religion",
        "formats-and-protocols", "terminals", "printing", "mobile",
    ]

    # ---------------- Fronteira ----------------
    def build_partitions(self, cfg) -> List[Tuple[str, str, int]]:
        """
        Gera partições (seeds do diretório) por faceta de SO e de categoria.
        `query` codifica o tipo/valor da faceta: 'os:<valor>' ou 'cat:<valor>'.
        """
        parts: List[Tuple[str, str, int]] = []
        for os_name in self._OS_FACETS:
            parts.append((f"sf:os={os_name}", f"os:{os_name}", 1))
        for cat in self._CATEGORY_FACETS:
            parts.append((f"sf:cat={cat}", f"cat:{cat}", 1))
        return parts

    # ---------------- Listagem (diretório) ----------------
    def listing_request(self, cfg, query: str, page: int
                        ) -> Tuple[str, Optional[dict]]:
        kind, _, value = query.partition(":")
        if kind == "os":
            url = f"{self.site_base}/directory/os:{value}/"
        elif kind == "cat":
            url = f"{self.site_base}/directory/{value}/"
        else:
            url = f"{self.site_base}/directory/"
        # O diretório do SourceForge pagina por ?page=N e ordena por popular.
        params = {"sort": "popular", "page": page}
        return url, params

    def parse_listing(self, html: str) -> List[str]:
        """
        Extrai os SLUGS de projeto (identificador em /projects/<slug>/) da
        página de diretório. Robustez: procuramos qualquer link para
        '/projects/<slug>/' e deduplicamos.
        """
        soup = BeautifulSoup(html, "html.parser")
        found: List[str] = []
        seen = set()

        for a in soup.select('a[href*="/projects/"]'):
            href = a.get("href", "")
            m = re.search(r"/projects/([^/?#]+)/?", href)
            if not m:
                continue
            slug = m.group(1)
            # ignora rotas utilitárias que não são projetos
            if slug in {"", "add", "search"}:
                continue
            if slug in seen:
                continue
            seen.add(slug)
            found.append(slug)
        return found

    # ---------------- Detalhe (página do projeto) ----------------
    def detail_url(self, item_id: str) -> str:
        return f"{self.site_base}/projects/{item_id}/"

    def parse_detail(self, item_id: str, html: str) -> Dict:
        soup = BeautifulSoup(html, "html.parser")

        repo: Dict = {
            "full_name": f"sourceforge/{item_id}",
            "source": self.name,
            "name": item_id,
            "owner_login": "sourceforge",
            "description": None,
            "language": None,
            "topics": [],
            "stars": None,          # SourceForge não tem "stars"; usamos rating/downloads
            "forks": None,
            "watchers": None,
            "open_issues": None,
            "size_kb": None,
            "license_name": None,
            "default_branch": None,
            "homepage": None,
            "html_url": f"{self.site_base}/projects/{item_id}/",
            "is_fork": False,
            "created_at": None,
            "updated_at": None,
            "pushed_at": None,
        }

        # ---- Nome legível (título da página do projeto) ----
        title = soup.select_one('h1, header h1, .project-title')
        if title:
            nm = clean_text(title.get_text())
            if nm:
                repo["name"] = nm

        # ---- Descrição ----
        about = soup.select_one(
            'meta[name="description"], meta[property="og:description"]')
        if about and about.get("content"):
            repo["description"] = clean_text(about["content"])
        if not repo["description"]:
            p = soup.select_one('.description, [itemprop="description"], p.summary')
            if p:
                repo["description"] = clean_text(p.get_text())

        # ---- Categorias/tópicos e SO -> topics ----
        topics: List[str] = []
        for a in soup.select(
                'a[href*="/directory/os:"], a[href*="/directory/"] , '
                '.categories a, [itemprop="applicationCategory"]'):
            href = a.get("href", "")
            if "/directory/" not in href:
                continue
            txt = clean_text(a.get_text())
            if txt and len(txt) < 40 and txt not in topics:
                topics.append(txt)
        repo["topics"] = topics[:20]

        # ---- Linguagem (quando exposta como "Programming Language") ----
        lang_label = soup.find(string=re.compile(r"Programming Language", re.I))
        if lang_label and lang_label.parent:
            sib = lang_label.parent.find_next(["a", "span", "td"])
            if sib:
                repo["language"] = clean_text(sib.get_text())

        # ---- License ----
        lic_label = soup.find(string=re.compile(r"License", re.I))
        if lic_label and lic_label.parent:
            sib = lic_label.parent.find_next(["a", "span", "td"])
            if sib:
                lic = clean_text(sib.get_text())
                if lic and len(lic) < 80:
                    repo["license_name"] = lic

        # ---- Downloads (usamos como sinal de popularidade, em watchers) ----
        dl = soup.select_one(
            '[title*="Downloads"], .downloads, #downloads-count, '
            'a[href$="/files/stats/timeline"]')
        if dl:
            repo["watchers"] = parse_compact_number(
                dl.get("title") or dl.get_text())

        # ---- Homepage (link externo do projeto) ----
        home = soup.select_one('a.homepage, a[href^="http"][rel*="nofollow"]')
        if home and home.get("href", "").startswith("http") \
                and "sourceforge.net" not in home["href"]:
            repo["homepage"] = home["href"]

        return repo

    def parse_readme(self, html: str) -> Optional[str]:
        """
        Texto rico do projeto: a seção de descrição longa / conteúdo principal
        da página do projeto no SourceForge.
        """
        soup = BeautifulSoup(html, "html.parser")
        node = soup.select_one(
            '#content_base, .project-description, [itemprop="description"], '
            'section.description, #description')
        if not node:
            # fallback: og:description já é um bom resumo textual
            og = soup.select_one('meta[property="og:description"]')
            if og and og.get("content"):
                return clean_text(og["content"])
            return None
        text = node.get_text("\n").strip()
        return text or None

    def parse_owner(self, item_id: str, detail: Dict) -> Dict:
        return {
            "login": "sourceforge",
            "type": "Organization",
            "html_url": self.site_base,
            "avatar_url": None,
        }
