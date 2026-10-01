"""
Armazenamento do coletor.

1. SQLite (data/coletor.db) guarda todo o estado da coleta:
   - fila:        URLs a visitar, separadas por site (fila de cada domínio);
   - conhecidas:  conjunto de URLs já vistas (na fila ou visitadas). Um link
                  só entra na fila se ainda não estiver aqui;
   - visitadas:   cada URL já processada, com código HTTP, resultado e a
                  posição do HTML bruto no arquivo de bloco;
   - projetos:    os campos extraídos das páginas de projeto;
   - pistas:      dados vistos numa listagem sobre um projeto ainda não
                  visitado (a linguagem do repositório no cartão do tópico);
   - execucoes:   início e duração de cada execução, para as estatísticas.

   Cada página é registrada numa única transação: sai da fila, entra em
   visitadas, grava o projeto e enfileira os links novos. Se o programa
   cair no meio, ou a página inteira foi registrada ou nada foi, e ao rodar
   de novo a coleta continua exatamente de onde parou.

2. HTML bruto compactado em blocos (data/html/<site>/bloco_00001.gz ...),
   `block_size` páginas por arquivo. Cada página é um membro gzip
   independente; a tabela visitadas guarda o arquivo, a posição e o tamanho,
   então qualquer página pode ser lida de volta sem descompactar o bloco
   inteiro (ver Storage.read_raw).
"""

import gzip
import json
import os
import re
import sqlite3
import threading
from typing import Dict, Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS fila (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    site          TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    tipo          TEXT NOT NULL,        -- project | listing | sitemap
    prioridade    INTEGER NOT NULL,     -- 0 = projeto achado numa listagem; 1 = demais
    profundidade  INTEGER NOT NULL,     -- distância em links a partir da seed
    origem        TEXT                  -- página onde o link foi achado
);
CREATE INDEX IF NOT EXISTS idx_fila_ordem ON fila(site, prioridade, profundidade, id);

CREATE TABLE IF NOT EXISTS conhecidas (
    url   TEXT PRIMARY KEY,
    site  TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS visitadas (
    url           TEXT PRIMARY KEY,
    site          TEXT NOT NULL,
    tipo          TEXT,
    profundidade  INTEGER,
    status_http   INTEGER,
    resultado     TEXT NOT NULL,        -- projeto | ok | redirecionada | soft404 | duplicada
                                        -- | erro_http | erro_rede | bloqueada_robots | tipo_invalido
    detalhe       TEXT,                 -- mensagem de erro ou destino do redirecionamento
    coletado_em   TEXT NOT NULL,
    bytes         INTEGER,              -- tamanho baixado (sem compressão)
    bloco         TEXT,                 -- arquivo de bloco com o HTML bruto
    posicao       INTEGER,              -- posição do membro gzip no bloco
    tamanho       INTEGER               -- tamanho compactado
);
CREATE INDEX IF NOT EXISTS idx_visitadas_site ON visitadas(site, resultado);
CREATE INDEX IF NOT EXISTS idx_visitadas_bloco ON visitadas(site, bloco);

CREATE TABLE IF NOT EXISTS projetos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    site                TEXT NOT NULL,
    chave               TEXT NOT NULL,  -- dono/repo no GitHub, nome no SourceForge
    url                 TEXT NOT NULL,  -- URL canônica do projeto
    url_coletada        TEXT NOT NULL,
    coletado_em         TEXT NOT NULL,
    status_http         INTEGER,
    nome                TEXT,
    dono                TEXT,
    descricao           TEXT,
    resumo              TEXT,
    topicos             TEXT,           -- lista JSON
    categorias          TEXT,           -- lista JSON
    linguagem           TEXT,
    estrelas            INTEGER,
    forks               INTEGER,
    licenca             TEXT,
    readme              TEXT,
    downloads_semana    INTEGER,
    nota                REAL,
    num_avaliacoes      INTEGER,
    ultima_atualizacao  TEXT,
    hash_conteudo       TEXT,
    UNIQUE(site, chave)
);
CREATE INDEX IF NOT EXISTS idx_projetos_hash ON projetos(site, hash_conteudo);

CREATE TABLE IF NOT EXISTS pistas (
    url    TEXT PRIMARY KEY,
    dados  TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS execucoes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio    TEXT NOT NULL,
    fim       TEXT,
    segundos  REAL DEFAULT 0
);
"""

PROJECT_COLUMNS = [
    "site", "chave", "url", "url_coletada", "coletado_em", "status_http",
    "nome", "dono", "descricao", "resumo", "topicos", "categorias",
    "linguagem", "estrelas", "forks", "licenca", "readme",
    "downloads_semana", "nota", "num_avaliacoes", "ultima_atualizacao",
    "hash_conteudo",
]
LIST_COLUMNS = {"topicos", "categorias"}

VISIT_COLUMNS = [
    "url", "site", "tipo", "profundidade", "status_http", "resultado",
    "detalhe", "coletado_em", "bytes", "bloco", "posicao", "tamanho",
]

# Campos exportados para o JSONL, por site (entrada da etapa de indexação).
EXPORT_FIELDS = {
    "github": [
        "site", "url", "coletado_em", "status_http", "nome", "dono",
        "descricao", "topicos", "linguagem", "estrelas", "forks", "licenca",
        "readme",
    ],
    "sourceforge": [
        "site", "url", "coletado_em", "status_http", "nome", "descricao",
        "resumo", "categorias", "licenca", "linguagem", "downloads_semana",
        "nota", "num_avaliacoes", "ultima_atualizacao",
    ],
}


class Storage:
    def __init__(self, output_dir: str, db_filename: str):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.db_path = os.path.join(output_dir, db_filename)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=60)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._lock = threading.RLock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ---------------- Fila ----------------
    def _enqueue(self, entries: Iterable[Dict]) -> int:
        """Enfileira só as URLs que ainda não estão no conjunto de conhecidas."""
        added = 0
        for e in entries:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO conhecidas(url, site) VALUES (?, ?)",
                (e["url"], e["site"]))
            if cur.rowcount == 1:
                self._conn.execute(
                    "INSERT INTO fila(site, url, tipo, prioridade, profundidade, origem) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (e["site"], e["url"], e["tipo"], e["prioridade"],
                     e["profundidade"], e.get("origem")))
                added += 1
        return added

    def add_to_frontier(self, entries: Iterable[Dict]) -> int:
        with self._lock:
            added = self._enqueue(entries)
            self._conn.commit()
            return added

    def next_url(self, site: str) -> Optional[Dict]:
        """
        Próxima URL da fila do site. Ordem: prioridade, depois profundidade
        (busca em largura), depois ordem de chegada.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fila WHERE site = ? "
                "ORDER BY prioridade, profundidade, id LIMIT 1", (site,)).fetchone()
            return dict(row) if row else None

    def frontier_count(self, site: Optional[str] = None) -> int:
        with self._lock:
            if site:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM fila WHERE site = ?", (site,)).fetchone()[0]
            return self._conn.execute("SELECT COUNT(*) FROM fila").fetchone()[0]

    # ---------------- Consultas usadas durante a coleta ----------------
    def project_count(self, site: str) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM projetos WHERE site = ?", (site,)).fetchone()[0]

    def project_exists(self, site: str, key: str) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM projetos WHERE site = ? AND chave = ?",
                (site, key)).fetchone() is not None

    def hash_exists(self, site: str, digest: str) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM projetos WHERE site = ? AND hash_conteudo = ?",
                (site, digest)).fetchone() is not None

    def hint(self, url: str) -> Optional[Dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT dados FROM pistas WHERE url = ?", (url,)).fetchone()
            return json.loads(row[0]) if row else None

    # ---------------- Registro de uma página (uma transação) ----------------
    def record(self, item: Dict, visit: Dict, project: Optional[Dict] = None,
               hints: Optional[Dict[str, Dict]] = None,
               links: Optional[List[Dict]] = None,
               known: Optional[List[tuple]] = None) -> int:
        """
        Registra o processamento de uma página e devolve quantos links novos
        entraram na fila. Tudo acontece numa transação só.
        """
        with self._lock:
            try:
                self._conn.execute("DELETE FROM fila WHERE id = ?", (item["id"],))
                self._conn.execute(
                    f"INSERT OR REPLACE INTO visitadas({', '.join(VISIT_COLUMNS)}) "
                    f"VALUES ({', '.join('?' * len(VISIT_COLUMNS))})",
                    [visit.get(c) for c in VISIT_COLUMNS])
                if project:
                    values = []
                    for c in PROJECT_COLUMNS:
                        v = project.get(c)
                        if c in LIST_COLUMNS and v is not None:
                            v = json.dumps(v, ensure_ascii=False)
                        values.append(v)
                    self._conn.execute(
                        f"INSERT INTO projetos({', '.join(PROJECT_COLUMNS)}) "
                        f"VALUES ({', '.join('?' * len(PROJECT_COLUMNS))})", values)
                for url, data in (hints or {}).items():
                    self._conn.execute(
                        "INSERT OR IGNORE INTO pistas(url, dados) VALUES (?, ?)",
                        (url, json.dumps(data, ensure_ascii=False)))
                for url, site in (known or []):
                    self._conn.execute(
                        "INSERT OR IGNORE INTO conhecidas(url, site) VALUES (?, ?)",
                        (url, site))
                added = self._enqueue(links or [])
                self._conn.commit()
                return added
            except Exception:
                self._conn.rollback()
                raise

    # ---------------- Blocos de HTML ----------------
    def last_block(self, site: str) -> Optional[Dict]:
        """Último bloco usado pelo site: nome, páginas gravadas e fim dos dados válidos."""
        with self._lock:
            row = self._conn.execute(
                "SELECT bloco, COUNT(*) AS paginas, MAX(posicao + tamanho) AS fim "
                "FROM visitadas WHERE site = ? AND bloco = "
                "(SELECT MAX(bloco) FROM visitadas WHERE site = ?)",
                (site, site)).fetchone()
            if not row or row["bloco"] is None:
                return None
            return dict(row)

    def read_raw(self, url: str) -> Optional[bytes]:
        """Lê de volta o HTML bruto de uma URL visitada."""
        with self._lock:
            row = self._conn.execute(
                "SELECT bloco, posicao, tamanho FROM visitadas WHERE url = ?",
                (url,)).fetchone()
        if not row or row["bloco"] is None:
            return None
        with open(os.path.join(self.output_dir, row["bloco"]), "rb") as f:
            f.seek(row["posicao"])
            return gzip.decompress(f.read(row["tamanho"]))

    # ---------------- Execuções (tempo total) ----------------
    def start_run(self, started_at: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO execucoes(inicio) VALUES (?)", (started_at,))
            self._conn.commit()
            return cur.lastrowid

    def update_run(self, run_id: int, seconds: float, finished_at: Optional[str] = None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE execucoes SET segundos = ?, fim = COALESCE(?, fim) WHERE id = ?",
                (seconds, finished_at, run_id))
            self._conn.commit()

    # ---------------- Exportação ----------------
    def export_jsonl(self, path: str) -> int:
        """Grava um projeto por linha. Devolve o número de projetos exportados."""
        count = 0
        tmp = path + ".tmp"
        with self._lock:
            cur = self._conn.execute("SELECT * FROM projetos ORDER BY id")
            with open(tmp, "w", encoding="utf-8") as f:
                while True:
                    rows = cur.fetchmany(500)
                    if not rows:
                        break
                    for row in rows:
                        rec = dict(row)
                        for c in LIST_COLUMNS:
                            if rec.get(c):
                                rec[c] = json.loads(rec[c])
                        fields = EXPORT_FIELDS.get(rec["site"], list(rec))
                        out = {k: rec.get(k) for k in fields}
                        f.write(json.dumps(out, ensure_ascii=False) + "\n")
                        count += 1
        os.replace(tmp, path)
        return count

    # ---------------- Acesso para as estatísticas ----------------
    def query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()


class BlockWriter:
    """
    Grava o HTML bruto compactado em blocos de `block_size` páginas.

    Cada página vira um membro gzip anexado ao fim do bloco atual. Ao
    retomar uma coleta, o bloco é cortado no fim do último membro registrado
    no banco, descartando restos de uma gravação interrompida.
    """

    def __init__(self, storage: Storage, raw_dir: str, site: str, block_size: int):
        self.rel_dir = f"{raw_dir}/{site}"
        self.abs_dir = os.path.join(storage.output_dir, raw_dir, site)
        os.makedirs(self.abs_dir, exist_ok=True)
        self.block_size = block_size
        self.index, self.count = 1, 0
        self._fh = None

        last = storage.last_block(site)
        if last:
            self.index = int(re.search(r"(\d+)\.gz$", last["bloco"]).group(1))
            self.count = last["paginas"]
            path = self._path()
            if os.path.exists(path) and os.path.getsize(path) > last["fim"]:
                with open(path, "r+b") as f:
                    f.truncate(last["fim"])

    def _name(self) -> str:
        return f"bloco_{self.index:05d}.gz"

    def _path(self) -> str:
        return os.path.join(self.abs_dir, self._name())

    def write(self, content: bytes):
        """Grava uma página e devolve (bloco, posição, tamanho compactado)."""
        if self.count >= self.block_size:
            self.close()
            self.index += 1
            self.count = 0
        if self._fh is None:
            self._fh = open(self._path(), "ab")
        data = gzip.compress(content, compresslevel=6)
        self._fh.seek(0, os.SEEK_END)
        offset = self._fh.tell()
        self._fh.write(data)
        self._fh.flush()
        self.count += 1
        return f"{self.rel_dir}/{self._name()}", offset, len(data)

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None
