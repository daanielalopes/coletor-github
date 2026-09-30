# Sistema de Recuperação da Informação — Parte 1: Coletor

**Fontes de dados:** GitHub (`github.com`) e SourceForge (`sourceforge.net`)
**Método de coleta:** **crawler de HTML** (parsing do DOM das páginas públicas)
**Documento coletado:** repositórios/projetos públicos (+ perfis dos proprietários)
**Armazenamento:** somente **arquivos** (JSON Lines) — **sem banco de dados**
**Linguagem:** Python 3
**Grupo:** Camila de Paula Rodrigues, Daniela da Silva Lopes, Luísa Ferreira Marques, Luisa Sapori e Thiago Lacerda Santos Barbosa

---

## 🎯 1. Proposta do Sistema de RI (30%)

### 1.1 O problema

Repositórios de código-fonte estão espalhados por diversas plataformas —
**GitHub** (a maior, com centenas de milhões de repositórios) e **SourceForge**
(um dos diretórios de software livre mais antigos). Encontrar projetos
relevantes nesse volume é uma necessidade real: *"qual biblioteca resolve X?"*,
*"que projetos de um dado tema existem?"*, *"quero um exemplo com tal
tecnologia"*.

**Problema de RI:** dado um acervo de repositórios/projetos coletados da Web,
permitir **recuperar itens relevantes** a partir de uma necessidade de
informação — por **busca textual** (nome, descrição e README) e por
**navegação facetada** (linguagem, tópico/categoria, popularidade, licença).

### 1.2 A solução proposta

Um **Sistema de RI de busca e navegacional** sobre repositórios/projetos de
software, dividido nas três etapas do trabalho:

| Etapa | Papel |
|-------|-------|
| **1. Coletor** (esta entrega) | Adquirir o acervo, via **crawler de HTML**, de **duas fontes** (GitHub + SourceForge). |
| **2. Representação/Indexação** | Pré-processar o texto (tokenização, normalização, *stopwords*, *stemming*) e construir um **índice invertido** ponderado (TF-IDF/BM25). |
| **3. Recuperação** | Atender consultas (modelo vetorial/BM25) + navegação por facetas, ordenando por relevância. |

**Documento (unidade de recuperação):** um repositório/projeto. Reúne um campo
textual principal (descrição + README) e campos estruturados usados como
facetas/sinais (linguagem, tópicos/categorias, estrelas/popularidade, licença).

### 1.3 Por que duas fontes

Usar **GitHub e SourceForge** aumenta a **cobertura** (quesito de Qualidade) e
demonstra que o coletor **generaliza** para páginas HTML de estruturas
diferentes. As duas fontes convergem para o **mesmo formato de documento**
(um campo `source` identifica a origem), o que simplifica a indexação.

---

## ⚙️ 2. Descrição do Coletor (40%)

### 2.1 Tipo do coletor

É um **coletor vertical** (*focado*): não percorre a Web inteira seguindo links
arbitrários, mas **duas fontes específicas** e um **tipo de documento-alvo**
(repositórios/projetos). O mecanismo é o de um **web crawler de HTML**, exatamente
como no processo visto em aula: inicializa uma fronteira de *seeds*, baixa a
página (`GET`), **faz o parsing do HTML**, extrai os itens/URLs de interesse,
salva o conteúdo e avança. De cada documento também extrai o **proprietário**
(perfil), armazenado de forma deduplicada.

> **Incremento em relação à versão anterior:** antes a coleta era feita apenas
> pela **API** do GitHub (JSON). Agora o núcleo é um **crawler de HTML** que faz
> *parsing do DOM* — atendendo ao que o trabalho pede — e ganhou uma **segunda
> fonte** (SourceForge). A fonte por API do GitHub foi **mantida** como
> alternativa selecionável.

### 2.2 Arquitetura

```
        Gerador de PARTIÇÕES (seeds)                 ┌─────────────────┐
   GitHub: stars:1..5000  | SourceForge: facetas     │  Fontes (Source)│
                │ inicializa a fronteira             │  github_html    │
                ▼                                     │  sourceforge    │
        ┌────────────────┐   próxima partição         │  github_api     │
        │   FRONTEIRA     │──────────────────────────▶│ (listagem +     │
        │ (state/ em      │◀──────────────────────────│  parsing DOM +  │
        │  arquivos)      │   próxima página / done    │  detalhe)       │
        └───────┬────────┘                            └────────┬────────┘
                │ checkpoint (arquivos)                        │ HTML/JSON
                ▼                                              ▼
        ┌────────────────────┐  documentos+perfis   ┌────────────────────┐
        │  STORAGE (ARQUIVOS) │◀─────────────────────│  FETCHER            │
        │ JSONL + raw + state │                      │ robots.txt+delay+  │
        └────────────────────┘                       │ retry (HTML/JSON)  │
                                                      └────────────────────┘
```

- **Fetcher** (`fetcher.py`): baixa páginas (`get_html`) ou JSON (`get_json`);
  consulta `robots.txt`, aplica *delay*+*jitter* e *retry* com *backoff*.
- **Sources** (`sources/`): cada fonte sabe gerar suas partições, montar a URL
  da listagem, **fazer o parsing do HTML** (lista de itens e página de detalhe)
  e o proprietário. Interface comum em `base.py`.
- **Crawler** (`crawler.py`): motor genérico que orquestra as fontes, pagina as
  listagens, deduplica e salva.
- **Storage** (`storage.py`): persiste **em arquivos** (sem BD) e mantém o
  estado (fronteira/concluídas/vistos) para **retomar**.

### 2.3 Propriedades de coleta (Quality / Freshness / Volume)

Seguindo Baeza-Yates & Ribeiro-Neto (Modern IR):

- **Qualidade — Cobertura/Acurácia:** foco em repositórios/projetos (documentos
  úteis para busca), duas fontes para ampliar cobertura, e **seleção** que
  descarta duplicatas e itens irrelevantes.
- **Volume — Eficiência/Escalabilidade:** particionamento do espaço de busca
  (Seção 3) para escalar além de 50 mil, com *checkpoint* para execuções longas.
- **Atualização (Freshness):** *snapshot* — coleta **única** (cada URL é visitada
  uma vez). Adequado ao escopo (o acervo é uma "fotografia" para indexar).

### 2.4 Políticas

#### Política de seleção (o que coletar / o que seguir)
- **Documentos-alvo:** repositórios (GitHub) e projetos (SourceForge).
- **Seleção de links:** por **estrutura do HTML** — no GitHub, links de resultado
  no formato `/owner/repo` (rotas reservadas como `/search`, `/settings` são
  filtradas); no SourceForge, links `/projects/<slug>/`.
- **Seleção de documentos:** **deduplicação** por identificador
  (`full_name = owner/repo` no GitHub; `sourceforge/<slug>` no SourceForge) e por
  `login` do proprietário; itens sem página válida (404) são descartados.

#### Política de boas maneiras (polidez)
- **Identificação:** `User-Agent` em toda requisição.
- **robots.txt:** lido e **respeitado por domínio** (`urllib.robotparser`).
- **Controle de banda:** *delay* base + *jitter* entre requisições e **um único
  worker** sequencial (evita a proteção anti-bot / HTTP 429).

#### Política de re-visita (freshness)
- **Coleta única (snapshot).** Partições concluídas vão para
  `done_partitions.txt` e **não** são reprocessadas.

#### Tolerância a falhas
- **Timeout** por requisição; **retry com backoff exponencial + jitter** para
  erros transitórios (429, 500, 502, 503, 504); honra ao `Retry-After`.
- Erros definitivos (404) **não** re-tentam. Falhas são **registradas** em
  `state/failures.jsonl` (auditoria).

#### Critério de parada (limite offline)
Encerra quando **qualquer** condição ocorre:
1. **Meta de documentos atingida** (padrão **50.000**) — critério principal;
2. **Fronteira esgotada** (todas as partições processadas);
3. **Interrupção manual** — o estado é salvo e a coleta é **retomável**.

#### Checkpointing / retomada
A cada N itens (`checkpoint_every`) e ao concluir cada página, o estado é
gravado em `data/state/` (partição/página atual, concluídas, vistos). Ao
reiniciar, o coletor **retoma de onde parou**, sem recoletar.

### 2.5 Armazenamento sem banco de dados

**Restrição do trabalho:** proibido usar banco de dados (SQL ou NoSQL). Assim,
tudo é gravado em **arquivos**:

- `repositories.jsonl` — o acervo, **1 documento por linha** (JSON, *append-only*);
- `users.jsonl` — proprietários deduplicados;
- `raw_readme/…` — texto rico bruto (README/descrição) por documento;
- `state/…` — conjuntos `seen_*` (dedup/retomada), fronteira, concluídas, falhas.

**Justificativa:** JSON Lines escreve em O(1), não carrega tudo em memória, é
*streamável* para o indexador (Parte 2) e dispensa servidor/índice de banco. Os
conjuntos `seen_*` são carregados dos arquivos no início, garantindo
deduplicação e retomada **sem** qualquer SGBD.

### 2.6 Dados extraídos por documento

`full_name`, `source`, `name`, `owner_login`, `description`, **`readme`**
(texto rico), `language`, `topics`/categorias, `stars`/popularidade, `forks`,
`watchers`/downloads, `open_issues`, `license_name`, `default_branch`,
`homepage`, `html_url`, `is_fork` e datas (quando disponíveis no HTML).
Cada **proprietário**: `login`, `type`, `html_url`, `avatar_url`.

### 2.7 Justificativa das principais decisões

| Decisão | Justificativa |
|--------|---------------|
| **Crawler de HTML** (parsing do DOM) | Requisito do trabalho; lê as mesmas páginas de um usuário, sem depender de API. |
| **Duas fontes** (GitHub + SourceForge) | Amplia cobertura e mostra generalização do coletor para HTML diferente. |
| **Arquivos (JSONL), sem BD** | Restrição do trabalho; simples, *append-only*, streamável e retomável. |
| **Particionar por estrelas / facetas** | Contorna o teto de resultados navegáveis por consulta → viabiliza 50k+. |
| **robots.txt + delay + 1 worker** | Boas maneiras: polidez, respeito ao domínio, evita bloqueio anti-bot. |
| **Checkpoint em arquivos** | Coletas longas precisam ser retomáveis sem SGBD. |
| **Salvar README bruto** | Desacopla coleta de indexação (reindexar sem recoletar). |
| **Manter fonte por API** | Alternativa/segurança, selecionável por `--sources`. |

---

## 📈 3. Escala (30%)

### 3.1 Estratégia — superar o limite de resultados por consulta

Tanto a busca do GitHub quanto o diretório do SourceForge limitam quantos
resultados são navegáveis por consulta. A solução é **particionar** o espaço de
busca em milhares de consultas **disjuntas** (cada uma pequena) e **somar**:

- **GitHub** — por número **exato de estrelas**: `stars:1`, `stars:2`, …,
  `stars:5000` (5.000 partições disjuntas). Cada valor isola um subconjunto
  pequeno; a soma cobre muito além de 50 mil repositórios.
- **SourceForge** — por **faceta** do diretório: sistemas operacionais
  (`os:windows`, `os:linux`, …) e categorias (`development`, `internet`,
  `games`, …), cada uma paginada. Dezenas de facetas × muitas páginas.

> Essa é a principal **decisão de projeto de escala**: transforma um limite
> rígido de navegação em uma coleta de tamanho arbitrário.

### 3.2 Viabilidade e tempo

Com ~100 itens por página de listagem, alcançar 50.000 documentos exige a ordem
de **centenas de páginas de listagem** + a página de detalhe de cada documento.
Respeitando o *delay* de polidez (padrão ~2–3,5s/requisição, 1 worker), a coleta
completa leva horas — por isso é **retomável** e pode rodar por partes. Para
acelerar testes, use `--no-readme` (não baixa o texto rico) e/ou `--target` menor.

### 3.3 Como comprovar a escala coletada

```bash
wc -l data/repositories.jsonl      # nº de documentos coletados
wc -l data/users.jsonl             # nº de perfis (proprietários)
```

O log (`crawler.log`) reporta o progresso ("Progresso: N documentos").

---

## ▶️ 4. Como executar

```bash
pip install -r requirements.txt

# Teste rápido (200 documentos, duas fontes de crawler)
python run_coletor.py --target 200

# Coleta completa (>50 mil)
python run_coletor.py --target 50000 --export

# Somente uma fonte / incluindo a API do GitHub
python run_coletor.py --sources github_html
python run_coletor.py --sources sourceforge
python run_coletor.py --sources github_html sourceforge github_api   # API requer GITHUB_TOKEN

# Retomar após interrupção: rodar o mesmo comando
python run_coletor.py --target 50000
```

**Saídas** (em `data/`): `repositories.jsonl`, `users.jsonl`, `raw_readme/`,
`state/` (estado do coletor) e `crawler.log`.

**Testes dos parsers (offline):** `python -m pytest tests/ -q`

---

## 🔭 5. Limitações e trabalhos futuros

- O HTML dos sites muda com o tempo; os parsers usam **seletores com fallback**,
  mas podem exigir ajuste — os testes com *fixtures* ajudam a detectar quebras.
- Coleta é *snapshot* (sem atualização incremental) — adequado ao escopo.
- Poderíamos paralelizar por domínio (fila de Mercator) para ganhar eficiência,
  mantendo o *delay* por host.
- Na Parte 2, `repositories.jsonl` será a entrada do indexador (índice invertido
  + ponderação TF-IDF/BM25).
