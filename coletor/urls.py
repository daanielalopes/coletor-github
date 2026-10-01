"""
Normalização de URLs e política de seleção de links.

Toda URL encontrada numa página passa por aqui antes de entrar na fila:
  1. normalize(): coloca a URL numa forma canônica, para que a mesma página
     não seja coletada duas vezes com endereços diferentes;
  2. classify(): aplica as regex de cada site e diz o tipo da página
     ('project', 'listing' ou 'sitemap'), ou None se o link deve ser
     descartado.

Só entram na fila páginas de dois sites: github.com e sourceforge.net.
"""

import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

GITHUB = "github"
SOURCEFORGE = "sourceforge"

HOSTS = {
    "github.com": GITHUB,
    "sourceforge.net": SOURCEFORGE,
}

# Parâmetros usados só para rastrear cliques. Não mudam o conteúdo da página.
TRACKING_PARAMS = {
    "ref", "ref_cta", "ref_loc", "ref_page", "ref_type", "source",
    "referrer", "fbclid", "gclid", "mc_cid", "mc_eid", "_ga",
}

# O GitHub serve no máximo 50 páginas por tópico (a página 51 devolve 404).
GITHUB_MAX_TOPIC_PAGE = 50

# Primeiros segmentos de caminho que o GitHub usa para páginas próprias.
# Ex.: /sponsors/fulano e /features/copilot têm o formato /x/y, mas não são
# repositórios. Nenhum usuário do GitHub pode ter esses nomes.
GITHUB_RESERVED = {
    "about", "account", "accelerator", "advisories", "apps", "auth", "blog",
    "business", "codespaces", "collections", "contact", "contact-sales",
    "copilot", "customer-stories", "dashboard", "discussions", "education",
    "enterprise", "enterprises", "events", "explore", "features", "gist",
    "git-guides", "github-copilot", "home", "issues", "join", "login",
    "logout", "maintenance", "marketplace", "mcp", "models", "new",
    "newsroom", "nonprofit", "notifications", "open-source", "organizations",
    "orgs", "packages", "partners", "password_reset", "premium-support",
    "pricing", "pulls", "readme", "redeem", "resources", "search",
    "security", "sessions", "settings", "shop", "signup", "site",
    "solutions", "spark", "sponsors", "stars", "status", "support", "team",
    "teams", "topics", "trending", "trust-center", "users", "watching",
    "why-github",
}

RE_GH_TOPIC = re.compile(r"^/topics(?:/[a-z0-9][a-z0-9-]*)?$")
RE_GH_REPO = re.compile(r"^/([a-z0-9][a-z0-9-]*)/([a-z0-9._-]+)$")

RE_SF_PROJECT = re.compile(r"^/projects/([a-z0-9][a-z0-9._-]*)/$")
RE_SF_DIRECTORY = re.compile(r"^/directory/(?:[a-z0-9][a-z0-9._:+-]*/)*$")
RE_SF_SITEMAP = re.compile(r"^/(?:sitemap|directory_sitemap)(?:-\d+)?\.xml$")


def site_of(url: str) -> Optional[str]:
    """Diz de qual site é a URL (já normalizada), ou None."""
    return HOSTS.get(urlsplit(url).netloc)


def normalize(url: str, base: Optional[str] = None) -> Optional[str]:
    """
    Devolve a forma canônica da URL, ou None se ela não for http(s).

    - resolve links relativos a partir da página de origem;
    - https, host em minúsculas, sem "www." e sem porta;
    - remove o fragmento (#...);
    - remove parâmetros de rastreio e "page=1" (é a mesma página sem o
      parâmetro) e ordena os parâmetros que sobram;
    - barra final: cada site tem a sua forma canônica. O GitHub usa caminhos
      sem barra no fim; o SourceForge redireciona /projects/nome para
      /projects/nome/, então lá a barra final é sempre colocada;
    - no GitHub o caminho vai para minúsculas, porque o site ignora
      maiúsculas em nomes de dono e de repositório (/PSF/Requests e
      /psf/requests são a mesma página).
    """
    if not url:
        return None
    url = url.strip()
    if base:
        url = urljoin(base, url)
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None

    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None

    # Parâmetro repetido (?page=2&page=3): vale o último valor, como fazem os
    # servidores. Sem isso, cada repetição viraria uma "página nova".
    params = {}
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key in TRACKING_PARAMS or key.startswith("utm_"):
            continue
        params[key] = value
    if params.get("page") == "1":
        del params["page"]
    query = urlencode(sorted(params.items()))

    path = parts.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    site = HOSTS.get(host)
    if site == GITHUB:
        path = path.lower()
        if len(path) > 1:
            path = path.rstrip("/")
    elif site == SOURCEFORGE:
        last = path.rsplit("/", 1)[-1]
        if not path.endswith("/") and "." not in last:
            path += "/"

    return urlunsplit(("https", host, path, query, ""))


def _query(url: str) -> dict:
    return dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))


def _page_ok(query: dict, max_page: Optional[int] = None) -> bool:
    """Aceita no máximo o parâmetro page, com número válido."""
    if set(query) - {"page"}:
        return False
    if "page" in query:
        if not query["page"].isdigit():
            return False
        page = int(query["page"])
        if page < 2 or (max_page is not None and page > max_page):
            return False
    return True


def classify(url: str) -> Optional[str]:
    """
    Política de seleção de links (URL já normalizada).

    GitHub
      - 'listing': páginas de tópico, /topics e /topics/nome, com no máximo
        o parâmetro ?page=N (N <= 50);
      - 'project': raiz de repositório, /dono/repo, sem nada depois e sem
        parâmetros. Login, issues, pulls, commits, tree, blob, search,
        settings, marketplace etc. ficam de fora porque não casam com a regex
        ou porque o primeiro segmento é reservado.
    SourceForge
      - 'project': raiz do projeto, /projects/nome/;
      - 'listing': /directory/... com no máximo o parâmetro ?page=N;
      - 'sitemap': os sitemaps de projetos e do diretório. Downloads, files,
        reviews, rss e auth ficam de fora porque não casam com nenhuma regex.
    """
    parts = urlsplit(url)
    site = HOSTS.get(parts.netloc)
    path = parts.path
    query = _query(url)

    if site == GITHUB:
        if RE_GH_TOPIC.match(path):
            return "listing" if _page_ok(query, GITHUB_MAX_TOPIC_PAGE) else None
        m = RE_GH_REPO.match(path)
        if m and not query:
            owner, repo = m.groups()
            if owner in GITHUB_RESERVED or repo.endswith(".git"):
                return None
            if repo in (".", ".."):
                return None
            return "project"
        return None

    if site == SOURCEFORGE:
        if RE_SF_PROJECT.match(path):
            return "project" if not query else None
        if RE_SF_DIRECTORY.match(path):
            return "listing" if _page_ok(query) else None
        if RE_SF_SITEMAP.match(path):
            return "sitemap" if not query else None
        return None

    return None


def is_pagination(src: str, dst: str) -> bool:
    """True se dst é outra página da mesma listagem de src (muda só o page)."""
    a, b = urlsplit(src), urlsplit(dst)
    if (a.netloc, a.path) != (b.netloc, b.path):
        return False
    qa, qb = _query(src), _query(dst)
    qa.pop("page", None)
    qb.pop("page", None)
    return qa == qb
