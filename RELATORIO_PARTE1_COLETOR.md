# Sistema de Recuperação da Informação — Parte 1: Coletor

**Fonte de dados:** Letterboxd (rede social de filmes — `letterboxd.com`)
**Linguagem:** Python 3
**Grupo:** _(preencher com os nomes dos integrantes)_

---

## 1. Proposta do Sistema de RI (30%)

### 1.1 O problema

O **Letterboxd** é uma das maiores redes sociais dedicadas a cinema, com um
catálogo de mais de um milhão de filmes, cada um descrito por metadados ricos
(sinopse, diretor, elenco, gênero, país, idioma, duração) e por sinais sociais
(nota média e número de avaliações). Encontrar filmes relevantes nesse volume
por meio de navegação manual é ineficiente.

**Problema de RI:** dado um acervo de páginas de filmes coletadas do
Letterboxd, permitir que o usuário **recupere filmes relevantes** a partir de
uma necessidade de informação — seja por **busca textual** (ex.: "ficção
científica distópica sobre inteligência artificial") sobre a sinopse e os
metadados, seja por **navegação facetada** (por gênero, ano, diretor, país,
faixa de nota).

### 1.2 A solução proposta

Construir um **Sistema de RI de busca e navegacional** dividido nas três
etapas do trabalho:

| Etapa | Papel no sistema |
|-------|------------------|
| **1. Coletor** (esta entrega) | Adquirir o acervo de documentos (páginas de filme) da web. |
| **2. Representação/Indexação** | Pré-processar o texto (tokenização, normalização, remoção de *stopwords*, *stemming*) e construir um **índice invertido** ponderado (ex.: TF-IDF/BM25) sobre título + sinopse + metadados. |
| **3. Recuperação** | Atender consultas do usuário (modelo vetorial/BM25) e oferecer navegação por facetas, ordenando por relevância. |

**Documento (unidade de recuperação):** uma página de filme. Cada documento
reúne um campo textual principal (sinopse) e campos estruturados usados como
facetas/filtros e como sinais de relevância (gênero, diretor, elenco, ano,
nota média, nº de avaliações).

### 1.3 Por que o Letterboxd é uma boa fonte

- **Escala:** catálogo na casa do milhão de itens — folga para superar a meta
  de 50 mil páginas.
- **Estrutura semântica:** cada página embute um bloco **JSON-LD**
  (`schema.org/Movie`), o que torna a extração de metadados robusta e estável.
- **Listagens paginadas** (`/films/by/rating/`, `/films/popular/`, por gênero)
  funcionam como excelentes **sementes** de coleta.

---

## 2. Descrição do Coletor (40%)

### 2.1 Tipo do coletor

Trata-se de um **crawler focado (*focused crawler*)**, e não de um crawler de
web aberta. Ele é **restrito a um único domínio** (`letterboxd.com`) e a um
**único tipo de recurso-alvo** (páginas de filme `/film/{slug}/`). A partir de
**sementes** (páginas de listagem), o coletor segue links de forma dirigida,
descartando qualquer URL fora do escopo.

É um coletor de **busca em largura (BFS)** sobre a fronteira, com dois tipos de
nó:
- **`list`** — páginas de listagem paginadas; produzem *novos links* de filme e
  a próxima página da lista;
- **`film`** — páginas de filme; produzem *documentos* (metadados).

### 2.2 Arquitetura (visão geral)

```
           seeds (listas)
                │
                ▼
        ┌───────────────┐   URLs        ┌──────────────┐
        │   FRONTEIRA    │──────────────▶│   Workers    │
        │ (fila + dedup) │◀──────────────│ (threads)    │
        └───────────────┘  novos links   └──────┬───────┘
                ▲                                │
                │ checkpoint                     ▼
        ┌───────┴────────┐            ┌────────────────────┐
        │    Storage     │◀───────────│ Fetcher  +  Parser │
        │  SQLite + HTML │  metadados └────────────────────┘
        └────────────────┘
```

- **Fetcher** (`fetcher.py`): baixa páginas com polidez e tolerância a falhas.
- **Parser** (`parser.py`): descobre links e extrai metadados (JSON-LD + HTML).
- **Storage** (`storage.py`): persiste metadados (SQLite), HTML bruto (disco) e
  o estado do crawler.
- **Crawler** (`crawler.py`): orquestra a fronteira, os workers e o critério de
  parada.

### 2.3 Propriedades e políticas

#### Política de seleção (o que coletar)
- Somente URLs do domínio `letterboxd.com`.
- Somente páginas de filme como documentos; listagens servem apenas para
  descoberta de links.
- URLs **canônicas**: `/film/{slug}/` normalizada (remove sufixos e parâmetros),
  o que evita coletar variações da mesma página.

#### Política de polidez (não sobrecarregar o servidor)
- **User-Agent identificável**, com contato do grupo (transparência).
- **Respeito ao `robots.txt`** (habilitado por padrão): antes de baixar,
  verifica-se `can_fetch`.
- **Crawl-delay** configurável entre requisições **por worker**, com **jitter**
  aleatório para suavizar o padrão de acesso.
- **Concorrência limitada** (poucos workers) — decisão consciente de trocar
  velocidade por polidez.

#### Política de re-visita
- Coleta **única** (*snapshot*): cada URL é visitada uma só vez. O conjunto de
  URLs visitadas é mantido em memória e **persistido em SQLite**, garantindo
  deduplicação mesmo entre execuções.

#### Tolerância a falhas
- **Timeout** por requisição.
- **Retry com *backoff* exponencial + jitter** para erros **transitórios**
  (429, 500, 502, 503, 504); honra o cabeçalho **`Retry-After`**.
- Erros **definitivos** (404/403/410) **não** são re-tentados.
- Exceções em uma página **não derrubam** o worker; a falha é **registrada**
  (tabela `failures`) para auditoria.

#### Critério de parada
O crawl encerra quando **qualquer** condição ocorre:
1. **Meta de documentos atingida** (padrão: **50.000** páginas de filme) — este
   é o critério principal, alinhado ao quesito Escala;
2. **Fronteira esgotada** (não há mais URLs a visitar);
3. **Interrupção manual** (Ctrl+C) — o estado é salvo e a coleta pode ser
   retomada depois.

Há ainda limites de segurança: tamanho máximo da fronteira e número máximo de
páginas de listagem por semente.

#### Checkpointing / retomada
O estado (fronteira pendente + URLs visitadas + documentos já salvos) é
persistido periodicamente. Ao reiniciar, o coletor **retoma exatamente de onde
parou**, sem recomeçar do zero nem re-coletar páginas.

### 2.4 Extração de conteúdo

A extração de metadados prioriza o bloco **JSON-LD `schema.org/Movie`** embutido
na página (fonte estruturada e estável), com **fallback** para seletores HTML
quando um campo não está no JSON-LD. Campos coletados por documento:

`url`, `slug`, `title`, `year`, `director`, `cast`, `genres`, `countries`,
`languages`, `runtime_min`, `rating_avg`, `rating_count`, `synopsis`,
`tagline`, `poster_url`.

O **HTML bruto é armazenado** em disco (opcional, ligado por padrão). Isso
permite **reprocessar** as páginas nas fases de Indexação e Recuperação — por
exemplo, extrair campos adicionais — **sem precisar coletar novamente**.

### 2.5 Justificativa das decisões de projeto

| Decisão | Justificativa |
|--------|---------------|
| Crawler **focado** (1 domínio, 1 alvo) | O problema de RI é sobre filmes; coletar a web aberta seria desperdício e ruído. |
| **Threads** (não processos) | A coleta é *I/O-bound* (espera de rede); threads bastam e são leves. |
| **SQLite** | Banco embarcado, transacional, sem servidor; suporta os milhões de linhas do trabalho e simplifica a entrega. |
| **JSON-LD primeiro** | Fonte estruturada e menos sensível a mudanças de layout do site que os seletores CSS. |
| **Guardar HTML bruto** | Desacopla coleta de extração; permite reindexar sem recoletar (economia e reprodutibilidade). |
| **Checkpointing** | Coletas de 50k+ páginas levam horas; retomar após falha/pausa é essencial. |
| Polidez (delay + robots) | Evita bloqueios e respeita o servidor — boa prática e requisito ético do quesito. |

---

## 3. Escala (30%)

### 3.1 Meta

A pontuação máxima do quesito exige **mais de 50 mil páginas coletadas**. O
coletor foi configurado com **`target_pages = 50000`** por padrão, e as
sementes escolhidas (listagens gerais + por gênero) dão acesso a **muito mais**
que isso: cada página de listagem expõe ~72 filmes, e há milhares de páginas de
listagem disponíveis.

### 3.2 Estimativa de tempo

Com `request_delay = 1s` e `4 workers`, o *throughput* teórico é ~4
requisições/s. Considerando ~1 página de listagem para cada ~72 filmes, a
maioria esmagadora das requisições são páginas de filme:

- 50.000 páginas ÷ 4 req/s ≈ **3,5 horas** de coleta (ordem de grandeza).

O tempo real varia com a latência do site e os *retries*. Parâmetros como
`--workers` e `--delay` permitem ajustar velocidade × polidez.

### 3.3 Como comprovar a escala coletada

O número de documentos coletados pode ser verificado a qualquer momento:

```bash
sqlite3 data/letterboxd.db "SELECT COUNT(*) FROM films;"
```

O log (`crawler.log`) também reporta o progresso continuamente
("Progresso: N filmes coletados").

---

## 4. Como executar

```bash
# 1) Instalar dependências
pip install -r requirements.txt

# 2) Teste rápido (recomendado antes do crawl grande)
python run_coletor.py --target 100 --workers 2 --delay 1.5

# 3) Coleta completa (>50 mil), exportando o JSONL ao final
python run_coletor.py --target 50000 --workers 4 --export

# 4) Retomar após interrupção: basta rodar de novo (lê o estado do banco)
python run_coletor.py --target 50000 --workers 4

# 5) Exportar os documentos já coletados para a fase de Indexação
python run_coletor.py --export-only
```

**Saídas geradas** (dentro de `data/`):
- `letterboxd.db` — banco SQLite com os metadados e o estado do crawler;
- `raw_html/` — HTML bruto de cada página (para reprocessamento);
- `films.jsonl` — um documento por linha (entrada para a Parte 2 — Indexação);
- `crawler.log` — log de execução.

---

## 5. Limitações e trabalhos futuros

- O Letterboxd pode alterar o layout ou adotar medidas anti-bot mais fortes; os
  seletores de *fallback* podem precisar de ajuste. O uso de JSON-LD mitiga
  isso.
- A coleta atual é um *snapshot* (sem re-visita/atualização incremental) — o que
  é adequado para o escopo do trabalho.
- Na Parte 2, o `films.jsonl` será a entrada do indexador (índice invertido +
  ponderação TF-IDF/BM25).
