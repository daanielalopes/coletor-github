"""
Fetcher HTTP: camada de rede do coletor.

Concentra as POLÍTICAS de rede/boas maneiras (conforme visto em aula):
  - Identidade: User-Agent (identificar-se como robô/cliente) e Accept-Language.
  - Boas maneiras: consulta e RESPEITA o robots.txt de cada host (política de
    acesso dos domínios), aplica delay + jitter por requisição (controle de
    banda) e usa um único worker sequencial.
  - Tolerância a falhas: timeout, retry com backoff exponencial em erros
    transitórios (429/5xx) e honra ao cabeçalho Retry-After (anti-bot/limite).

Dois modos de obtenção:
  - get_html(url)  -> texto HTML (usado pelos CRAWLERS: github_html, sourceforge)
  - get_json(url)  -> JSON     (usado pela fonte por API: github_api)
"""

import logging
import random
import time
from typing import Optional, Tuple
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, config):
        self.cfg = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.user_agent,
            "Accept-Language": config.accept_language,
            "Connection": "keep-alive",
        })
        self._last_request = 0.0
        # Cache de robots.txt por host (política de boas maneiras).
        self._robots: dict = {}

    # ---------------- Boas maneiras: robots.txt ----------------
    def _robots_allows(self, url: str) -> bool:
        if not self.cfg.respect_robots:
            return True
        parsed = urlparse(url)
        host = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._robots.get(host)
        if rp is None:
            rp = RobotFileParser()
            rp.set_url(f"{host}/robots.txt")
            try:
                rp.read()
            except Exception:
                # Se não conseguimos ler o robots.txt, seguimos (fail-open),
                # mas mantendo o resto das boas maneiras (delay, UA).
                rp = None
            self._robots[host] = rp
        if rp is None:
            return True
        return rp.can_fetch(self.cfg.user_agent, url)

    # ---------------- Polidez (delay + jitter) ----------------
    def _polite_wait(self) -> None:
        delay = self.cfg.request_delay + random.uniform(
            0, self.cfg.request_delay_jitter)
        elapsed = time.monotonic() - self._last_request
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.monotonic()

    # ---------------- núcleo do GET com retry ----------------
    def _get(self, url: str, params: Optional[dict], headers: Optional[dict]
             ) -> Optional[requests.Response]:
        if not self._robots_allows(url):
            logger.info("Bloqueado por robots.txt: %s", url)
            return None

        attempt = 0
        while attempt <= self.cfg.max_retries:
            self._polite_wait()
            try:
                resp = self.session.get(
                    url, params=params, headers=headers,
                    timeout=self.cfg.request_timeout)
            except requests.RequestException as e:
                wait = self._backoff(attempt)
                logger.warning("Erro de rede em %s (tent. %d): %s. Aguardando %.1fs",
                               url, attempt + 1, e, wait)
                time.sleep(wait)
                attempt += 1
                continue

            if resp.status_code == 200:
                return resp

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() \
                    else self._backoff(attempt)
                logger.warning("HTTP 429 em %s. Aguardando %.0fs.", url, wait)
                time.sleep(wait)
                attempt += 1
                continue

            if resp.status_code in self.cfg.retry_status_codes:
                wait = self._backoff(attempt)
                logger.warning("HTTP %d em %s (tent. %d). Aguardando %.1fs",
                               resp.status_code, url, attempt + 1, wait)
                time.sleep(wait)
                attempt += 1
                continue

            # 403/404 e demais definitivos.
            logger.info("HTTP %d (definitivo) em %s", resp.status_code, url)
            return None

        logger.error("Esgotadas as tentativas para %s", url)
        return None

    # ---------------- GET HTML (crawlers) ----------------
    def get_html(self, url: str, params: Optional[dict] = None) -> Optional[str]:
        resp = self._get(
            url, params,
            headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
        return resp.text if resp is not None else None

    # ---------------- GET JSON (fonte por API) ----------------
    def get_json(self, url: str, params: Optional[dict] = None,
                 extra_headers: Optional[dict] = None
                 ) -> Tuple[Optional[dict], Optional[requests.Response]]:
        headers = {"Accept": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        resp = self._get(url, params, headers=headers)
        if resp is None:
            return None, None
        try:
            return resp.json(), resp
        except ValueError:
            return None, resp

    def _backoff(self, attempt: int) -> float:
        base = self.cfg.backoff_base * (self.cfg.backoff_factor ** attempt)
        return base + random.uniform(0, 1.0)
