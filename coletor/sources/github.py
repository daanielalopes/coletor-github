"""
Fonte GITHUB — CRAWLER de HTML (sem API).

Baixa as páginas HTML públicas de github.com e extrai os dados fazendo o
parsing do DOM. Escala via particionamento por nº EXATO de estrelas: para
cada valor S, a consulta é `stars:S`; cada partição cabe no limite navegável
da busca e a soma de milhares de partições cobre 50k+ repositórios.
"""

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from ._util import clean_text, parse_compact_number
from .base import Source


class GitHubSource(Source):
    name = "github"
    site_base = "https://github.com"

    # Rotas de topo do github.com que NÃO são donos de repositório.
    _RESERVED = {
        "search", "marketplace", "sponsors", "topics", "collections",
        "trending", "features", "about", "pricing", "login", "join",
        "settings", "notifications", "explore", "orgs", "apps", "issues",
        "pulls", "codespaces", "new", "contact", "site", "customer-stories",
    }

    # ---------------- Fronteira ----------------
    def build_partitions(self, cfg) -> List[Tuple[str, str, int]]:
        parts = []
        for s in range(cfg.star_max, cfg.star_min - 1, -1):
            parts.append((f"gh:stars={s}", f"stars:{s}", 1))
        return parts

    # ---------------- Listagem ----------------
    def listing_request(self, cfg, query: str, page: int
                        ) -> Tuple[str, Optional[dict]]:
        url = f"{self.site_base}/search"
        params = {
            "q": query,
            "type": "repositories",
            "s": "stars",
            "o": "desc",
            "per_page": cfg.per_page,
            "p": page,
        }
        return url, params

    def parse_listing(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        found: List[str] = []
        seen = set()

        candidates = soup.select(
            'a[href^="/"].v-align-middle, '
            'div.search-title a[href^="/"], '
            'a.prc-Link-Link-85e08, '
            'h3 a[href^="/"], '
            '[data-testid="results-list"] a[href^="/"]'
        )
        if not candidates:
            candidates = soup.select('a[href^="/"]')

        for a in candidates:
            href = a.get("href", "").split("?", 1)[0].split("#", 1)[0]
            parts = [p for p in href.strip("/").split("/") if p]
            if len(parts) != 2:
                continue
            owner, repo = parts
            if owner.lower() in self._RESERVED:
                continue
            full = f"{owner}/{repo}"
            if full in seen:
                continue
            seen.add(full)
            found.append(full)
        return found

    # ---------------- Detalhe ----------------
    def detail_url(self, item_id: str) -> str:
        return f"{self.site_base}/{item_id}"

    def parse_detail(self, item_id: str, html: str) -> Dict:
        soup = BeautifulSoup(html, "html.parser")
        owner_login, _, name = item_id.partition("/")

        repo: Dict = {
            "full_name": item_id,
            "source": self.name,
            "name": name,
            "owner_login": owner_login,
            "description": None,
            "language": None,
            "topics": [],
            "stars": None,
            "forks": None,
            "watchers": None,
            "open_issues": None,
            "size_kb": None,
            "license_name": None,
            "default_branch": None,
            "homepage": None,
            "html_url": f"{self.site_base}/{item_id}",
            "is_fork": None,
            "created_at": None,
            "updated_at": None,
            "pushed_at": None,
        }

        about = soup.select_one('p.f4.my-3, [data-testid="about-description"]')
        if about:
            repo["description"] = clean_text(about.get_text())
        if not repo["description"]:
            og = soup.find("meta", attrs={"property": "og:description"})
            if og and og.get("content"):
                desc = og["content"].split(". Contribute to", 1)[0]
                repo["description"] = clean_text(desc)

        star_el = soup.select_one(
            '#repo-stars-counter-star, a[href$="/stargazers"] strong, '
            'a[href$="/stargazers"] .Counter'
        )
        if star_el:
            repo["stars"] = parse_compact_number(
                star_el.get("title") or star_el.get_text())

        fork_el = soup.select_one(
            '#repo-network-counter, a[href$="/forks"] strong, '
            'a[href$="/forks"] .Counter'
        )
        if fork_el:
            repo["forks"] = parse_compact_number(
                fork_el.get("title") or fork_el.get_text())

        watch_el = soup.select_one(
            'a[href$="/watchers"] strong, a[href$="/watchers"] .Counter')
        if watch_el:
            repo["watchers"] = parse_compact_number(
                watch_el.get("title") or watch_el.get_text())

        issues_el = soup.select_one('#issues-repo-tab-count')
        if issues_el:
            repo["open_issues"] = parse_compact_number(
                issues_el.get("title") or issues_el.get_text())

        lang_el = soup.select_one(
            'span[itemprop="programmingLanguage"], a[href*="/search?l="] span')
        if lang_el:
            repo["language"] = clean_text(lang_el.get_text())

        topics = []
        for t in soup.select('a.topic-tag, a[data-ga-click*="topic"]'):
            txt = clean_text(t.get_text())
            if txt and txt not in topics:
                topics.append(txt)
        repo["topics"] = topics

        lic_el = soup.select_one('a[href$="#license"], a[href$="/LICENSE"]')
        if lic_el:
            lic_txt = clean_text(lic_el.get_text())
            if lic_txt:
                repo["license_name"] = lic_txt.replace("License", "").strip() \
                    or lic_txt

        home_el = soup.select_one(
            'a[role="link"][href^="http"].text-bold, '
            '[data-testid="repository-homepage"] a')
        if home_el and home_el.get("href", "").startswith("http"):
            repo["homepage"] = home_el["href"]

        branch_el = soup.select_one(
            '#branch-picker-repos-header-ref-selector span.css-truncate-target')
        if branch_el:
            repo["default_branch"] = clean_text(branch_el.get_text())

        repo["is_fork"] = bool(soup.find(string=re.compile(r"forked from", re.I)))
        return repo

    def parse_readme(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "html.parser")
        article = soup.select_one(
            'article.markdown-body, [data-testid="readme"] article, '
            'div#readme article')
        if not article:
            return None
        text = article.get_text("\n").strip()
        return text or None

    def parse_owner(self, item_id: str, detail: Dict) -> Dict:
        owner_login, _, _ = item_id.partition("/")
        return {
            "login": owner_login,
            "type": None,
            "html_url": f"{self.site_base}/{owner_login}",
            "avatar_url": f"{self.site_base}/{owner_login}.png",
        }
