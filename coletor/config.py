"""
Configuração central do coletor.

Reúne todas as políticas, tolerâncias e critérios de parada, para facilitar a
justificativa das decisões de projeto exigida no relatório.

Fontes de conteúdo (duas, conforme o trabalho):
  - github_html : CRAWLER de HTML de github.com (parsing do DOM);
  - sourceforge : CRAWLER de HTML de sourceforge.net (segunda fonte);
  - github_api  : coletor pela API REST do GitHub (mantido como alternativa).

Documento (unidade de recuperação): um repositório/projeto. De cada um também
extraímos o PROPRIETÁRIO (perfil), armazenado de forma deduplicada.

Armazenamento: SOMENTE ARQUIVOS — é PROIBIDO banco de dados (nem SQL nem NoSQL).
"""

from dataclasses import dataclass, field
from typing import List

from .sources import DEFAULT_SOURCES


@dataclass
class CrawlerConfig:
    # -------------------- Fontes de conteúdo --------------------
    sources: List[str] = field(default_factory=lambda: list(DEFAULT_SOURCES))

    # -------------------- Identidade / boas maneiras --------------------
    # User-Agent de navegador: os crawlers leem as mesmas páginas HTML que um
    # usuário veria. Também usado para consultar o robots.txt.
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 "
        "RICrawler/2.0 (trabalho academico)"
    )
    accept_language: str = "en-US,en;q=0.9"
    # Respeitar o robots.txt de cada domínio (política de boas maneiras).
    respect_robots: bool = True

    # -------------------- Política de polidez --------------------
    # Sem API (crawler), a polidez é nossa responsabilidade: delay + jitter por
    # requisição para não sobrecarregar os sites nem disparar proteção anti-bot.
    request_delay: float = 2.0
    request_delay_jitter: float = 1.5
    num_workers: int = 1

    # -------------------- Tolerância a falhas --------------------
    request_timeout: float = 30.0
    max_retries: int = 4
    backoff_factor: float = 2.0
    backoff_base: float = 3.0
    retry_status_codes: tuple = (429, 500, 502, 503, 504)

    # -------------------- Critério de parada (limite offline) --------------
    # Meta de documentos. >50.000 = nota máxima em Escala.
    target_pages: int = 50000

    # -------------------- Texto rico (README/descrição) --------------------
    fetch_readme: bool = True
    readme_max_bytes: int = 200000

    # -------------------- Armazenamento (arquivos) --------------------
    output_dir: str = "data"
    raw_html_dir: str = "raw_readme"
    save_raw_html: bool = True
    checkpoint_every: int = 100

    # -------------------- Estratégia de busca / particionamento --------
    # Contorna os limites de paginação/consulta de cada site particionando o
    # espaço de busca em muitas listagens disjuntas e somando-as.
    star_min: int = 1
    star_max: int = 5000        # GitHub: partições stars:1..stars:5000
    per_page: int = 100
    search_max_pages: int = 100  # máx. de páginas navegáveis por partição

    # -------------------- Logging --------------------
    log_level: str = "INFO"
    log_file: str = "crawler.log"
