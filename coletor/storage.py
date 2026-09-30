"""
Camada de armazenamento do coletor — SOMENTE ARQUIVOS (sem banco de dados).

Restrição do trabalho: é PROIBIDO usar banco de dados (nem SQL nem NoSQL).
Portanto, tudo é persistido em arquivos simples no disco, exatamente como no
diagrama de coleta visto em aula ("Salvar conteúdo" -> REPO em arquivos):

  data/
    repositories.jsonl   -> um DOCUMENTO (repositório/projeto) por linha (JSON)
    users.jsonl          -> um PROPRIETÁRIO por linha (JSON), deduplicado
    raw_readme/xx/<hash>.md -> texto rico bruto (README/descrição) por documento
    state/
      seen_docs.txt      -> ids de documentos já coletados (dedup / retomar)
      seen_users.txt     -> logins de usuários já salvos (dedup)
      partitions.jsonl   -> fronteira: partições pendentes (key, query, page)
      done_partitions.txt-> partições já concluídas (não reprocessar)
      failures.jsonl     -> registro de falhas (tolerância a falhas / auditoria)

Decisões de projeto (justificativa para o relatório):
  - JSON Lines (JSONL): 1 documento por linha, append-only. Escreve em O(1),
    não carrega tudo em memória, é streamável para a fase de Indexação e não
    exige servidor/índice de banco.
  - Conjuntos "seen_*" em memória (carregados dos arquivos no início) garantem
    DEDUPLICAÇÃO e permitem RETOMAR a coleta de onde parou (checkpoint).
  - README/descrição bruta em arquivos separados desacopla coleta de indexação
    (permite reprocessar sem recoletar).
"""

import hashlib
import json
import os
import threading
from typing import Dict, List, Optional, Set, Tuple


class Storage:
    def __init__(self, output_dir: str, raw_dir_name: str = "raw_readme"):
        self.output_dir = output_dir
        self.raw_dir = os.path.join(output_dir, raw_dir_name)
        self.state_dir = os.path.join(output_dir, "state")
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.raw_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)

        # Caminhos dos arquivos.
        self.repos_path = os.path.join(output_dir, "repositories.jsonl")
        self.users_path = os.path.join(output_dir, "users.jsonl")
        self.seen_docs_path = os.path.join(self.state_dir, "seen_docs.txt")
        self.seen_users_path = os.path.join(self.state_dir, "seen_users.txt")
        self.partitions_path = os.path.join(self.state_dir, "partitions.jsonl")
        self.done_path = os.path.join(self.state_dir, "done_partitions.txt")
        self.failures_path = os.path.join(self.state_dir, "failures.jsonl")

        self._lock = threading.Lock()

        # Estado em memória (carregado dos arquivos -> permite retomar).
        self._seen_docs: Set[str] = self._load_lines(self.seen_docs_path)
        self._seen_users: Set[str] = self._load_lines(self.seen_users_path)
        self._done: Set[str] = self._load_lines(self.done_path)
        # Fronteira: dict key -> (query, page). Carregada do partitions.jsonl.
        self._partitions: Dict[str, Tuple[str, int]] = \
            self._load_partitions()

        # Handles append-only para os documentos e usuários.
        self._repos_fh = open(self.repos_path, "a", encoding="utf-8")
        self._users_fh = open(self.users_path, "a", encoding="utf-8")

    # ---------------- utilitários de arquivo ----------------
    @staticmethod
    def _load_lines(path: str) -> Set[str]:
        result: Set[str] = set()
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        result.add(line)
        except FileNotFoundError:
            pass
        return result

    def _load_partitions(self) -> Dict[str, Tuple[str, int]]:
        parts: Dict[str, Tuple[str, int]] = {}
        try:
            with open(self.partitions_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    key = rec["key"]
                    if key in self._done:
                        continue
                    parts[key] = (rec["query"], int(rec.get("page", 1)))
        except FileNotFoundError:
            pass
        return parts

    def _rewrite_partitions(self) -> None:
        """Regrava o arquivo da fronteira a partir do estado em memória."""
        tmp = self.partitions_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for key, (query, page) in self._partitions.items():
                f.write(json.dumps(
                    {"key": key, "query": query, "page": page},
                    ensure_ascii=False) + "\n")
        os.replace(tmp, self.partitions_path)

    # ---------------- README/descrição bruta ----------------
    def save_raw_readme(self, doc_id: str, text: str) -> str:
        digest = hashlib.sha1(doc_id.encode("utf-8")).hexdigest()
        subdir = os.path.join(self.raw_dir, digest[:2])
        os.makedirs(subdir, exist_ok=True)
        path = os.path.join(subdir, f"{digest}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return os.path.relpath(path, self.output_dir)

    # ---------------- Documentos (repositórios/projetos) ----------------
    def doc_exists(self, doc_id: str) -> bool:
        with self._lock:
            return doc_id in self._seen_docs

    def save_repository(self, data: Dict) -> bool:
        """
        Grava um documento (uma linha JSON). Retorna True se é NOVO (para a
        contagem de escala). Deduplica por `full_name`.
        """
        doc_id = data.get("full_name")
        if not doc_id:
            return False
        with self._lock:
            if doc_id in self._seen_docs:
                return False
            self._repos_fh.write(json.dumps(data, ensure_ascii=False) + "\n")
            self._seen_docs.add(doc_id)
            self._append_line(self.seen_docs_path, doc_id)
            return True

    def save_user(self, user: Dict) -> None:
        login = user.get("login") if user else None
        if not login:
            return
        with self._lock:
            if login in self._seen_users:
                return
            self._users_fh.write(json.dumps(user, ensure_ascii=False) + "\n")
            self._seen_users.add(login)
            self._append_line(self.seen_users_path, login)

    @staticmethod
    def _append_line(path: str, value: str) -> None:
        with open(path, "a", encoding="utf-8") as f:
            f.write(value + "\n")

    def repo_count(self) -> int:
        with self._lock:
            return len(self._seen_docs)

    def user_count(self) -> int:
        with self._lock:
            return len(self._seen_users)

    # ---------------- Partições (fronteira) ----------------
    def add_partitions(self, items) -> None:
        """items: iterável de (key, query, page). Ignora as já concluídas."""
        with self._lock:
            for key, query, page in items:
                if key in self._done or key in self._partitions:
                    continue
                self._partitions[key] = (query, int(page))
            self._rewrite_partitions()

    def update_partition_page(self, key: str, page: int) -> None:
        with self._lock:
            if key in self._partitions:
                query, _ = self._partitions[key]
                self._partitions[key] = (query, int(page))
                self._rewrite_partitions()

    def finish_partition(self, key: str) -> None:
        with self._lock:
            self._partitions.pop(key, None)
            if key not in self._done:
                self._done.add(key)
                self._append_line(self.done_path, key)
            self._rewrite_partitions()

    def load_partitions(self) -> List[Tuple[str, str, int]]:
        with self._lock:
            return [(k, q, p) for k, (q, p) in sorted(self._partitions.items())]

    def done_partition_keys(self) -> Set[str]:
        with self._lock:
            return set(self._done)

    def partitions_pending(self) -> int:
        with self._lock:
            return len(self._partitions)

    def record_failure(self, ref: str, status: str, error: str) -> None:
        with self._lock:
            with open(self.failures_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(
                    {"ref": ref, "status": status, "error": error},
                    ensure_ascii=False) + "\n")

    # ---------------- ciclo de vida ----------------
    def commit(self) -> None:
        with self._lock:
            self._repos_fh.flush()
            self._users_fh.flush()
            os.fsync(self._repos_fh.fileno()) if hasattr(os, "fsync") else None

    def close(self) -> None:
        with self._lock:
            try:
                self._repos_fh.flush()
                self._users_fh.flush()
            finally:
                self._repos_fh.close()
                self._users_fh.close()

    # ---------------- Exportação (para a fase de Indexação) ----------------
    def export_jsonl(self, path: Optional[str] = None) -> str:
        """
        O acervo JÁ é um JSONL (repositories.jsonl). Este método apenas
        garante o flush e devolve o caminho — mantido por compatibilidade com
        o fluxo anterior (--export / --export-only).
        """
        with self._lock:
            self._repos_fh.flush()
        return path or self.repos_path
