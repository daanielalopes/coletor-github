"""
Fonte GITHUB_API — coletor baseado na API REST oficial do GitHub.

Esta fonte é MANTIDA (o trabalho tem tanto o crawler de HTML quanto o coletor
por API). Diferente das demais, ela consome JSON estruturado de
`api.github.com` (uses_api = True), portanto não faz parsing de HTML.

Escala: mesma estratégia de particionamento por nº EXATO de estrelas
(`stars:S`), contornando o teto de 1.000 resultados por consulta da Search API.

Token: lido de GITHUB_TOKEN (env ou .env). Sem token, o limite é de 60 req/h;
com token, 5.000 req/h. O crawler de HTML (fontes github_html/sourceforge) NÃO
precisa de token — este módulo é a alternativa por API.
"""

import os
from typing import Dict, List, Optional, Tuple

from .base import Source


def _load_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    for path in (".env", os.path.join(os.path.dirname(__file__),
                                      "..", "..", ".env")):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GITHUB_TOKEN") and "=" in line:
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except FileNotFoundError:
            continue
    return ""


class GitHubApiSource(Source):
    name = "github_api"
    site_base = "https://api.github.com"
    uses_api = True

    def __init__(self):
        self.token = _load_token()

    # ---------------- Fronteira ----------------
    def build_partitions(self, cfg) -> List[Tuple[str, str, int]]:
        parts = []
        for s in range(cfg.star_max, cfg.star_min - 1, -1):
            parts.append((f"api:stars={s}", f"stars:{s}", 1))
        return parts

    # ---------------- Listagem (Search API) ----------------
    def listing_request(self, cfg, query: str, page: int
                        ) -> Tuple[str, Optional[dict]]:
        url = f"{self.site_base}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(cfg.per_page, 100),
            "page": page,
        }
        return url, params

    def parse_listing_json(self, data: Dict) -> List[Dict]:
        """A API já devolve os itens completos; retornamos os objetos brutos."""
        return data.get("items", []) or []

    # ---------------- Detalhe ----------------
    def parse_detail_json(self, item: Dict) -> Dict:
        owner = item.get("owner") or {}
        lic = item.get("license") or {}
        return {
            "full_name": item.get("full_name"),
            "source": self.name,
            "name": item.get("name"),
            "owner_login": owner.get("login"),
            "description": item.get("description"),
            "language": item.get("language"),
            "topics": item.get("topics", []) or [],
            "stars": item.get("stargazers_count"),
            "forks": item.get("forks_count"),
            "watchers": item.get("watchers_count"),
            "open_issues": item.get("open_issues_count"),
            "size_kb": item.get("size"),
            "license_name": lic.get("name"),
            "default_branch": item.get("default_branch"),
            "homepage": item.get("homepage"),
            "html_url": item.get("html_url"),
            "is_fork": item.get("fork"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "pushed_at": item.get("pushed_at"),
        }

    def parse_owner_json(self, item: Dict) -> Dict:
        owner = item.get("owner") or {}
        return {
            "login": owner.get("login"),
            "type": owner.get("type"),
            "html_url": owner.get("html_url"),
            "avatar_url": owner.get("avatar_url"),
        }
