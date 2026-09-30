"""
Interface base de uma FONTE de conteúdo para o coletor (crawler de HTML).

Toda fonte é um CRAWLER de páginas HTML (nunca API): baixa a listagem,
extrai os itens, baixa a página de detalhe de cada item e faz o parsing do
DOM. O motor genérico (crawler.py) apenas orquestra; a lógica específica de
cada site fica na sua subclasse.
"""

from typing import Dict, List, Optional, Tuple


class Source:
    #: nome curto/único da fonte (também gravado no campo `source`).
    name: str = "base"
    #: base do site (somente HTML público — sem API).
    site_base: str = ""
    #: True se a fonte consome uma API JSON em vez de fazer parsing de HTML.
    #: Por padrão False: TODAS as fontes são crawlers de HTML.
    uses_api: bool = False

    # ------------------------------------------------------------------
    # Fronteira / escala
    # ------------------------------------------------------------------
    def build_partitions(self, cfg) -> List[Tuple[str, str, int]]:
        """
        Gera as partições da fronteira: lista de (key, query, start_page).
        `query` é uma string livre interpretada pela própria fonte em
        `listing_request`. O particionamento é o que permite superar os
        limites de paginação de cada site e atingir a escala (50k+).
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Listagem (páginas de busca/diretório)
    # ------------------------------------------------------------------
    def listing_request(self, cfg, query: str, page: int
                        ) -> Tuple[str, Optional[dict]]:
        """Devolve (url, params) da página `page` da listagem de `query`."""
        raise NotImplementedError

    def parse_listing(self, html: str) -> List[str]:
        """Extrai do HTML a lista de identificadores de itens (full_name/slug)."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Detalhe (página do item)
    # ------------------------------------------------------------------
    def detail_url(self, item_id: str) -> str:
        """URL da página de detalhe (HTML) de um item."""
        raise NotImplementedError

    def parse_detail(self, item_id: str, html: str) -> Dict:
        """Extrai os metadados do item a partir do HTML da página de detalhe."""
        raise NotImplementedError

    def parse_readme(self, html: str) -> Optional[str]:
        """Extrai o texto rico (README/descrição longa) do HTML de detalhe."""
        raise NotImplementedError

    def parse_owner(self, item_id: str, detail: Dict) -> Dict:
        """Monta o registro do proprietário (deduplicado por login)."""
        raise NotImplementedError
