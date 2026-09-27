# Sistema de Recuperação da Informação — Parte 1: Coletor

**Fonte de dados:** GitHub (via API REST oficial — `api.github.com`)
**Documento coletado:** repositórios públicos (+ perfis dos proprietários)
**Linguagem:** Python 3
**Grupo:** Camila de Paula Rodrigues, Daniela da Silva Lopes, Luísa Ferreira Marques, Luisa Sapori e Thiago Lacerda Santos Barbosa


---

## 🎯 1. Proposta do Sistema de RI (30%)

### 1.1 O problema

O **GitHub** é a maior plataforma de hospedagem de código do mundo, com mais de
**400 milhões de repositórios** públicos. Encontrar projetos relevantes nesse
volume é uma necessidade real de desenvolvedores: "qual biblioteca resolve X?",
"que projetos de machine learning em Python existem?", "quero um exemplo de app
com tal framework". A busca nativa ajuda, mas é limitada e não permite
experimentar diferentes modelos de recuperação.

**Problema de RI:** dado um acervo de repositórios coletados do GitHub, permitir
que o usuário **recupere repositórios relevantes** a partir de uma necessidade
de informação — por **busca textual** (sobre nome, descrição e README) e por
**navegação facetada** (por linguagem, tópico, popularidade, licença).

### 1.2 A solução proposta

Um **Sistema de RI de busca e navegacional** sobre repositórios, dividido nas
três etapas do trabalho:

| Etapa | Papel no sistema |
|-------|------------------|
| **1. Coletor** (esta entrega) | Adquirir o acervo de documentos (repositórios) via API. |
| **2. Representação/Indexação** | Pré-processar o texto (tokenização, normalização, remoção de *stopwords*, *stemming*) e construir um **índice invertido** ponderado (TF-IDF/BM25) sobre nome + descrição + README. |
| **3. Recuperação** | Atender consultas (modelo vetorial/BM25) e oferecer navegação por facetas, ordenando por relevância (podendo combinar similaridade textual com popularidade). |

**Documento (unidade de recuperação):** um repositório. Reúne um campo textual
principal (descrição + README) e campos estruturados usados como
facetas/sinais de relevância (linguagem, tópicos, estrelas, forks, licença).

### 1.3 Por que o GitHub é uma boa fonte

- **Escala:** centenas de milhões de repositórios — folga enorme para superar
  a meta de 50 mil documentos.
- **API oficial e estruturada:** retorna **JSON limpo**, sem necessidade de
  *parsing* de HTML e **sem bloqueio anti-bot**.
- **Metadados ricos:** descrição, README (texto longo), linguagem, tópicos,
  estrelas, forks, datas, licença e o proprietário — ideais para busca textual
  e navegação facetada.

---

## ⚙️ 2. Descrição do Coletor (40%)

### 2.1 Tipo do coletor

Trata-se de um **coletor baseado em API** (*API harvester*), **focado** em um
único serviço (`api.github.com`) e em um **tipo de recurso-alvo**
(repositórios). Não é um crawler de HTML que segue *links*; ele consome a
**Search API** de forma paginada e sistemática. De cada repositório, também
extrai o **proprietário** (perfil de usuário/organização), armazenado de forma
deduplicada.

### 2.2 Arquitetura (visão geral)

```
   Gerador de PARTIÇÕES (por nº de estrelas)
                │  cria a fronteira
                ▼
        ┌────────────────┐   partição      ┌──────────────┐
        │   FRONTEIRA     │────────────────▶│   Coletor    │
        │ (partitions DB) │◀────────────────│  (paginação) │
        └────────────────┘  próxima página  └──────┬───────┘
                ▲                                   │  JSON
                │ checkpoint                        ▼
        ┌───────┴────────┐              ┌────────────────────┐
        │    Storage     │◀─────────────│  Fetcher (API)     │
        │  SQLite+README │  repos+users └────────────────────┘
        └────────────────┘
```

- **Fetcher** (`fetcher.py`): fala com a API (autenticação, *rate limit*,
  *retry*).
- **Crawler** (`crawler.py`): gera as partições, pagina a busca, normaliza o
  JSON e enriquece com README e proprietário.
- **Storage** (`storage.py`): persiste repositórios, usuários e o estado das
  partições (SQLite) + READMEs brutos em disco.

### 2.3 Propriedades e políticas

#### Política de seleção (o que coletar)
- Somente a API `api.github.com`.
- Documento-alvo: repositórios com **pelo menos 1 estrela** (`stars:>=1`) —
  decisão de projeto para focar em conteúdo minimamente relevante e reduzir
  ruído/spam.
- Deduplicação por **`id` numérico** do repositório (chave primária) e por
  `login` do usuário.

#### Política de autenticação e polidez (rate limit)
- **Token pessoal** (Bearer) — eleva o limite de **60 → 5.000 requisições/hora**.
  O token é lido de variável de ambiente/`.env` e **nunca** vai para o código.
- **User-Agent** obrigatório e versão da API fixada (boas práticas do GitHub).
- **Respeito ativo ao *rate limit*:** o coletor lê os cabeçalhos
  `X-RateLimit-Remaining`/`X-RateLimit-Reset` e **dorme** até a janela reabrir
  quando a cota se esgota; também honra `Retry-After` (limite secundário/abuso).
- **Delay + jitter** entre requisições e **um único worker** — a Search API não
  recomenda concorrência alta.

#### Política de re-visita
- Coleta **única** (*snapshot*). Partições concluídas vão para
  `done_partitions` e **não** são reprocessadas.

#### Tolerância a falhas
- **Timeout** por requisição.
- **Retry com *backoff* exponencial + jitter** para erros transitórios
  (429, 500, 502, 503, 504) e para 403 de *rate limit*.
- Erros definitivos (404 — ex.: repositório sem README) **não** re-tentam.
- Falhas são **registradas** (tabela `failures`) para auditoria.

#### Critério de parada
Encerra quando **qualquer** condição ocorre:
1. **Meta de documentos atingida** (padrão: **50.000** repositórios) — critério
   principal, alinhado ao quesito Escala;
2. **Partições esgotadas** (todo o espaço de busca foi percorrido);
3. **Interrupção manual** — o estado é salvo e a coleta pode ser retomada.

#### Checkpointing / retomada
O progresso (página atual de cada partição, partições concluídas, repositórios
já salvos) é persistido periodicamente em SQLite. Ao reiniciar, o coletor
**retoma de onde parou**, sem recomeçar nem recoletar.

### 2.4 Estratégia de escala — o ponto central (superar o limite de 1.000)

A Search API do GitHub devolve **no máximo 1.000 resultados por consulta**
(10 páginas de 100). Para coletar **muito mais** que isso, aplicamos
**particionamento do espaço de busca**: dividimos a coleta em milhares de
consultas **disjuntas**, cada uma com ≤ 1.000 resultados, e somamos os itens.

Partição adotada: por **número exato de estrelas**. Para cada valor `S`, a
consulta é `stars:S`. Como cada valor de estrela isola um subconjunto pequeno
de repositórios, praticamente toda partição cabe no limite de 1.000 — e a soma
de milhares de partições cobre **muito além de 50 mil** repositórios. Os
parâmetros `--star-min`/`--star-max` controlam a faixa.

> Essa é a principal **decisão de projeto** do coletor: transforma um limite
> rígido da API (1.000/consulta) em uma coleta de escala arbitrária.

### 2.5 Dados extraídos por documento

`id`, `full_name` (owner/repo), `name`, `owner_login`, `description`,
**`readme`** (texto rico), `language`, `topics`, `stars`, `forks`, `watchers`,
`open_issues`, `size_kb`, `license_name`, `default_branch`, `homepage`,
`html_url`, `is_fork`, `created_at`, `updated_at`, `pushed_at`.

Além disso, cada **proprietário** é salvo (deduplicado): `id`, `login`, `type`
(User/Organization), `html_url`, `avatar_url`. O README bruto é gravado em
disco para permitir **reprocessamento** nas fases seguintes sem recoletar.

### 2.6 Justificativa das decisões de projeto

| Decisão | Justificativa |
|--------|---------------|
| **API oficial** (não *scraping*) | JSON estruturado, estável e sem bloqueio anti-bot; coleta confiável e legal. |
| **Repositórios** como documento | Texto rico (descrição + README) para busca + facetas (linguagem, tópico) para navegação. |
| **Particionar por estrelas** | Contorna o teto de 1.000 resultados/consulta da Search API, viabilizando 50k+. |
| **Token via env/.env** | Segurança: segredo fora do código versionado; eleva a cota para 5.000/h. |
| **Respeitar `X-RateLimit`** | Evita banimento temporário e é polidez com o serviço. |
| **SQLite + checkpoint** | Coletas longas (horas) precisam ser retomáveis; banco embarcado simples. |
| **Salvar README bruto** | Desacopla coleta de indexação; permite reindexar sem recoletar. |
| **Deduplicar usuários** | Entrega também "perfis" (citados no enunciado) sem custo extra de requisição. |

---

## 📈 3. Escala (30%)

### 3.1 Meta e viabilidade

A pontuação máxima exige **mais de 50 mil documentos**. O coletor usa
`target_pages = 50000` por padrão, e o particionamento por estrelas dá acesso a
**ordens de grandeza acima disso** (o GitHub tem centenas de milhões de repos).

### 3.2 Estimativa de tempo (com token)

Com token (5.000 req/h) e ~100 repos por página de busca:

- **Sem baixar README:** cada requisição de busca traz 100 repos. 50.000 repos
  ≈ 500 requisições de busca → **poucos minutos** (respeitando o *rate limit*).
- **Baixando README:** cada repo custa +1 requisição (endpoint `/readme`).
  50.000 READMEs ≈ 50.000 requisições → ~10 horas de relógio por causa do teto
  de 5.000/h (o coletor dorme e retoma automaticamente).

> Recomendação: para bater a meta rapidamente, rode com `--no-readme` primeiro
> (garante os 50k) e, se quiser o texto rico, rode depois com README ligado —
> a coleta é retomável.

### 3.3 Como comprovar a escala coletada

```bash
sqlite3 data/github.db "SELECT COUNT(*) FROM repositories;"
sqlite3 data/github.db "SELECT COUNT(*) FROM users;"
```

O log (`crawler.log`) reporta o progresso continuamente ("Progresso: N
repositorios").

---

## ▶️ 4. Como executar

```bash
# 1) Instalar dependências
pip install -r requirements.txt

# 2) Definir o token (grátis) — gere em https://github.com/settings/tokens
export GITHUB_TOKEN=ghp_xxx            # Linux/Mac
# $env:GITHUB_TOKEN="ghp_xxx"          # Windows PowerShell
# ou copie .env.example para .env e coloque o token lá

# 3) Teste rápido (200 repositórios)
python run_coletor.py --target 200

# 4) Coleta completa (>50 mil), sem README (rápida), exportando JSONL
python run_coletor.py --target 50000 --no-readme --export

# 5) Retomar após interrupção: basta rodar de novo
python run_coletor.py --target 50000

# 6) Exportar o que já foi coletado (fase de Indexação)
python run_coletor.py --export-only
```

**Saídas geradas** (em `data/`):
- `github.db` — SQLite com repositórios, usuários e estado do coletor;
- `raw_readme/` — READMEs brutos (reprocessamento);
- `repositories.jsonl` — um documento por linha (entrada da Parte 2);
- `crawler.log` — log de execução.

---

## 🔭 5. Limitações e trabalhos futuros

- A Search API limita 1.000 resultados/consulta; contornamos com
  particionamento por estrelas (poderíamos particionar também por data ou
  linguagem para granularidade ainda maior).
- Baixar READMEs multiplica as requisições; por isso é opcional (`--no-readme`).
- A coleta é um *snapshot* (sem atualização incremental) — adequado ao escopo.
- Na Parte 2, o `repositories.jsonl` será a entrada do indexador (índice
  invertido + ponderação TF-IDF/BM25).
