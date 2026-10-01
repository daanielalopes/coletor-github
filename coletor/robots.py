"""
Leitura e consulta do robots.txt de cada domínio.

Usa a biblioteca protego (a mesma do Scrapy). O urllib.robotparser da
biblioteca padrão não entende curingas (* e $), e os robots.txt do GitHub e
do SourceForge usam muitos, por exemplo "Disallow: /*/*/issues/new" e
"Allow: /directory/*?page=". O protego também aplica a regra da
correspondência mais longa entre Allow e Disallow, como manda a RFC 9309.

Regras quando o robots.txt não pode ser lido:
  - 4xx (ex.: 404): o site não tem robots.txt, tudo é permitido;
  - 5xx ou erro de rede: não sabemos as regras, então não coletamos nada
    desse domínio agora. A thread espera e tenta ler o arquivo de novo.
"""

import logging
from typing import List, Optional

from protego import Protego

logger = logging.getLogger(__name__)


class RobotsRules:
    def __init__(self, fetcher, base_url: str, user_agent: str):
        self.fetcher = fetcher
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self._parser: Optional[Protego] = None

    def load(self) -> bool:
        """Baixa e interpreta o robots.txt. Devolve False se não conseguiu."""
        url = f"{self.base_url}/robots.txt"
        res = self.fetcher.get(url)
        if res.status == 200:
            text = res.content.decode("utf-8", errors="replace")
            self._parser = Protego.parse(text)
            logger.info("robots.txt de %s carregado (%d bytes). Crawl-delay: %s.",
                        self.base_url, len(res.content), self.crawl_delay())
            return True
        if res.status is not None and 400 <= res.status < 500:
            logger.info("%s nao tem robots.txt (HTTP %d): tudo permitido.",
                        self.base_url, res.status)
            self._parser = Protego.parse("")
            return True
        logger.warning("Nao foi possivel ler %s (HTTP %s, %s).",
                       url, res.status, res.error)
        return False

    @property
    def loaded(self) -> bool:
        return self._parser is not None

    def allowed(self, url: str) -> bool:
        return self._parser is not None and self._parser.can_fetch(url, self.user_agent)

    def crawl_delay(self) -> Optional[float]:
        if self._parser is None:
            return None
        return self._parser.crawl_delay(self.user_agent)

    def sitemaps(self) -> List[str]:
        if self._parser is None:
            return []
        return list(self._parser.sitemaps)
