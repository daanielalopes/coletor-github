# Relatório Final — Parte 3: Recuperação, Ranking e Interface

Sistema de busca de projetos de software livre (GitHub e SourceForge).
Este relatório descreve a etapa final: a **recuperação** da informação a
partir do índice invertido, o **ranking** por relevância e a **interface
gráfica** apresentada ao usuário. Ele complementa os relatórios das etapas
anteriores (`RELATORIO_PARTE1_COLETOR.md` e `RELATORIO_PARTE2_INDEXACAO.md`)
e consolida as melhorias feitas depois da entrega parcial.

---

## 1. Visão geral do sistema

O sistema tem três partes, ligadas por arquivos no disco (sem banco de dados
compartilhado):

```
   páginas web                 data/projetos.jsonl              data/indice/
  (GitHub, SF)   ──coletor──▶   (um projeto por linha)  ──indexador──▶  índice invertido
                                                                            │
                                            consulta do usuário             │
                        buscar.py (CLI)  ◀───────────────────────────── Indice + Buscador
                        interface/app.py (web)  ◀───────────────────────────┘
```

1. **Coletor** (Parte 1): coletor web clássico; baixa o HTML, segue links e
   exporta `data/projetos.jsonl`.
2. **Indexador** (Parte 2): pré-processa o texto e constrói o índice invertido
   com SPIMI, postings comprimidas (gaps + Variable Byte), posições e
   frequência por campo.
3. **Recuperação e interface** (Parte 3, este relatório): lê o índice, ranqueia
   os documentos por BM25/BM25F e apresenta o resultado ao usuário por linha de
   comando (`buscar.py`) e por uma interface gráfica web (`interface/app.py`).

Todo o código é em Python. O indexador, a recuperação e a interface rodam só
com a **biblioteca padrão** (ver seção 8).

---

## 2. Recuperação pelo índice invertido

A recuperação está em `indexador/indice.py` (classe `Indice`). O ponto central
do critério de avaliação é: **a busca consulta o índice invertido, e não faz
uma varredura dos documentos nem uma busca simplificada à parte.**

Como funciona, para cada termo da consulta:

1. **Análise idêntica à da indexação.** A consulta passa pelo mesmo analisador
   do indexador (`Indice.termos_da_consulta`), então "C++" vira `cpp`,
   "machine learning" vira `machin learn` etc. Isso garante que a consulta caia
   no mesmo vocabulário do índice.
2. **Léxico por partição (hash).** O léxico é dividido em 16 partições por
   `crc32(termo) % 16`. Só a partição do termo pedido é carregada
   (`Indice.lexico`/`Indice.particao`); não se carrega o vocabulário inteiro
   (779 mil termos no índice completo) para responder a uma consulta.
3. **Leitura direcionada das postings.** A entrada do léxico guarda o
   deslocamento e o tamanho da lista do termo. `Indice.postings` faz
   `f.seek(offset); f.read(n)` e lê **só os bytes daquele termo**, decodificando
   os gaps (Variable Byte) para reconstruir as unidades e as frequências por
   campo. As posições (`posicoes_XXX.bin`) só são lidas quando a consulta
   precisa delas (frase), porque ficam num arquivo separado.

Essa é a definição de recuperação por índice invertido: da consulta vai-se
direto às listas de documentos de cada termo, sem olhar os documentos que não
contêm os termos.

**Prova prática.** O comando `python buscar.py --termo "machine learning"`
(e o endpoint `/api/termo` na interface) mostra a entrada de cada termo lida do
índice. Exemplo real, no índice de amostra (100 projetos):

```
termo 'machin' (partição 14): df=6 cf=14
  campos: ['nome', 'descricao', 'rotulos', 'readme']
  unidade  9  tf=(1, 2, 2, 3)  .../advanced-machine-learning-engineer-roadmap-2024
  unidade 22  tf=(0, 1, 0, 1)  .../nexus-zkvm
  ...
termo 'learn'  (partição 12): df=12 cf=39
  unidade  0  tf=(0, 1, 0, 3)  .../system-design-primer
  ...
```

O teste `tests/test_indexador.py` confirma, termo a termo, que essas listas
coincidem exatamente com um índice calculado por força bruta — ou seja, a
recuperação está correta.

---

## 3. Ranking por relevância (BM25 / BM25F)

O ranking está em `indexador/busca.py` (classe `Buscador`). Usamos a família
**BM25** (Robertson & Spärck Jones), hoje o modelo probabilístico padrão de
recuperação, com a extensão **BM25F** (Robertson & Zaragoza, 2009) para dar
pesos diferentes aos campos do documento.

### 3.1 IDF

A importância de um termo cai com o número de documentos em que ele aparece.
Usamos o IDF probabilístico do BM25:

```
idf(t) = log( 1 + (N - df(t) + 0.5) / (df(t) + 0.5) )
```

- `N`: número de unidades indexadas;
- `df(t)`: em quantas unidades o termo aparece.

O `+1` externo evita IDF negativo para termos muito comuns (df > N/2), problema
clássico da fórmula original do BM25.

### 3.2 Saturação da frequência (BM25)

A frequência de um termo no documento (`tf`) contribui com retornos
decrescentes: a 10ª ocorrência vale menos que a 2ª. O BM25 modela isso com

```
       tf · (k1 + 1)
peso = ───────────────            (k1 = 1.2)
         tf + k1
```

Na implementação usamos a forma equivalente `idf · tf / (k1 + tf)` (a constante
`(k1+1)` é um fator comum que não muda a ordenação). O `k1 = 1.2` é o valor
usual da literatura.

### 3.3 Normalização pelo comprimento e pesos de campo (BM25F)

Documentos longos tendem a ter `tf` maior só por serem longos. O BM25 corrige
isso normalizando pelo comprimento da unidade em relação ao comprimento médio:

```
norm = 1 - b + b · (comprimento / comprimento_médio)      (b = 0.75)
```

No **BM25F** (granularidade "campo", padrão), cada campo é normalizado pelo seu
próprio comprimento médio, ponderado pelo peso do campo e **somado antes da
saturação**:

```
tf_f = Σ_campo  peso_campo · tf_campo / norm_campo
nota(d) = Σ_termo  idf(t) · qtf(t) · tf_f / (k1 + tf_f)
```

- `qtf(t)`: quantas vezes o termo aparece na própria consulta;
- somar por campo **antes** da saturação é o que diferencia o BM25F de
  simplesmente ranquear cada campo à parte: um termo que aparece no nome *e* na
  descrição conta junto, com os respectivos pesos.

Pesos provisórios usados (em `busca.py`):

| Campo     | Peso | Motivo |
|-----------|------|--------|
| nome      | 3.0  | o nome do projeto é o sinal mais forte de relevância |
| descrição | 2.0  | resumo curto e direto do projeto |
| rótulos   | 2.0  | tópicos/categorias/linguagem, muito discriminativos |
| README    | 1.0  | texto longo, ruidoso; peso de base |

### 3.4 Granularidades

- **"campo"** (padrão): uma unidade por projeto, com a frequência de cada campo
  separada → **BM25F**.
- **"documento"**: uma unidade por projeto, todos os campos juntos → **BM25**
  clássico.
- **"chunk"**: o README é cortado em janelas; a nota do projeto é a da sua
  melhor janela (**MaxP**, *max passage*), útil para READMEs longos.

### 3.5 Efeito do ranking (resultados reais)

Consulta `static site generator` no índice de amostra:

```
 1.  7.83  [github] tumblelog         A static tumblelog generator (Perl e Python)
 2.  3.23  [github] HibiAPI           ...APIs for a variety of commonly used sites
 3.  2.44  [github] sitemap.js        Sitemap-generating framework for node.js
```

O 1º lugar tem os três termos, dois deles no **nome/descrição** ("static ...
generator"), e ganha de projetos que só têm "site" ou "generator" soltos — é
exatamente o efeito esperado do BM25F com peso maior para nome e descrição.

---

## 4. Interface com o usuário

### 4.1 Decisão: interface web com a biblioteca padrão

O trabalho pede uma interface gráfica para o usuário. Optamos por uma
**interface web** servida por `interface/app.py`, por três razões:

1. **Zero dependências:** usa só `http.server` da biblioteca padrão do Python.
   Não precisa instalar Flask, Django nem Node; roda em qualquer máquina só com
   o Python (reforça o critério de facilidade de instalação).
2. **Acessível:** abre no navegador (`http://localhost:8000`), sem instalar
   cliente nenhum, em qualquer sistema operacional.
3. **Open source:** todo o código é nosso e está no repositório.

### 4.2 A interface usa o mesmo mecanismo de busca

Este é o ponto mais importante do ponto de vista da avaliação: a interface
**não tem busca própria**. No início, o servidor carrega uma instância de
`Indice` e uma de `Buscador` (as mesmas classes usadas por `buscar.py`) e toda
consulta é atendida por `Buscador.buscar(...)`. Os endpoints são:

- `GET /` — a página HTML (uma só página, com HTML/CSS/JS embutidos);
- `GET /api/buscar?q=...&k=...` — chama o `Buscador` e devolve os resultados
  ranqueados **mais** a entrada do índice (df, cf, partição) de cada termo da
  consulta;
- `GET /api/termo?t=...` — devolve a entrada do léxico e as primeiras postings
  do termo, lidas do índice (o mesmo que `buscar.py --termo`);
- `GET /api/info` — estatísticas do índice carregado.

O teste `tests/test_busca.py::TestInterfaceWeb::test_busca_igual_ao_buscador`
verifica automaticamente que a lista de URLs devolvida pela API é **idêntica,
na mesma ordem**, à do `Buscador` chamado diretamente. Ou seja, está provado em
teste que a interface não faz uma busca diferente ou simplificada.

### 4.3 O que o usuário vê

A cada busca, a interface mostra:

- os resultados ranqueados, com posição, **nota**, nome com link, site,
  linguagem, licença, estrelas e um trecho da descrição;
- os **termos em que a consulta foi analisada** (ex.: "c++" → `cpp`), cada um
  com o seu df e cf no índice;
- clicando num termo, abre-se o **detalhe da entrada no índice invertido**
  (partição, df, cf e as primeiras postings com a frequência por campo) — para
  que o avaliador veja, na própria interface, que a busca vem do índice.

A figura abaixo é uma captura real da interface para a consulta
"machine learning" sobre o índice de amostra (arquivo
`evidencias/interface/busca_machine_learning.png`):

![Interface web](evidencias/interface/busca_machine_learning.png)

---

## 5. Integração entre as partes

As três partes se integram pelos arquivos no disco, o que as mantém
desacopladas e permite testar cada uma isoladamente:

- **coletor → indexador:** o coletor exporta `data/projetos.jsonl`; o indexador
  lê esse arquivo (`indexador/documentos.py`), unificando os campos de GitHub e
  SourceForge em quatro campos comuns (nome, descrição, rótulos, README).
- **indexador → busca:** o indexador grava `data/indice/` (postings, posições,
  léxico, documentos, comprimentos, meta); `Indice` lê essa pasta e `Buscador`
  ranqueia.
- **busca → usuário:** `buscar.py` (CLI) e `interface/app.py` (web) são duas
  "cascas" sobre o mesmo par `Indice` + `Buscador`.

Verificamos a integração de ponta a ponta nesta revisão: a partir da amostra de
100 projetos (`evidencias/amostra_projetos.jsonl`), construímos o índice com
`run_indexador.py`, e rodamos consultas reais tanto no `buscar.py` quanto na
interface web — com resultados idênticos.

---

## 6. Testes automatizados

A suíte roda com `python -m unittest discover -s tests -v`. Nesta máquina:
**28 testes, menos de 1 segundo** (1 pulado — a comparação opcional com o
pacote `snowballstemmer`, que não estava instalado).

| Arquivo | O que cobre |
|---------|-------------|
| `tests/test_indexador.py` | Variable Byte (ida e volta, tamanhos, exemplos do livro); analisador (termos técnicos, limpeza, camelCase, ideogramas, stopwords, stemming); **índice contra força bruta** — compara postings, posições, df e cf termo a termo nas três granularidades. |
| `tests/test_busca.py` | **Ranking:** recupera só documentos que têm o termo; peso de campo (nome > descrição > README); mais ocorrências ranqueia acima; IDF decresce com o df; notas em ordem decrescente; respeita `k`. **Interface web:** API devolve o mesmo que o `Buscador`, expõe df/cf do índice e as postings; consulta vazia devolve 400. |
| `tests/test_porter2.py` | Stemmer Porter2 interno contra valores de referência do algoritmo e, se disponível, contra o `snowballstemmer`. |

O teste de maior valor para esta etapa é o `test_busca_igual_ao_buscador`:
ele garante, de forma automática, que a interface usa o mecanismo de busca do
sistema e não uma busca à parte.

---

## 7. Decisões de projeto e melhorias após a entrega parcial

### 7.1 BM25F em vez de TF-IDF/cosseno

**Alternativa considerada:** modelo vetorial com TF-IDF e similaridade do
cosseno. **Escolha:** BM25F. **Vantagem:** o BM25 satura a frequência (não
premia repetição exagerada) e normaliza o comprimento de forma controlada por
`b`; o BM25F ainda dá peso por campo, essencial aqui porque o nome e a
descrição de um projeto valem muito mais que o README. **Desvantagem:** três
parâmetros (`k1`, `b`, pesos) a calibrar; adotamos os valores usuais da
literatura (`k1=1.2`, `b=0.75`) e pesos provisórios, deixando a calibração com
julgamentos de relevância como trabalho futuro.

### 7.2 Interface web sem framework

**Alternativa:** Flask/Streamlit. **Escolha:** `http.server` da biblioteca
padrão. **Vantagem:** nenhuma dependência nova, instalação trivial, roda em
qualquer máquina. **Desvantagem:** sem recursos prontos de um framework (rotas,
templates); como a interface é pequena (uma página e quatro endpoints), isso não
pesou.

### 7.3 Melhoria após a entrega parcial — stemmer opcional (portabilidade)

Na entrega parcial, o indexador dependia obrigatoriamente do pacote
`snowballstemmer`. Numa máquina sem internet (ou sem `pip install`), o sistema
simplesmente não rodava. Para corrigir, implementamos o **Porter2 (English
Snowball) em Python puro** (`indexador/porter2.py`) e o `analisador.py` passou
a usá-lo automaticamente quando o pacote não está instalado, emitindo um aviso.
Assim o sistema inteiro (indexador + busca + interface) roda **só com a
biblioteca padrão**. O stemmer interno coincide com o pacote na quase totalidade
das palavras (ver `tests/test_porter2.py`); quando o pacote está presente, ele
continua sendo usado (é um pouco mais rápido).

### 7.4 Melhoria após a entrega parcial — testes do ranking e da interface

A entrega parcial testava o índice (leitura das postings), mas não o ranking
nem a camada de apresentação. Nesta etapa acrescentamos `tests/test_busca.py`,
que testa o comportamento do BM25F (peso de campo, saturação, IDF) e garante
que a interface web devolve exatamente o resultado do `Buscador`.

### 7.5 Separação postings/posições e compressão

Mantida da Parte 2 e relevante aqui: as posições ficam num arquivo separado das
postings, então uma consulta normal (sem frase) nunca lê nem decodifica
posições — a recuperação fica mais leve. A compressão (gaps + Variable Byte)
reduz o índice invertido de 183,6 MB (sem compressão) para 91,8 MB no índice
completo.

---

## 8. Bibliotecas externas

| Parte | Biblioteca | Uso | Obrigatória? |
|-------|-----------|-----|--------------|
| Coletor | `requests`, `protego`, `beautifulsoup4`, `lxml` | baixar e parsear HTML, ler robots.txt | sim, só para coletar da internet |
| Indexador | `snowballstemmer` | stemmer de inglês | **não** — há o Porter2 interno |
| Indexador | `psutil` | medir memória de pico | não (cai para `resource`) |
| Experimentos | `numpy`, `matplotlib` | gráficos do relatório | não |
| Recuperação + interface | — | só biblioteca padrão | — |

---

## 9. Números do sistema

**Índice completo** (coleta real de 52.000 projetos, em
`evidencias/indexacao/indice_principal.txt`):

| Métrica | Valor |
|---------|-------|
| Documentos (projetos) | 52.000 |
| Vocabulário (termos) | 779.148 |
| Postings (pares termo-unidade) | 9.783.738 |
| Ocorrências (tokens) | 25.575.077 |
| Maior lista (df) | 30.228 |
| Tempo total de indexação | 97,8 s |
| Memória de pico | 216 MB |
| Índice invertido (comprimido) | 91,8 MB (vs 183,6 MB sem compressão) |
| Índice total em disco | 118,7 MB |

**Índice de amostra** usado na demonstração desta revisão (100 projetos de
`evidencias/amostra_projetos.jsonl`): 2.815 termos, 4.839 postings, 7.187
ocorrências; cada consulta responde em cerca de 1 ms.

---

## 10. Conclusão

O sistema cobre o ciclo completo de recuperação de informação: coleta,
indexação com índice invertido comprimido, recuperação direcionada pelo índice,
ranking por BM25/BM25F e apresentação ao usuário por linha de comando e por uma
interface gráfica web. A recuperação é comprovadamente feita pelo índice
invertido (testes contra força bruta e o detalhe de postings na própria
interface), e a interface usa o mesmo mecanismo de busca do sistema (garantido
por teste). As melhorias feitas após a entrega parcial — stemmer opcional e
testes de ranking/interface — aumentaram a portabilidade e a confiança no
sistema.
