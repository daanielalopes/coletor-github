"""
Fetcher HTTP: a camada que efetivamente baixa as páginas.

Concentra as POLÍTICAS de rede do coletor:
  - Polidez: User-Agent identificável, crawl-delay + jitter, respeito ao
    robots.txt.
  - Tolerância a falhas: timeout, retry com backoff exponencial em erros
    transitórios (429/5xx) e honra ao cabeçalho Retry-After.
"""

import logging
import random
import threading
import time
import urllib.robotparser
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests

# O Letterboxd fica atrás do Cloudflare. A lib 'cloudscraper' resolve o
# desafio anti-bot automaticamente. Se estiver instalada, usamos uma sessão
# dela no lugar da requests.Session comum. Instale com:
#     pip install cloudscraper
try:
    import cloudscraper  # type: ignore
    _HAS_CLOUDSCRAPER = True
except ImportError:  # pragma: no cover
    _HAS_CLOUDSCRAPER = False

logger = logging.getLogger(__name__)


class Fetcher:
    def __init__(self, config):
        self.cfg = config
        if _HAS_CLOUDSCRAPER:
            # Sessão que resolve o desafio Cloudflare do Letterboxd.
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows",
                         "mobile": False}
            )
            logger.info("Usando cloudscraper (bypass Cloudflare).")
        else:
            self.session = requests.Session()
            logger.warning(
                "cloudscraper NAO instalado. O Letterboxd usa Cloudflare e "
                "pode devolver 403. Instale com: pip install cloudscraper"
            )
        # Conjunto de cabeçalhos que imita um navegador real. Sites com
        # proteção anti-bot (Cloudflare, etc.) devolvem 403 quando faltam.
        self.session.headers.update({
            "User-Agent": config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        })

        # Delay independente por thread (cada worker respeita seu crawl-delay).
        self._local = threading.local()

        # robots.txt
        self._robots: Optional[urllib.robotparser.RobotFileParser] = None
        if config.respect_robots_txt:
            self._load_robots()

    # ---------------- robots.txt ----------------
    def _load_robots(self) -> None:
        robots_url = urljoin(self.cfg.base_url, "/robots.txt")
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = self.session.get(robots_url, timeout=self.cfg.request_timeout)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                logger.info("robots.txt carregado de %s", robots_url)
            else:
                logger.warning(
                    "robots.txt retornou %s; assumindo permissão total.",
                    resp.status_code,
                )
                rp = None
        except requests.RequestException as e:
            logger.warning("Falha ao carregar robots.txt (%s); prosseguindo.", e)
            rp = None
        self._robots = rp

    def can_fetch(self, url: str) -> bool:
        """Verifica a política de seleção definida pelo robots.txt."""
        if not self.cfg.respect_robots_txt or self._robots is None:
            return True
        return self._robots.can_fetch(self.cfg.user_agent, url)

    # ---------------- Polidez: crawl-delay ----------------
    def _polite_wait(self) -> None:
        last = getattr(self._local, "last_request", 0.0)
        delay = self.cfg.request_delay + random.uniform(
            0, self.cfg.request_delay_jitter
        )
        elapsed = time.monotonic() - last
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._local.last_request = time.monotonic()

    # ---------------- GET com retry/backoff ----------------
    def get(self, url: str) -> Optional[str]:
        """
        Baixa a URL e retorna o HTML (str) ou None se falhar em definitivo.
        Aplica polidez, valida domínio/robots e re-tenta em erros transitórios.
        """
        # Política de seleção: só o domínio permitido.
        if urlparse(url).netloc.replace("www.", "") != self.cfg.allowed_domain:
            logger.debug("Fora do domínio permitido, ignorando: %s", url)
            return None

        if not self.can_fetch(url):
            logger.info("Bloqueado por robots.txt: %s", url)
            return None

        attempt = 0
        while attempt <= self.cfg.max_retries:
            self._polite_wait()
            try:
                resp = self.session.get(
                    url, timeout=self.cfg.request_timeout
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

            if resp.status_code == 200:
                return resp.text

            if resp.status_code in self.cfg.retry_status_codes:
                # Honrar Retry-After quando presente (ex.: 429).
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = float(retry_after)
                else:
                    wait = self._backoff(attempt)
                logger.warning(
                    "HTTP %d em %s (tentativa %d). Aguardando %.1fs",
                    resp.status_code, url, attempt + 1, wait,
                )
                time.sleep(wait)
                attempt += 1
                continue

            # Erros não transitórios (404, 403, 410...): não re-tenta.
            if resp.status_code == 403:
                logger.warning(
                    "HTTP 403 (bloqueio anti-bot) em %s. O site recusou a "
                    "requisicao. Tente: aumentar --delay, reduzir --workers, "
                    "ou ajustar o User-Agent em config.py.",
                    url,
                )
            else:
                logger.info("HTTP %d (definitivo) em %s", resp.status_code, url)
            return None

        logger.error("Esgotadas as tentativas para %s", url)
        return None

    def _backoff(self, attempt: int) -> float:
        """Backoff exponencial com jitter."""
        base = self.cfg.backoff_base * (self.cfg.backoff_factor ** attempt)
        return base + random.uniform(0, 1.0)
