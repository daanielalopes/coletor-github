"""
Configuração central do coletor.

Todas as políticas do coletor (boas maneiras, tolerância a falhas, critério
de parada, seeds e armazenamento) ficam concentradas aqui, para facilitar a
leitura e a justificativa das decisões no relatório.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class CrawlerConfig:
    # -------------------- Identificação --------------------
    user_agent: str = "ColetorRI-PUCMinas/1.0 (trabalho academico)"

    # -------------------- Boas maneiras --------------------
    # Espera mínima entre dois pedidos ao mesmo domínio, em segundos. Se o
    # robots.txt tiver Crawl-delay maior, vale o Crawl-delay.
    min_delay: float = 1.0

    # -------------------- Tolerância a falhas --------------------
    request_timeout: float = 30.0
    max_retries: int = 3               # novas tentativas após a primeira
    backoff_base: float = 5.0          # 5 s, 10 s, 20 s
    max_backoff: float = 300.0
    retry_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504)
    max_page_bytes: int = 5_000_000    # páginas maiores são cortadas
    robots_retry_wait: float = 60.0    # espera para tentar ler o robots.txt de novo
    # Se o site continuar respondendo 429/503 depois de todas as tentativas,
    # a thread desse site faz uma pausa maior antes de seguir para a próxima URL.
    throttle_pause: float = 120.0

    # -------------------- Critério de parada --------------------
    target_per_site: int = 25000       # páginas de projeto por site
    max_depth: Optional[int] = None    # None = sem limite de profundidade
    sites: Tuple[str, ...] = ("github", "sourceforge")

    # -------------------- Seeds --------------------
    github_seed_topics: Tuple[str, ...] = (
        "python", "javascript", "machine-learning", "java", "linux",
        "typescript", "go", "rust", "cpp", "c", "php", "ruby", "android",
        "docker", "react", "nodejs", "deep-learning", "security", "database",
        "kubernetes", "api", "cli", "game-engine", "swift", "kotlin",
        "csharp", "data-visualization", "compiler", "emulator",
        "bioinformatics",
    )
    # Páginas de cada tópico que entram como seed (?page=1..N). O GitHub
    # mostra 20 repositórios por página e no máximo 50 páginas por tópico.
    github_seed_pages: int = 50

    sourceforge_seed_categories: Tuple[str, ...] = (
        "software-development", "system", "internet", "games", "multimedia",
        "business", "scientific-engineering", "communications",
        "artificial-intelligence", "education", "database", "security",
        "formats-and-protocols", "desktop-environment", "text-editors",
        "linux", "windows", "mac",
    )
    # Páginas de cada categoria que entram como seed (?page=1..N). O
    # SourceForge mostra 25 projetos por página.
    sourceforge_seed_pages: int = 20

    # -------------------- Armazenamento --------------------
    output_dir: str = "data"
    db_filename: str = "coletor.db"
    raw_dir: str = "html"              # HTML bruto em blocos gzip
    block_size: int = 1000             # páginas por arquivo de bloco
    export_filename: str = "projetos.jsonl"
    readme_max_chars: int = 100_000

    # -------------------- Log --------------------
    log_level: str = "INFO"
    log_filename: str = "coletor.log"
