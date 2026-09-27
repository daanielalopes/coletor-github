"""
Fetcher HTTP: camada que conversa com a API REST do GitHub.

Concentra as POLÍTICAS de rede do coletor:
  - Autenticação: token pessoal (Bearer), User-Agent obrigatório, versão da API.
  - Polidez / rate limit: respeita os cabeçalhos X-RateLimit-Remaining e
    X-RateLimit-Reset (dorme até a janela reabrir) e o "secondary rate limit".
  - Tolerância a falhas: timeout, retry com backoff exponencial em erros
    transitórios (429/5xx) e honra ao cabeçalho Retry-After.

Diferença em relação a um crawler de HTML: aqui consumimos JSON estruturado
de uma API oficial — não há parsing de páginas nem risco de bloqueio anti-bot.
"""

import logging
import random
import time
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, config):
        self.cfg = config
        self.session = requests.Session()
        headers = {
            "User-Agent": config.user_agent,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": config.api_version,
        }
        if config.token:
            headers["Authorization"] = f"Bearer {config.token}"
            logger.info("Autenticado com token (limite ~5000 req/h).")
        else:
            logger.warning(
                "SEM token: limite de apenas 60 req/h. Defina GITHUB_TOKEN "
                "(variavel de ambiente ou arquivo .env) para 5000 req/h."
            )
        self.session.headers.update(headers)
        self._last_request = 0.0

    # ---------------- Polidez ----------------
    def _polite_wait(self) -> None:
        delay = self.cfg.request_delay + random.uniform(
            0, self.cfg.request_delay_jitter
        )
        elapsed = time.monotonic() - self._last_request
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.monotonic()

    # ---------------- Rate limit ----------------
    def _respect_rate_limit(self, resp: requests.Response) -> None:
        """Se estamos no fim da cota, dorme até a janela reabrir."""
        remaining = resp.headers.get("X-RateLimit-Remaining")
        reset = resp.headers.get("X-RateLimit-Reset")
        if remaining is not None and reset is not None:
            try:
                if int(remaining) <= 1:
                    wait = max(0.0, float(reset) - time.time()) + 1.0
                    if wait > 0:
                        logger.warning(
                            "Rate limit atingido. Aguardando %.0fs ate reset.",
                            wait,
                        )
                        time.sleep(wait)
            except ValueError:
                pass

    # ---------------- GET JSON ----------------
    def get_json(self, url: str, params: Optional[dict] = None
                 ) -> Tuple[Optional[dict], Optional[requests.Response]]:
        """
        Faz GET e devolve (json, response). Em falha definitiva devolve
        (None, response|None). Trata rate limit e erros transitórios.
        """
        attempt = 0
        while attempt <= self.cfg.max_retries:
            self._polite_wait()
            try:
                resp = self.session.get(
                    url, params=params, timeout=self.cfg.request_timeout
                )
            except requests.RequestException as e:
                wait = self._backoff(attempt)
                logger.warning(
                    "Erro de rede em %s (tentativa %d): %s. Aguardando %.1fs",
                    url, attempt + 1, e, wait,
                )
                time.sleep(wait)
                attempt += 1
                continue

            self._respect_rate_limit(resp)

            if resp.status_code == 200:
                try:
                    return resp.json(), resp
                except ValueError:
                    logger.error("Resposta 200 sem JSON valido em %s", url)
                    return None, resp

            # 403 pode ser rate limit primário/secundário (não é bloqueio
            # anti-bot como no scraping de HTML).
            if resp.status_code in (403, 429):
                retry_after = resp.headers.get("Retry-After")
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if retry_after and retry_after.isdigit():
                    wait = float(retry_after)
                elif remaining == "0":
                    reset = resp.headers.get("X-RateLimit-Reset")
                    wait = max(1.0, float(reset) - time.time()) + 1.0 if reset \
                        else self._backoff(attempt)
                else:
                    wait = self._backoff(attempt)
                logger.warning(
                    "HTTP %d em %s (rate/abuse limit). Aguardando %.0fs.",
                    resp.status_code, url, wait,
                )
                time.sleep(wait)
                attempt += 1
                continue

            if resp.status_code in self.cfg.retry_status_codes:
                wait = self._backoff(attempt)
                logger.warning(
                    "HTTP %d em %s (tentativa %d). Aguardando %.1fs",
                    resp.status_code, url, attempt + 1, wait,
                )
                time.sleep(wait)
                attempt += 1
                continue

            # 404 e outros definitivos.
            logger.info("HTTP %d (definitivo) em %s", resp.status_code, url)
            return None, resp

        logger.error("Esgotadas as tentativas para %s", url)
        return None, None

    # ---------------- GET texto (README bruto) ----------------
    def get_text(self, url: str, accept: str = "application/vnd.github.raw+json"
                 ) -> Optional[str]:
        attempt = 0
        while attempt <= self.cfg.max_retries:
            self._polite_wait()
            try:
                resp = self.session.get(
                    url, timeout=self.cfg.request_timeout,
                    headers={"Accept": accept},
                )
            except requests.RequestException as e:
                time.sleep(self._backoff(attempt))
                attempt += 1
                continue
            self._respect_rate_limit(resp)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code in (403, 429) or \
                    resp.status_code in self.cfg.retry_status_codes:
                time.sleep(self._backoff(attempt))
                attempt += 1
                continue
            return None  # 404: repo sem README
        return None

    def _backoff(self, attempt: int) -> float:
        base = self.cfg.backoff_base * (self.cfg.backoff_factor ** attempt)
        return base + random.uniform(0, 1.0)
