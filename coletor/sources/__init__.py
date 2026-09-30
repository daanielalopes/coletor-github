"""
Fontes de conteúdo do coletor.

Cada fonte encapsula:
  - como gerar as PARTIÇÕES da fronteira (para escala);
  - a URL/params da listagem de cada partição/página;
  - o parsing da listagem (lista de itens);
  - a URL da página de detalhe de um item;
  - o parsing do detalhe (metadados + texto rico) e do proprietário.

O mesmo motor de coleta (crawler.py) atende múltiplas fontes:
  - github_html  : CRAWLER de HTML do site github.com (parsing do DOM);
  - sourceforge  : CRAWLER de HTML do site sourceforge.net (segunda fonte);
  - github_api   : coletor pela API REST do GitHub (mantido; uses_api=True).

Por padrão o trabalho coleta pelas duas fontes de CRAWLER (github_html e
sourceforge); a fonte por API fica disponível como alternativa.

Observação: as fontes de crawler dependem de BeautifulSoup (bs4). Para não
exigir bs4 quando só se usa a API, os imports são LAZY (feitos dentro de
get_source), carregando apenas a fonte solicitada.
"""

from .base import Source

# Nomes das fontes disponíveis (a classe é importada sob demanda).
SOURCE_NAMES = ["github_html", "sourceforge", "github_api"]

# Conjunto padrão de fontes do trabalho: os dois CRAWLERS de HTML.
DEFAULT_SOURCES = ["github_html", "sourceforge"]

# Compatibilidade: dict-like para escolhas de CLI (sorted(SOURCES)).
SOURCES = {name: name for name in SOURCE_NAMES}


def get_source(name: str) -> Source:
    """Importa e instancia a fonte pedida (import lazy para evitar deps extras)."""
    if name == "github_html":
        from .github import GitHubSource
        return GitHubSource()
    if name == "sourceforge":
        from .sourceforge import SourceForgeSource
        return SourceForgeSource()
    if name == "github_api":
        from .github_api import GitHubApiSource
        return GitHubApiSource()
    raise ValueError(
        f"Fonte desconhecida: {name!r}. Disponiveis: {SOURCE_NAMES}")
