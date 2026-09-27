"""
Camada de armazenamento do coletor.

Responsabilidades:
  1. Persistir os metadados extraídos de cada filme (SQLite).
  2. Guardar o HTML bruto em disco (para reprocessamento nas fases
     de Indexação/Recuperação sem precisar re-coletar).
  3. Manter o estado do crawler (URLs visitadas + fronteira pendente),
     permitindo RETOMAR uma coleta interrompida (checkpointing).

O uso de SQLite é uma decisão de projeto: é um banco embarcado, sem
servidor, transacional e concorrente-seguro para leitura, adequado para
milhões de linhas — suficiente para as 50k+ páginas do trabalho.
"""

import hashlib
import json
import os
import sqlite3
import threading
from typing import Dict, Iterable, List, Optional, Set


SCHEMA = """
CREATE TABLE IF NOT EXISTS films (
    url             TEXT PRIMARY KEY,
    slug            TEXT,
    title           TEXT,
    year            INTEGER,
    director        TEXT,
    cast_list       TEXT,     -- JSON array
    genres          TEXT,     -- JSON array
    countries       TEXT,     -- JSON array
    languages       TEXT,     -- JSON array
    runtime_min     INTEGER,
    rating_avg      REAL,
    rating_count    INTEGER,
    synopsis        TEXT,
    tagline         TEXT,
    poster_url      TEXT,
    raw_html_path   TEXT,
    fetched_at      TEXT DEFAULT (datetime('now'))
);

-- Fronteira (frontier): URLs pendentes de visita.
CREATE TABLE IF NOT EXISTS frontier (
    url         TEXT PRIMARY KEY,
    url_type    TEXT,          -- 'film' | 'list'
    depth       INTEGER DEFAULT 0
);

-- URLs já processadas (política de re-visita: não revisitar).
CREATE TABLE IF NOT EXISTS visited (
    url         TEXT PRIMARY KEY
);

-- Registro de falhas (tolerância a falhas / auditoria).
CREATE TABLE IF NOT EXISTS failures (
    url         TEXT,
    status      TEXT,
    error       TEXT,
    failed_at   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_films_year   ON films(year);
CREATE INDEX IF NOT EXISTS idx_films_rating ON films(rating_avg);
"""


class Storage:
    def __init__(self, output_dir: str, db_filename: str, raw_html_dir: str):
        self.output_dir = output_dir
        self.raw_html_dir = os.path.join(output_dir, raw_html_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.raw_html_dir, exist_ok=True)

        self.db_path = os.path.join(output_dir, db_filename)
        # check_same_thread=False + lock explícito: os workers compartilham
        # a mesma conexão de forma serializada nas escritas.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")   # melhor concorrência
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ---------------- HTML bruto ----------------
    def save_raw_html(self, url: str, html: str) -> str:
        """Salva o HTML bruto em disco e retorna o caminho relativo."""
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        # Sharding em subpastas por prefixo do hash para não estourar
        # o nº de arquivos por diretório.
        subdir = os.path.join(self.raw_html_dir, digest[:2])
        os.makedirs(subdir, exist_ok=True)
        path = os.path.join(subdir, f"{digest}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return os.path.relpath(path, self.output_dir)

    # ---------------- Filmes ----------------
    def save_film(self, data: Dict) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO films
                (url, slug, title, year, director, cast_list, genres,
                 countries, languages, runtime_min, rating_avg, rating_count,
                 synopsis, tagline, poster_url, raw_html_path)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    data.get("url"),
                    data.get("slug"),
                    data.get("title"),
                    data.get("year"),
                    data.get("director"),
                    json.dumps(data.get("cast", []), ensure_ascii=False),
                    json.dumps(data.get("genres", []), ensure_ascii=False),
                    json.dumps(data.get("countries", []), ensure_ascii=False),
                    json.dumps(data.get("languages", []), ensure_ascii=False),
                    data.get("runtime_min"),
                    data.get("rating_avg"),
                    data.get("rating_count"),
                    data.get("synopsis"),
                    data.get("tagline"),
                    data.get("poster_url"),
                    data.get("raw_html_path"),
                ),
            )
            self._conn.commit()

    def film_count(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM films")
            return cur.fetchone()[0]

    # ---------------- Estado / checkpoint ----------------
    def mark_visited(self, url: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO visited(url) VALUES (?)", (url,)
            )

    def is_visited(self, url: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM visited WHERE url = ?", (url,)
            )
            return cur.fetchone() is not None

    def load_visited(self) -> Set[str]:
        with self._lock:
            cur = self._conn.execute("SELECT url FROM visited")
            return {row[0] for row in cur.fetchall()}

    def add_to_frontier(self, items: Iterable[tuple]) -> None:
        """items: iterável de (url, url_type, depth)."""
        with self._lock:
            self._conn.executemany(
                "INSERT OR IGNORE INTO frontier(url, url_type, depth) "
                "VALUES (?,?,?)",
                list(items),
            )
            self._conn.commit()

    def pop_frontier(self, url: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM frontier WHERE url = ?", (url,))

    def load_frontier(self) -> List[tuple]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT url, url_type, depth FROM frontier"
            )
            return cur.fetchall()

    def frontier_size(self) -> int:
        with self._lock:
            cur = self._conn.execute("SELECT COUNT(*) FROM frontier")
            return cur.fetchone()[0]

    def record_failure(self, url: str, status: str, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO failures(url, status, error) VALUES (?,?,?)",
                (url, status, error),
            )
            self._conn.commit()

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()

    # ---------------- Exportação (para a fase de Indexação) ----------------
    def export_jsonl(self, path: Optional[str] = None) -> str:
        """Exporta todos os filmes para JSONL (uma linha = um documento)."""
        path = path or os.path.join(self.output_dir, "films.jsonl")
        with self._lock:
            cur = self._conn.execute("SELECT * FROM films")
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                rec = dict(zip(cols, row))
                for k in ("cast_list", "genres", "countries", "languages"):
                    if rec.get(k):
                        try:
                            rec[k] = json.loads(rec[k])
                        except (json.JSONDecodeError, TypeError):
                            pass
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return path
