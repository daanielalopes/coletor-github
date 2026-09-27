"""
Camada de armazenamento do coletor (GitHub).

Responsabilidades:
  1. Persistir os REPOSITÓRIOS coletados (documento principal) — SQLite.
  2. Persistir os USUÁRIOS/organizações proprietários, deduplicados.
  3. Guardar o README bruto em disco (texto rico para a fase de Indexação).
  4. Manter o estado do coletor (partições pendentes + já concluídas),
     permitindo RETOMAR uma coleta interrompida (checkpointing).

SQLite é uma decisão de projeto: banco embarcado, sem servidor,
transacional e adequado para milhões de linhas — suficiente para as
50k+ documentos do trabalho.
"""

import hashlib
import json
import os
import sqlite3
import threading
from typing import Dict, Iterable, List, Optional, Set


SCHEMA = """
-- Documento principal do RI: repositórios.
CREATE TABLE IF NOT EXISTS repositories (
    id              INTEGER PRIMARY KEY,   -- id numérico do GitHub
    full_name       TEXT UNIQUE,           -- owner/repo
    name            TEXT,
    owner_login     TEXT,
    description     TEXT,
    readme          TEXT,                  -- texto do README (busca textual)
    language        TEXT,
    topics          TEXT,                  -- JSON array
    stars           INTEGER,
    forks           INTEGER,
    watchers        INTEGER,
    open_issues     INTEGER,
    size_kb         INTEGER,
    license_name    TEXT,
    default_branch  TEXT,
    homepage        TEXT,
    html_url        TEXT,
    is_fork         INTEGER,
    created_at      TEXT,
    updated_at      TEXT,
    pushed_at       TEXT,
    readme_path     TEXT,                  -- caminho do README bruto em disco
    fetched_at      TEXT DEFAULT (datetime('now'))
);

-- Perfis (proprietários) extraídos dos repositórios, deduplicados.
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    login       TEXT UNIQUE,
    type        TEXT,          -- 'User' | 'Organization'
    html_url    TEXT,
    avatar_url  TEXT,
    seen_at     TEXT DEFAULT (datetime('now'))
);

-- Partições de busca pendentes (fronteira do coletor).
CREATE TABLE IF NOT EXISTS partitions (
    key         TEXT PRIMARY KEY,   -- ex.: 'stars=42'
    query       TEXT,               -- consulta completa da Search API
    page        INTEGER DEFAULT 1   -- próxima página a buscar nesta partição
);

-- Partições já concluídas (não reprocessar).
CREATE TABLE IF NOT EXISTS done_partitions (
    key         TEXT PRIMARY KEY
);

-- Registro de falhas (tolerância a falhas / auditoria).
CREATE TABLE IF NOT EXISTS failures (
    ref         TEXT,
    status      TEXT,
    error       TEXT,
    failed_at   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_repo_lang  ON repositories(language);
CREATE INDEX IF NOT EXISTS idx_repo_stars ON repositories(stars);
"""


class Storage:
    def __init__(self, output_dir: str, db_filename: str, raw_html_dir: str):
        self.output_dir = output_dir
        self.raw_dir = os.path.join(output_dir, raw_html_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.raw_dir, exist_ok=True)

        self.db_path = os.path.join(output_dir, db_filename)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ---------------- README bruto ----------------
    def save_raw_readme(self, full_name: str, text: str) -> str:
        digest = hashlib.sha1(full_name.encode("utf-8")).hexdigest()
        subdir = os.path.join(self.raw_dir, digest[:2])
        os.makedirs(subdir, exist_ok=True)
        path = os.path.join(subdir, f"{digest}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return os.path.relpath(path, self.output_dir)

    # ---------------- Repositórios ----------------
    def save_repository(self, data: Dict) -> bool:
        """Retorna True se inseriu um repo novo (para contagem de escala)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM repositories WHERE id = ?", (data.get("id"),)
            )
            is_new = cur.fetchone() is None
            self._conn.execute(
                """
                INSERT OR REPLACE INTO repositories
                (id, full_name, name, owner_login, description, readme,
                 language, topics, stars, forks, watchers, open_issues,
                 size_kb, license_name, default_branch, homepage, html_url,
                 is_fork, created_at, updated_at, pushed_at, readme_path)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    data.get("id"),
                    data.get("full_name"),
                    data.get("name"),
                    data.get("owner_login"),
                    data.get("description"),
                    data.get("readme"),
                    data.get("language"),
                    json.dumps(data.get("topics", []), ensure_ascii=False),
                    data.get("stars"),
                    data.get("forks"),
                    data.get("watchers"),
                    data.get("open_issues"),
                    data.get("size_kb"),
                    data.get("license_name"),
                    data.get("default_branch"),
                    data.get("homepage"),
                    data.get("html_url"),
                    1 if data.get("is_fork") else 0,
                    data.get("created_at"),
                    data.get("updated_at"),
                    data.get("pushed_at"),
                    data.get("readme_path"),
                ),
            )
            return is_new

    def save_user(self, user: Dict) -> None:
        if not user or not user.get("id"):
            return
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO users(id, login, type, html_url, avatar_url)
                VALUES (?,?,?,?,?)
                """,
                (
                    user.get("id"), user.get("login"), user.get("type"),
                    user.get("html_url"), user.get("avatar_url"),
                ),
            )

    def repo_count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM repositories").fetchone()[0]

    def user_count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM users").fetchone()[0]

    # ---------------- Partições (fronteira) ----------------
    def add_partitions(self, items: Iterable[tuple]) -> None:
        """items: iterável de (key, query, page)."""
        with self._lock:
            self._conn.executemany(
                "INSERT OR IGNORE INTO partitions(key, query, page) "
                "VALUES (?,?,?)", list(items),
            )
            self._conn.commit()

    def update_partition_page(self, key: str, page: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE partitions SET page = ? WHERE key = ?", (page, key)
            )

    def finish_partition(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM partitions WHERE key = ?", (key,))
            self._conn.execute(
                "INSERT OR IGNORE INTO done_partitions(key) VALUES (?)", (key,)
            )
            self._conn.commit()

    def load_partitions(self) -> List[tuple]:
        with self._lock:
            return self._conn.execute(
                "SELECT key, query, page FROM partitions ORDER BY key"
            ).fetchall()

    def done_partition_keys(self) -> Set[str]:
        with self._lock:
            return {r[0] for r in
                    self._conn.execute("SELECT key FROM done_partitions")}

    def partitions_pending(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM partitions").fetchone()[0]

    def record_failure(self, ref: str, status: str, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO failures(ref, status, error) VALUES (?,?,?)",
                (ref, status, error),
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
        path = path or os.path.join(self.output_dir, "repositories.jsonl")
        with self._lock:
            cur = self._conn.execute("SELECT * FROM repositories")
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                rec = dict(zip(cols, row))
                if rec.get("topics"):
                    try:
                        rec["topics"] = json.loads(rec["topics"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return path
