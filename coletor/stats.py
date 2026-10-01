"""
Estatísticas da coleta (python run_coletor.py --stats).

Mostra: páginas baixadas no total, páginas de projeto por site, erros,
tempo total de coleta, tamanho em disco e o preenchimento de cada campo
extraído, para conferir a qualidade da extração.
"""

import os
from typing import List

from .storage import EXPORT_FIELDS, LIST_COLUMNS, Storage

RESULT_LABELS = {
    "projeto": "paginas de projeto salvas",
    "ok": "listagens e sitemaps",
    "redirecionada": "redirecionamentos",
    "duplicada": "descartadas: duplicadas",
    "soft404": "descartadas: soft-404",
    "erro_http": "erros HTTP (404 etc.)",
    "erro_rede": "erros de rede/timeout",
    "bloqueada_robots": "bloqueadas pelo robots.txt",
    "tipo_invalido": "tipo de conteudo invalido",
}

ERROR_RESULTS = ("erro_http", "erro_rede", "tipo_invalido")


def _dir_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _fmt_time(seconds: float) -> str:
    seconds = int(seconds or 0)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}h {m:02d}min {s:02d}s"


def report(storage: Storage, cfg) -> str:
    lines: List[str] = []
    add = lines.append
    sites = [r[0] for r in storage.query(
        "SELECT DISTINCT site FROM conhecidas ORDER BY site")]

    downloaded = storage.query(
        "SELECT COUNT(*) FROM visitadas WHERE status_http IS NOT NULL")[0][0]
    downloaded_bytes = storage.query(
        "SELECT COALESCE(SUM(bytes), 0) FROM visitadas")[0][0]
    projects = storage.query("SELECT COUNT(*) FROM projetos")[0][0]
    errors = storage.query(
        f"SELECT COUNT(*) FROM visitadas WHERE resultado IN ({','.join('?' * len(ERROR_RESULTS))})",
        ERROR_RESULTS)[0][0]
    runs = storage.query("SELECT COUNT(*), COALESCE(SUM(segundos), 0) FROM execucoes")[0]
    seconds = runs[1]

    add("=" * 64)
    add("ESTATISTICAS DA COLETA")
    add("=" * 64)
    add(f"Paginas baixadas (total):      {downloaded}")
    add(f"Paginas de projeto (total):    {projects}")
    add(f"Erros (total):                 {errors}")
    add(f"Tempo total de coleta:         {_fmt_time(seconds)} em {runs[0]} execucao(oes)")
    if seconds:
        add(f"Taxa media:                    {downloaded / (seconds / 3600):.0f} paginas/hora")
    add(f"Volume baixado (sem gzip):     {_fmt_bytes(downloaded_bytes)}")

    for site in sites:
        add("")
        add(f"--- {site} " + "-" * (58 - len(site)))
        n_proj = storage.query("SELECT COUNT(*) FROM projetos WHERE site = ?", (site,))[0][0]
        n_down = storage.query(
            "SELECT COUNT(*) FROM visitadas WHERE site = ? AND status_http IS NOT NULL",
            (site,))[0][0]
        pending = storage.query("SELECT COUNT(*) FROM fila WHERE site = ?", (site,))[0][0]
        known = storage.query("SELECT COUNT(*) FROM conhecidas WHERE site = ?", (site,))[0][0]
        add(f"Paginas de projeto:            {n_proj} (meta {cfg.target_per_site})")
        add(f"Paginas baixadas:              {n_down}")
        add(f"URLs conhecidas:               {known}")
        add(f"URLs na fila:                  {pending}")
        add("Resultado das URLs visitadas:")
        for row in storage.query(
                "SELECT resultado, COUNT(*) FROM visitadas WHERE site = ? "
                "GROUP BY resultado ORDER BY COUNT(*) DESC", (site,)):
            add(f"    {RESULT_LABELS.get(row[0], row[0]):32} {row[1]}")
        codes = storage.query(
            "SELECT status_http, COUNT(*) FROM visitadas WHERE site = ? "
            "AND status_http IS NOT NULL GROUP BY status_http ORDER BY COUNT(*) DESC",
            (site,))
        if codes:
            add("Codigos HTTP: " + ", ".join(f"{c[0]}: {c[1]}" for c in codes))
        if n_proj:
            # Uma passada só pela tabela para todos os campos, e com o total no
            # mesmo instante (antes, com a coleta rodando, dava mais de 100%).
            # octet_length() mede o texto sem carregá-lo inteiro: o README pode
            # ter 100 mil caracteres, e carregar todos deixava a consulta lenta
            # com o banco fora da memória.
            fields = [f for f in EXPORT_FIELDS.get(site, [])
                      if f not in ("site", "url", "coletado_em", "status_http")]
            exprs = []
            for field in fields:
                cond = f"octet_length({field}) > 0"
                if field in LIST_COLUMNS:
                    cond += f" AND {field} != '[]'"
                exprs.append(f"SUM(CASE WHEN {cond} THEN 1 ELSE 0 END)")
            row = storage.query(
                f"SELECT COUNT(*), {', '.join(exprs)} FROM projetos WHERE site = ?", (site,))[0]
            total = row[0] or 1
            add("Preenchimento dos campos (% dos projetos):")
            for field, filled in zip(fields, row[1:]):
                add(f"    {field:22} {100.0 * (filled or 0) / total:5.1f}%")

    out = cfg.output_dir
    html_size = _dir_size(os.path.join(out, cfg.raw_dir))
    db_size = sum(os.path.getsize(p) for p in (
        storage.db_path, storage.db_path + "-wal") if os.path.exists(p))
    jsonl = os.path.join(out, cfg.export_filename)
    jsonl_size = os.path.getsize(jsonl) if os.path.exists(jsonl) else 0
    blocks = sum(len(f) for _, _, f in os.walk(os.path.join(out, cfg.raw_dir)))
    add("")
    add("--- tamanho em disco " + "-" * 43)
    add(f"HTML bruto (gzip):             {_fmt_bytes(html_size)} em {blocks} blocos")
    add(f"Banco SQLite:                  {_fmt_bytes(db_size)}")
    add(f"{cfg.export_filename}:{' ' * (31 - len(cfg.export_filename))}{_fmt_bytes(jsonl_size)}")
    add(f"Total:                         {_fmt_bytes(html_size + db_size + jsonl_size)}")
    add("=" * 64)
    return "\n".join(lines)
