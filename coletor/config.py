"""
Configuração central do coletor (API do GitHub).

Todas as políticas, tolerâncias e critérios de parada do coletor ficam
concentrados aqui para facilitar a justificativa das decisões de projeto
exigida no relatório (Descrição do coletor - 40%).

Fonte de dados: API REST oficial do GitHub (https://api.github.com).
Documento principal: REPOSITÓRIOS. De cada repositório extraímos também o
PROPRIETÁRIO (usuário/organização), armazenado de forma deduplicada.
"""

import os
from dataclasses import dataclass, field
from typing import List


def _load_token() -> str:
    """
    Lê o token da API do GitHub de forma segura:
      1. variável de ambiente GITHUB_TOKEN;
      2. arquivo .env na raiz (linha GITHUB_TOKEN=...).
    O token NUNCA fica no código versionado.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return token
    # Fallback: .env simples (sem depender de libs externas).
    for path in (".env", os.path.join(os.path.dirname(__file__), "..", ".env")):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GITHUB_TOKEN") and "=" in line:
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except FileNotFoundError:
            continue
    return ""


@dataclass
class CrawlerConfig:
    # -------------------- Identidade / API --------------------
    api_base: str = "https://api.github.com"
    # Token pessoal (grátis). Sem token: 60 req/h. Com token: 5.000 req/h.
    token: str = field(default_factory=_load_token)
    # User-Agent é OBRIGATÓRIO pela API do GitHub.
    user_agent: str = "GitHubRICrawler/1.0 (Trabalho academico de RI)"
    # Versão da API (boa prática recomendada pelo GitHub).
    api_version: str = "2022-11-28"

    # -------------------- Política de polidez --------------------
    # A API do GitHub tem rate limit próprio; respeitamos os cabeçalhos
    # X-RateLimit-Remaining / X-RateLimit-Reset. Ainda assim, um pequeno
    # delay entre requisições evita a proteção de "abuso/secondary limit".
    request_delay: float = 0.8
    request_delay_jitter: float = 0.4
    num_workers: int = 1  # a Search API não recomenda concorrência alta

    # -------------------- Tolerância a falhas --------------------
    request_timeout: float = 30.0
    max_retries: int = 4
    backoff_factor: float = 2.0
    backoff_base: float = 2.0
    retry_status_codes: tuple = (429, 500, 502, 503, 504)

    # -------------------- Critério de parada --------------------
    # Meta de repositórios coletados. >50.000 = nota máxima em Escala.
    target_pages: int = 50000
    max_frontier_size: int = 1000000

    # -------------------- Coleta de README --------------------
    # O README é o texto rico usado na busca textual (fase de Indexação).
    fetch_readme: bool = True
    readme_max_bytes: int = 200000  # trunca READMEs gigantes

    # -------------------- Armazenamento --------------------
    output_dir: str = "data"
    db_filename: str = "github.db"
    raw_html_dir: str = "raw_readme"  # aqui guardamos os READMEs brutos
    save_raw_html: bool = True
    checkpoint_every: int = 100

    # -------------------- Estratégia de busca / particionamento --------
    # A Search API do GitHub retorna no máximo 1.000 resultados por consulta.
    # Para superar 50 mil, PARTICIONAMOS o espaço de busca em muitas consultas
    # menores (cada uma <= 1.000 resultados) e somamos. Aqui particionamos por
    # FAIXA DE ESTRELAS: repositórios com N estrelas exatas. Isso cria milhares
    # de partições disjuntas cobrindo praticamente todos os repositórios.
    #
    # Consulta base: filtramos apenas repositórios com >=1 estrela para focar
    # em conteúdo minimamente relevante (decisão de projeto).
    search_base_query: str = "stars:>=1"
    # Particionamento primário por nº exato de estrelas, de star_max até star_min.
    star_min: int = 1
    star_max: int = 5000
    per_page: int = 100  # máximo permitido pela API

    # -------------------- Logging --------------------
    log_level: str = "INFO"
    log_file: str = "crawler.log"
