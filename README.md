# Sistema de RI — Parte 1: Coletor (Letterboxd)

Coletor (web crawler focado) que adquire páginas de filmes do
[Letterboxd](https://letterboxd.com) para alimentar um Sistema de Recuperação
da Informação. Esta é a **Parte 1 (Coletor)** do trabalho.

> 📄 Relatório completo (proposta, coletor, escala):
> [`RELATORIO_PARTE1_COLETOR.md`](RELATORIO_PARTE1_COLETOR.md)

## Estrutura

```
letterboxd-ri/
├── coletor/
│   ├── config.py     # Todas as políticas/tolerâncias/critérios de parada
│   ├── fetcher.py    # HTTP: polidez, robots.txt, retry/backoff
│   ├── parser.py     # Descoberta de links + extração de metadados (JSON-LD)
│   ├── storage.py    # SQLite + HTML bruto + estado (checkpoint)
│   └── crawler.py    # Orquestração: fronteira, workers, parada
├── run_coletor.py    # CLI (ponto de entrada)
├── requirements.txt
├── README.md
└── RELATORIO_PARTE1_COLETOR.md
```

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
# Teste rápido (100 filmes)
python run_coletor.py --target 100 --workers 2 --delay 1.5

# Coleta completa (>50 mil) + exportar JSONL
python run_coletor.py --target 50000 --workers 4 --export

# Retomar coleta interrompida (basta rodar de novo)
python run_coletor.py --target 50000 --workers 4

# Só exportar o que já foi coletado
python run_coletor.py --export-only
```

### Opções da CLI

| Flag | Descrição |
|------|-----------|
| `--target N` | Meta de páginas de filme (critério de parada principal) |
| `--workers N` | Nº de workers concorrentes |
| `--delay S` | Delay base entre requisições, por worker (segundos) |
| `--output DIR` | Diretório de saída (padrão: `data/`) |
| `--no-robots` | Não respeitar robots.txt (use com responsabilidade) |
| `--no-raw-html` | Não salvar o HTML bruto |
| `--export` | Exportar `films.jsonl` ao final |
| `--export-only` | Só exportar do banco existente e sair |

## Saídas (em `data/`)

- `letterboxd.db` — metadados + estado do crawler (SQLite)
- `raw_html/` — HTML bruto por página (reprocessamento)
- `films.jsonl` — um documento/linha (entrada da Parte 2)
- `crawler.log` — log de execução

## Verificar quantos filmes foram coletados

```bash
sqlite3 data/letterboxd.db "SELECT COUNT(*) FROM films;"
```

## Notas

- Este é um **crawler focado**: restrito a `letterboxd.com` e a páginas de
  filme. Respeita `robots.txt`, aplica *crawl-delay* e re-tenta erros
  transitórios com *backoff*.
- Ajuste `--delay`/`--workers` conforme a resposta do servidor. Se receber
  muitos HTTP 429, **aumente o delay** e **reduza os workers**.
```
