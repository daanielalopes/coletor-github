"""
Fetcher HTTP: baixa uma página com GET, sem usar nenhuma API.

Concentra as políticas de rede do coletor:
  - identificação: User-Agent próprio do coletor;
  - polidez: espera mínima entre dois pedidos ao mesmo domínio (1 s por
    padrão, ou o Crawl-delay do robots.txt, o que for maior);
  - tolerância a falhas: timeout, e para 429/503 (e outros erros
    temporários) espera cada vez maior (backoff exponencial) antes de tentar
    de novo, até 3 vezes. O cabeçalho Retry-After é respeitado quando vem;
  - redirecionamentos não são seguidos automaticamente: o coletor trata o
    destino como um link novo, que passa pelo filtro e pelo robots.txt.

Cada thread de domínio tem o seu próprio Fetcher (a sessão do requests não
deve ser compartilhada entre threads).
"""

import logging
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    status: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)
    content: bytes = b""
    encoding: Optional[str] = None
    error: Optional[str] = None
    truncated: bool = False
    interrupted: bool = False   # parada pedida durante a espera do backoff

    @property
    def content_type(self) -> str:
        return self.headers.get("Content-Type", "").lower()


class Fetcher:
    def __init__(self, config, stop_event=None):
        self.cfg = config
        self.stop_event = stop_event
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
        })
        self._delay: Dict[str, float] = {}
        self._last: Dict[str, float] = {}

    # ---------------- Polidez ----------------
    def set_delay(self, host: str, seconds: float) -> None:
        self._delay[host] = max(self.cfg.min_delay, seconds or 0.0)

    def _wait_turn(self, host: str) -> None:
        delay = self._delay.get(host, self.cfg.min_delay)
        elapsed = time.monotonic() - self._last.get(host, 0.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last[host] = time.monotonic()

    def _sleep(self, seconds: float) -> bool:
        """Dorme, mas acorda se a parada for pedida. Devolve True se foi interrompido."""
        if self.stop_event is None:
            time.sleep(seconds)
            return False
        return self.stop_event.wait(seconds)

    def _backoff(self, attempt: int, retry_after: Optional[str] = None) -> float:
        if retry_after and retry_after.strip().isdigit():
            return min(float(retry_after), self.cfg.max_backoff)
        wait = self.cfg.backoff_base * (2 ** attempt)
        return min(wait, self.cfg.max_backoff) + random.uniform(0, 1.0)

    # ---------------- GET ----------------
    def get(self, url: str) -> FetchResult:
        host = urlsplit(url).netloc
        result = FetchResult(url=url)
        for attempt in range(self.cfg.max_retries + 1):
            self._wait_turn(host)
            try:
                resp = self.session.get(
                    url, timeout=self.cfg.request_timeout,
                    allow_redirects=False, stream=True,
                )
                content, truncated = self._read_body(resp)
            except requests.RequestException as e:
                result.error = f"{type(e).__name__}: {e}"
                if attempt < self.cfg.max_retries:
                    wait = self._backoff(attempt)
                    logger.warning("Erro de rede em %s (%s). Nova tentativa em %.0fs.",
                                   url, type(e).__name__, wait)
                    if self._sleep(wait):
                        result.interrupted = True
                        return result
                    continue
                return result

            result.status = resp.status_code
            result.headers = dict(resp.headers)
            result.content = content
            result.truncated = truncated
            result.encoding = resp.encoding if "charset" in result.content_type else None
            result.error = None

            if resp.status_code in self.cfg.retry_status_codes and attempt < self.cfg.max_retries:
                wait = self._backoff(attempt, resp.headers.get("Retry-After"))
                logger.warning("HTTP %d em %s. Esperando %.0fs antes da tentativa %d.",
                               resp.status_code, url, wait, attempt + 2)
                if self._sleep(wait):
                    result.interrupted = True
                    return result
                continue
            return result
        return result

    def _read_body(self, resp: requests.Response):
        """Lê o corpo até o limite de tamanho, para não travar em arquivos enormes."""
        chunks, size, truncated = [], 0, False
        try:
            for chunk in resp.iter_content(65536):
                chunks.append(chunk)
                size += len(chunk)
                if size > self.cfg.max_page_bytes:
                    truncated = True
                    break
        finally:
            resp.close()
        return b"".join(chunks), truncated

    def close(self) -> None:
        self.session.close()
