#!/usr/bin/env python3
"""
Gera a pasta evidencias/ com provas da coleta, tiradas direto do banco
(data/coletor.db), do log (data/coletor.log) e do arquivo final
(data/projetos.jsonl).

Os dados completos têm cerca de 3 GB e não cabem no GitHub. Os arquivos
gerados aqui são pequenos, podem ser versionados e permitem conferir a coleta:
a lista de todas as URLs coletadas, uma amostra dos projetos, a linha do tempo
por hora, trechos do log e o hash SHA-256 do arquivo final.

Uso:
    python gerar_evidencias.py
"""

import csv
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime

from coletor.config import CrawlerConfig
from coletor.stats import report
from coletor.storage import Storage

OUT = "evidencias"
SAMPLE_PER_SITE = 50
README_SAMPLE_CHARS = 500
LOG_KEYS = ("Inicio da coleta", "Coleta encerrada", "Meta atingida", "projetos exportados",
            "seeds novas", "robots.txt de", "sitemaps do robots", "Interrupcao")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    cfg = CrawlerConfig()
    cfg.target_per_site = int(sys.argv[1]) if len(sys.argv) > 1 else 26000
    data = cfg.output_dir
    db_path = os.path.join(data, cfg.db_filename)
    log_path = os.path.join(data, cfg.log_filename)
    jsonl_path = os.path.join(data, cfg.export_filename)
    os.makedirs(OUT, exist_ok=True)
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row

    # 1. Estatísticas (a mesma saída de run_coletor.py --stats)
    storage = Storage(data, cfg.db_filename)
    with open(os.path.join(OUT, "estatisticas.txt"), "w", encoding="utf-8") as f:
        f.write(report(storage, cfg) + "\n")
    storage.close()

    # 2. Todas as URLs de projeto coletadas
    n_urls = 0
    with open(os.path.join(OUT, "urls_coletadas.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site", "url", "coletado_em", "status_http", "nome"])
        for r in db.execute("SELECT site, url, coletado_em, status_http, nome FROM projetos ORDER BY id"):
            w.writerow(list(r))
            n_urls += 1

    # 3. Amostra de projetos (espaçada ao longo da coleta, sempre a mesma)
    with open(os.path.join(OUT, "amostra_projetos.jsonl"), "w", encoding="utf-8") as f:
        for site in ("github", "sourceforge"):
            # Escolhe só os ids primeiro: ler os READMEs de todos os projetos seria lento.
            ids = [r[0] for r in db.execute(
                "SELECT id FROM projetos WHERE site = ? ORDER BY id", (site,))]
            step = max(1, len(ids) // SAMPLE_PER_SITE)
            chosen = ids[::step][:SAMPLE_PER_SITE]
            rows = db.execute(
                f"SELECT * FROM projetos WHERE id IN ({','.join('?' * len(chosen))}) ORDER BY id",
                chosen)
            for r in rows:
                rec = {k: r[k] for k in r.keys() if k not in ("id", "hash_conteudo")}
                for k in ("topicos", "categorias"):
                    if rec.get(k):
                        rec[k] = json.loads(rec[k])
                if rec.get("readme") and len(rec["readme"]) > README_SAMPLE_CHARS:
                    rec["readme"] = rec["readme"][:README_SAMPLE_CHARS] + "..."
                rec = {k: v for k, v in rec.items() if v is not None}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 4. Linha do tempo: páginas baixadas e projetos salvos por hora
    with open(os.path.join(OUT, "projetos_por_hora.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hora", "site", "paginas_baixadas", "projetos_salvos"])
        for r in db.execute(
                "SELECT substr(coletado_em, 1, 13) || ':00' AS hora, site, "
                "SUM(status_http IS NOT NULL), SUM(resultado = 'projeto') "
                "FROM visitadas GROUP BY hora, site ORDER BY hora, site"):
            w.writerow(list(r))

    # 5. Trechos do log
    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    with open(os.path.join(OUT, "trechos_do_log.txt"), "w", encoding="utf-8") as f:
        f.write(f"Arquivo: {log_path} ({len(lines)} linhas)\n\n")
        f.write("=== Primeiras 20 linhas ===\n")
        f.writelines(lines[:20])
        f.write("\n=== Eventos principais (inicio, robots.txt, seeds, metas, fim) ===\n")
        f.writelines(l for l in lines if any(k in l for k in LOG_KEYS))
        mid = len(lines) // 2
        f.write(f"\n=== 40 linhas seguidas do meio da coleta (a partir da linha {mid + 1}) ===\n")
        f.writelines(lines[mid:mid + 40])
        f.write("\n=== Ultimas 15 linhas ===\n")
        f.writelines(lines[-15:])

    # 6. Hash e contagem do arquivo final
    jsonl_lines = 0
    per_site = {}
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            jsonl_lines += 1
            site = json.loads(line)["site"]
            per_site[site] = per_site.get(site, 0) + 1
    digest = sha256(jsonl_path)
    with open(os.path.join(OUT, "sha256.txt"), "w", encoding="utf-8") as f:
        f.write(f"{digest}  {cfg.export_filename}\n")

    # 7. Resumo em JSON
    runs = [dict(r) for r in db.execute("SELECT inicio, fim, segundos FROM execucoes ORDER BY id")]
    summary = {
        "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
        "periodo_da_coleta": dict(zip(("primeira_pagina", "ultima_pagina"), db.execute(
            "SELECT MIN(coletado_em), MAX(coletado_em) FROM visitadas").fetchone())),
        "execucoes": runs,
        "tempo_total_segundos": round(sum(r["segundos"] or 0 for r in runs)),
        "paginas_de_projeto": dict(db.execute(
            "SELECT site, COUNT(*) FROM projetos GROUP BY site").fetchall()),
        "paginas_baixadas": dict(db.execute(
            "SELECT site, COUNT(*) FROM visitadas WHERE status_http IS NOT NULL GROUP BY site").fetchall()),
        "resultado_das_urls_visitadas": {
            f"{r[0]}/{r[1]}": r[2] for r in db.execute(
                "SELECT site, resultado, COUNT(*) FROM visitadas GROUP BY 1, 2 ORDER BY 1, 2")},
        "codigos_http": {
            f"{r[0]}/{r[1]}": r[2] for r in db.execute(
                "SELECT site, status_http, COUNT(*) FROM visitadas WHERE status_http IS NOT NULL "
                "GROUP BY 1, 2 ORDER BY 1, 2")},
        "urls_conhecidas": db.execute("SELECT COUNT(*) FROM conhecidas").fetchone()[0],
        "urls_na_fila_ao_final": db.execute("SELECT COUNT(*) FROM fila").fetchone()[0],
        "bytes_baixados_sem_gzip": db.execute("SELECT SUM(bytes) FROM visitadas").fetchone()[0],
        "projetos_jsonl": {"linhas": jsonl_lines, "por_site": per_site, "sha256": digest,
                           "bytes": os.path.getsize(jsonl_path)},
    }
    with open(os.path.join(OUT, "resumo.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
        f.write("\n")
    db.close()

    print(f"Evidencias geradas em {OUT}/: {n_urls} URLs de projeto, "
          f"{jsonl_lines} linhas no JSONL, sha256 {digest[:16]}...")


if __name__ == "__main__":
    main()
