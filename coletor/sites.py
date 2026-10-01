"""
Seeds e endereço base de cada site coletado.

GitHub: a página /topics e as páginas dos tópicos populares, com a
paginação ?page=1..N. Cada página de tópico lista 20 repositórios ordenados
por estrelas, então as seeds levam direto aos projetos mais relevantes.

SourceForge: o diretório /directory/ e as suas categorias principais, com a
paginação ?page=1..N (25 projetos por página, ordenados por popularidade).
Os sitemaps listados no robots.txt do SourceForge entram na fila quando a
thread do site lê o robots.txt (ver crawler.SiteWorker).

As seeds são intercaladas por página: primeiro a página 1 de todos os
tópicos (ou categorias), depois a página 2 de todos, e assim por diante.
Assim a coleta cobre vários assuntos desde o início, em vez de esgotar um
tópico antes de começar o próximo.
"""

from typing import List

from .urls import GITHUB, SOURCEFORGE, normalize

BASE_URLS = {
    GITHUB: "https://github.com",
    SOURCEFORGE: "https://sourceforge.net",
}


def _paged(base: str, page: int) -> str:
    return base if page == 1 else f"{base}?page={page}"


def seed_urls(site: str, cfg) -> List[str]:
    urls = []
    if site == GITHUB:
        urls.append("https://github.com/topics")
        for page in range(1, cfg.github_seed_pages + 1):
            for topic in cfg.github_seed_topics:
                urls.append(_paged(f"https://github.com/topics/{topic}", page))
    elif site == SOURCEFORGE:
        for page in range(1, cfg.sourceforge_seed_pages + 1):
            urls.append(_paged("https://sourceforge.net/directory/", page))
            for cat in cfg.sourceforge_seed_categories:
                urls.append(_paged(f"https://sourceforge.net/directory/{cat}/", page))
    return [u for u in (normalize(x) for x in urls) if u]
