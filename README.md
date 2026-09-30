# 🗂️ Coletor de Repositórios (GitHub + SourceForge)

## 🎯 Objetivo

Construir um acervo de **repositórios/projetos de software públicos** para as
fases seguintes de um Sistema de Recuperação da Informação (indexação e busca).
Nesta etapa o foco é a **coleta** e o **armazenamento** dos dados.

A coleta é feita por um **crawler que extrai os dados do HTML** das páginas
públicas — como visto em aula (baixar a página, fazer o parsing do DOM, salvar
o conteúdo). São **duas fontes de conteúdo**:

| Fonte | Tipo | Origem |
|-------|------|--------|
| `github_html` | **Crawler de HTML** | páginas de `github.com` |
| `sourceforge` | **Crawler de HTML** | páginas de `sourceforge.net` |
| `github_api` | Coletor por API (opcional) | `api.github.com` |

Por padrão, o coletor usa as **duas fontes de crawler** (`github_html` e
`sourceforge`). A fonte por API do GitHub é mantida como alternativa.

De cada documento extraímos: nome, descrição, README/descrição longa (texto
rico), linguagem, tópicos/categorias, estrelas/popularidade, forks, licença,
datas e o **proprietário** (perfil), armazenado de forma deduplicada.

## 🧱 Armazenamento — **sem banco de dados**

Conforme a restrição do trabalho, **não** é usado banco de dados (nem SQL nem
NoSQL). Tudo é gravado em **arquivos** no diretório `data/`:

```
data/
  repositories.jsonl      # 1 documento por linha (JSON) — o acervo
  users.jsonl             # 1 proprietário por linha (deduplicado)
  raw_readme/xx/<hash>.md # texto rico bruto (README/descrição)
  state/                  # estado do coletor (permite retomar)
    seen_docs.txt         #   ids já coletados (deduplicação)
    seen_users.txt        #   logins já salvos
    partitions.jsonl      #   fronteira: partições pendentes
    done_partitions.txt   #   partições concluídas
    failures.jsonl        #   falhas (tolerância a falhas / auditoria)
```

O formato **JSON Lines** é *append-only*, streamável e não exige servidor —
ideal para alimentar o indexador da Parte 2 sem recoletar.

## 📋 Requisitos

- Python 3
- `requests`, `beautifulsoup4`, `lxml` (via `pip install -r requirements.txt`)
- **Nenhum token é necessário** para os crawlers de HTML. (Só a fonte opcional
  `github_api` usa um token do GitHub, lido de `GITHUB_TOKEN`.)

## ▶️ Execução

```bash
pip install -r requirements.txt

# Teste rápido: 200 documentos das duas fontes de crawler (padrão)
python run_coletor.py --target 200

# Coleta completa (>50 mil documentos) + confirmar caminho do acervo
python run_coletor.py --target 50000 --export

# Somente uma fonte
python run_coletor.py --sources github_html
python run_coletor.py --sources sourceforge

# Incluir também o coletor por API do GitHub (requer GITHUB_TOKEN)
python run_coletor.py --sources github_html sourceforge github_api

# Retomar coleta interrompida: rode o mesmo comando de novo
python run_coletor.py --target 50000
```

Se a coleta for interrompida, o progresso (partição/página atual, partições
concluídas, documentos já salvos) fica em `data/state/` e a execução **retoma
de onde parou**.

## 🤝 Boas maneiras (políticas de coleta)

- **Identificação:** User-Agent enviado em toda requisição.
- **robots.txt:** consultado e respeitado por domínio (desligável com
  `--no-robots`, não recomendado).
- **Delay + jitter** entre requisições e **um único worker** (controle de banda,
  evita a proteção anti-bot / HTTP 429).
- **Tolerância a falhas:** timeout, *retry* com *backoff* exponencial em erros
  transitórios (429/5xx) e honra ao `Retry-After`.

## 📈 Estratégia de escala (superar 50 mil)

As buscas/diretórios limitam quantos resultados são navegáveis por consulta.
Para superar isso, o espaço de busca é **particionado** em milhares de
consultas **disjuntas** cuja soma ultrapassa 50 mil:

- **GitHub:** por número **exato de estrelas** (`stars:1` … `stars:5000`).
- **SourceForge:** por **faceta** de sistema operacional e de categoria do
  diretório (`/directory/os:windows/`, `/directory/development/`, …).

## ✅ Testes

Os parsers de HTML têm testes *offline* contra fixtures salvas:

```bash
python -m pytest tests/ -q      # ou:  python tests/test_parsers.py
```

## 📁 Organização

```
coletor/config.py            configurações e políticas
coletor/fetcher.py           rede: robots.txt, delay, retry (HTML e JSON)
coletor/storage.py           armazenamento em ARQUIVOS (sem BD)
coletor/crawler.py           motor de coleta (multi-fonte)
coletor/sources/             fontes de conteúdo:
  base.py                      interface comum
  github.py                    crawler HTML do github.com
  sourceforge.py               crawler HTML do sourceforge.net
  github_api.py                coletor por API (opcional)
run_coletor.py               script principal
tests/                       testes dos parsers (offline)
```

Detalhes completos no relatório (`RELATORIO_PARTE1_COLETOR.md`).
