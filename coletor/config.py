"""
Configuração central do coletor.

Todas as políticas, tolerâncias e critérios de parada do crawler ficam
concentrados aqui para facilitar a justificativa das decisões de projeto
exigida no relatório (Descrição do coletor - 40%).
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class CrawlerConfig:
    # -------------------- Identidade / Domínio --------------------
    # Crawler FOCADO: restrito a um único domínio (letterboxd.com)
    base_url: str = "https://letterboxd.com"
    allowed_domain: str = "letterboxd.com"

    # User-Agent identificável (política de polidez / transparência).
    # Coloque um e-mail de contato real do grupo em produção.
    user_agent: str = (
        "LetterboxdRICrawler/1.0 (Trabalho academico de RI; "
        "contato: grupo-ri@exemplo.edu.br)"
    )

    # -------------------- Política de polidez --------------------
    # Delay mínimo (em segundos) entre requisições de UM MESMO worker.
    # Evita sobrecarregar o servidor (crawl-delay).
    request_delay: float = 1.0
    # Variação aleatória adicional (jitter) para não parecer um robô rígido.
    request_delay_jitter: float = 0.5
    # Nº de workers concorrentes. Mantenha baixo por polidez.
    num_workers: int = 4
    # Respeitar as diretivas do robots.txt do site.
    respect_robots_txt: bool = True

    # -------------------- Tolerância a falhas --------------------
    request_timeout: float = 20.0          # timeout por requisição (s)
    max_retries: int = 3                   # tentativas em erro transitório
    backoff_factor: float = 2.0            # backoff exponencial (2, 4, 8...)
    backoff_base: float = 2.0              # espera base (s) na 1ª retentativa
    # Códigos HTTP considerados transitórios (vale a pena re-tentar).
    retry_status_codes: tuple = (429, 500, 502, 503, 504)

    # -------------------- Critério de parada --------------------
    # Meta de páginas de filme coletadas. >50.000 = nota máxima em Escala.
    target_pages: int = 50000
    # Limite de segurança para a fronteira (frontier) não crescer infinito.
    max_frontier_size: int = 500000
    # Nº máximo de páginas de LISTAGEM (seeds paginadas) a percorrer por seed.
    max_list_pages_per_seed: int = 3000

    # -------------------- Armazenamento --------------------
    output_dir: str = "data"
    db_filename: str = "letterboxd.db"
    raw_html_dir: str = "raw_html"         # HTML bruto (subdir de output_dir)
    save_raw_html: bool = True             # guardar HTML p/ reprocessar depois
    checkpoint_every: int = 100            # persistir estado a cada N páginas

    # -------------------- Sementes (seeds) --------------------
    # Páginas de listagem paginadas do Letterboxd usadas como ponto de partida.
    # A partir delas o crawler extrai links para /film/{slug}/.
    seeds: List[str] = field(default_factory=lambda: [
        "https://letterboxd.com/films/by/rating/",
        "https://letterboxd.com/films/popular/",
        "https://letterboxd.com/films/by/release/",
        "https://letterboxd.com/films/genre/drama/by/rating/",
        "https://letterboxd.com/films/genre/comedy/by/rating/",
        "https://letterboxd.com/films/genre/horror/by/rating/",
        "https://letterboxd.com/films/genre/documentary/by/rating/",
        "https://letterboxd.com/films/genre/action/by/rating/",
        "https://letterboxd.com/films/genre/thriller/by/rating/",
        "https://letterboxd.com/films/genre/romance/by/rating/",
        "https://letterboxd.com/films/genre/animation/by/rating/",
        "https://letterboxd.com/films/genre/science-fiction/by/rating/",
    ])

    # -------------------- Logging --------------------
    log_level: str = "INFO"
    log_file: str = "crawler.log"
