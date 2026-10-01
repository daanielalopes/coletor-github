# Sistema de Recuperação da Informação, Parte 1: Coletor

**Tema:** busca de projetos de software livre
**Fontes:** GitHub (github.com) e SourceForge (sourceforge.net), coletados pelo HTML das páginas
**Documento coletado:** a página de um projeto
**Linguagem:** Python 3
**Grupo:** Camila de Paula Rodrigues, Daniela da Silva Lopes, Luísa Ferreira Marques, Luisa Sapori e Thiago Lacerda Santos Barbosa

---

## 🎯 1. Proposta do sistema

### 1.1 O problema

Existe uma quantidade enorme de software livre, espalhada por várias
plataformas. Quem procura uma ferramenta, por exemplo "um gerenciador de senhas
para Linux" ou "uma biblioteca Python para ler PDF", precisa pesquisar em cada
plataforma separadamente, cada uma com a sua própria busca e o seu próprio
jeito de organizar os projetos.

Duas plataformas concentram boa parte desse acervo e se complementam:

- o **GitHub** reúne a maior parte dos projetos novos e ativos, organizados
  por tópicos e com sinais de popularidade (estrelas e forks);
- o **SourceForge** guarda muitos projetos clássicos e programas prontos para
  baixar (7-Zip, KeePass, Notepad++...), organizados num diretório de
  categorias e com sinais de uso (downloads e avaliações).

Não existe um lugar que busque nas duas ao mesmo tempo.

**Problema de RI:** dada uma necessidade de informação escrita em linguagem
natural, recuperar as páginas de projeto mais relevantes, não importa em qual
das duas plataformas o projeto esteja.

### 1.2 A solução proposta

Um sistema de busca vertical sobre páginas de projetos de software livre,
construído nas três etapas do trabalho:

| Etapa | Papel no sistema |
|-------|------------------|
| **1. Coletor** (esta entrega) | Baixar as páginas de projeto do GitHub e do SourceForge seguindo links, e extrair os campos de cada projeto. |
| **2. Indexação** | Pré-processar o texto (tokenização, normalização, stopwords, stemming) e montar um índice invertido com pesos (TF-IDF ou BM25) sobre nome, descrição, resumo e README. |
| **3. Recuperação** | Responder consultas por relevância e permitir filtros pelos campos estruturados (linguagem, licença, tópicos, categorias, popularidade). |

**Documento (unidade de recuperação):** a página de um projeto, ou seja, um
repositório do GitHub (`github.com/dono/repo`) ou um projeto do SourceForge
(`sourceforge.net/projects/nome/`). Cada documento tem uma parte textual (nome,
descrição, resumo, README) e campos estruturados (linguagem, licença, tópicos
ou categorias, estrelas, forks, downloads, nota), que servem de filtros e de
sinais de relevância.

### 1.3 Por que esses dois sites

- **Volume:** o GitHub tem milhões de repositórios públicos. Só o sitemap do
  SourceForge lista cerca de 340 mil projetos (123 arquivos com cerca de 2.800
  projetos cada, contados durante a inspeção do site). Há folga para passar
  de 50 mil documentos.
- **Complementaridade:** projetos novos e de desenvolvedores (GitHub) e
  programas prontos para usuários finais (SourceForge).
- **Acesso:** as páginas de projeto são públicas, não exigem login, e o
  robots.txt dos dois sites permite coletá-las.
- **Estrutura previsível:** a URL de cada site já diz o tipo da página
  (`/dono/repo`, `/topics/...`, `/projects/nome/`, `/directory/...`), o que
  torna simples e confiável a seleção de links por expressão regular.

---

## ⚙️ 2. Descrição do coletor

### 2.1 Por que não foi usada a API

A primeira versão deste trabalho usava a API do GitHub. Ela foi descartada e
substituída por um coletor web clássico pelos seguintes motivos:

1. **Exigência do trabalho:** o coletor pedido é o modelo visto em aula, que
   baixa o HTML das páginas e segue os links. Com uma API não existe fila de
   URLs, extração de links, robots.txt, normalização de URLs nem política de
   seleção de links, que são justamente os conceitos que esta etapa avalia.
2. **O documento é a página:** o usuário do sistema vai abrir a página do
   projeto. Coletar a própria página garante que o documento indexado é o
   mesmo que o usuário vê.
3. **Um método só para os dois sites:** cada plataforma tem a sua API (quando
   tem), com formato, limites e autenticação próprios. O coletor de HTML trata
   o GitHub e o SourceForge do mesmo jeito.
4. **Sem token e sem truques de consulta:** a API do GitHub exige um token
   pessoal para ter volume e devolve no máximo 1.000 resultados por busca; a
   versão anterior precisava dividir as buscas por número de estrelas para
   contornar esse limite. O coletor de HTML não depende de conta nem de token.

O custo dessa escolha é que o HTML muda com mais frequência que uma API e
alguns dados não aparecem na página. A seção 2.7 explica como os seletores
foram escolhidos para resistir a mudanças e como tratamos o caso da linguagem
do repositório no GitHub.

### 2.2 Tipo do coletor: vertical e focado

O coletor é **vertical** e **focado**.

- **Vertical**, porque se limita a um domínio de conteúdo (software livre) e a
  dois sites escolhidos. Ele não tenta cobrir a web: links para qualquer outro
  domínio são descartados.
- **Focado**, porque dentro desses sites só segue links que levam a páginas de
  projeto ou a páginas que listam projetos (tópicos do GitHub, diretório e
  sitemaps do SourceForge). O foco é feito pelo padrão da URL, com expressões
  regulares, e não por um classificador de conteúdo, porque nesses dois sites a
  URL identifica o tipo da página com segurança. Além disso, a fila dá
  prioridade às páginas de projeto (seção 2.6).

Essa escolha gasta os pedidos só com páginas úteis. Um coletor genérico
nesses sites se perderia em milhões de páginas de issues, commits, arquivos e
downloads, que não são documentos do nosso sistema.

### 2.3 Arquitetura

```
             seeds  +  sitemaps listados no robots.txt
                              |
                              v
   +------------------------ SQLite ------------------------+
   |  fila (github)        fila (sourceforge)               |
   |  conhecidas           visitadas        projetos        |
   +--------------------------------------------------------+
        | próxima URL                    ^ visita, campos e links novos
        v                                |
   +----------------+           +--------------------+
   | thread github  |           | thread sourceforge |    (em paralelo)
   +----------------+           +--------------------+
   cada thread:  robots.txt (protego) -> GET -> extração -> blocos gzip
```

Cada thread repete o laço visto em aula:

1. pega a próxima URL da fila do seu domínio;
2. confere o robots.txt e baixa o HTML com GET;
3. salva o conteúdo: o HTML bruto compactado e, se for página de projeto, os
   campos extraídos;
4. extrai os links da página;
5. coloca na fila só os links novos (que não estão no conjunto de URLs
   conhecidas) e que passam no filtro;
6. repete até atingir a meta ou a fila acabar.

| Módulo | Papel |
|--------|-------|
| `coletor/urls.py` | normalização de URLs e filtro de links (regex de cada site) |
| `coletor/robots.py` | leitura do robots.txt com a biblioteca protego |
| `coletor/fetcher.py` | GET com User-Agent, espera entre pedidos e backoff |
| `coletor/extractors.py` | extração de links e dos campos das páginas de projeto |
| `coletor/sites.py` | seeds de cada site |
| `coletor/storage.py` | SQLite e blocos de HTML em gzip |
| `coletor/crawler.py` | laço do coletor, uma thread por domínio |
| `coletor/stats.py` | estatísticas da coleta |

### 2.4 Propriedades priorizadas: qualidade e volume acima de atualização

Um coletor não consegue maximizar ao mesmo tempo qualidade, volume e
atualização, porque todos disputam o mesmo recurso: os pedidos que podemos
fazer sem sobrecarregar os sites. Com a espera de 1 segundo, cada site recebe
no máximo cerca de 3.600 pedidos por hora. Priorizamos **qualidade** e
**volume**:

- **Volume**, porque a meta do trabalho é passar de 50 mil documentos e porque
  um acervo maior aumenta a chance de o projeto que o usuário procura estar
  na coleção (revocação).
- **Qualidade**, porque um sistema de busca de projetos só é útil se os
  documentos forem páginas de projeto de verdade, com os campos preenchidos e
  sem repetição. Por isso: as seeds levam primeiro aos projetos mais
  relevantes (tópicos ordenados por estrelas, diretório ordenado por
  popularidade), o filtro de links descarta tudo que não é projeto ou
  listagem, e páginas duplicadas e de erro são descartadas.
- **Atualização ficou em segundo plano**, porque a descrição, o README e as
  categorias de um projeto mudam devagar, em escala de meses. Para quem
  procura "um editor de Markdown", uma página coletada há algumas semanas
  continua útil. Revisitar páginas gastaria pedidos que rendem mais coletando
  páginas novas. A coleta é, portanto, uma fotografia única do acervo
  (seção 2.9).

### 2.5 Seeds

**GitHub (1.501 seeds)**

- `github.com/topics`, a página que lista os tópicos em destaque;
- as páginas de 30 tópicos populares (python, javascript, machine-learning,
  java, linux, typescript, go, rust, cpp, c, php, ruby, android, docker, react,
  nodejs, deep-learning, security, database, kubernetes, api, cli,
  game-engine, swift, kotlin, csharp, data-visualization, compiler, emulator,
  bioinformatics), com a paginação `?page=1` até `?page=50`.

Cada página de tópico mostra 20 repositórios ordenados por estrelas. Durante a
inspeção verificamos que o GitHub serve no máximo 50 páginas por tópico (a
página 51 devolve 404), por isso o limite de 50.

**SourceForge (380 seeds, mais os sitemaps)**

- `sourceforge.net/directory/` e 18 categorias principais do diretório
  (software-development, system, internet, games, multimedia, business,
  scientific-engineering, communications, artificial-intelligence, education,
  database, security, formats-and-protocols, desktop-environment, text-editors,
  linux, windows, mac), com a paginação `?page=1` até `?page=20`. Cada página
  mostra 25 projetos ordenados por popularidade;
- os sitemaps listados no robots.txt do SourceForge que levam a projetos:
  `sitemap.xml` (índice com 123 arquivos, cada um com cerca de 2.800 URLs de
  projeto) e `directory_sitemap.xml` (páginas do diretório). Os outros
  sitemaps listados (blog, artigos, software comercial, freeware) não têm
  páginas de projeto e são descartados pelo filtro.

As seeds são intercaladas por página: primeiro a página 1 de todos os tópicos
(ou categorias), depois a página 2 de todos, e assim por diante.

**Justificativa:** páginas de tópico e de diretório são "hubs": cada uma aponta
para 20 ou 25 páginas de projeto, já ordenadas por relevância. Começar por elas
traz primeiro os projetos mais conhecidos e bem documentados (qualidade). A
intercalação cobre vários assuntos desde o início, em vez de esgotar um tópico
antes de começar o próximo. Os sitemaps garantem volume e alcançam a cauda
longa de projetos menos populares, além de garantir que a fila do SourceForge
nunca acabe antes da meta.

### 2.6 Política de seleção de links

Todo link encontrado passa por três etapas antes de entrar na fila.

**1. Normalização**, para não coletar a mesma página duas vezes com endereços
diferentes:

- resolve links relativos a partir da página de origem;
- usa sempre `https`, host em minúsculas, sem `www.` e sem porta;
- remove o fragmento (`#readme`);
- remove parâmetros de rastreio (`utm_*`, `ref`, `source`, `fbclid`...) e
  `page=1`, que é a mesma página sem o parâmetro;
- padroniza a barra final conforme a forma canônica de cada site: sem barra no
  GitHub (`github.com/psf/requests`) e com barra no SourceForge
  (`sourceforge.net/projects/sevenzip/`), que redireciona para a versão com
  barra;
- no GitHub, coloca o caminho em minúsculas. Verificamos que o site ignora
  maiúsculas em nomes de dono e repositório: `/PSF/Requests` e `/psf/requests`
  devolvem a mesma página.

**2. Filtro por expressão regular** (lista do que é aceito; todo o resto é
descartado):

| Site | Tipo | Padrão aceito | Exemplo |
|------|------|---------------|---------|
| GitHub | listagem | `^/topics(/[a-z0-9][a-z0-9-]*)?$` com no máximo `?page=N` (N até 50) | `/topics/python?page=3` |
| GitHub | projeto | `^/([a-z0-9][a-z0-9-]*)/([a-z0-9._-]+)$` sem parâmetros | `/psf/requests` |
| SourceForge | projeto | `^/projects/([a-z0-9][a-z0-9._-]*)/$` sem parâmetros | `/projects/sevenzip/` |
| SourceForge | listagem | `^/directory/([a-z0-9][a-z0-9._:+-]*/)*$` com no máximo `?page=N` | `/directory/games/?page=2` |
| SourceForge | sitemap | `^/(sitemap\|directory_sitemap)(-N)?\.xml$` | `/sitemap-12.xml` |

No GitHub, o padrão `/dono/repo` também casaria com páginas do próprio site,
como `/sponsors/fulano` ou `/features/copilot`. Por isso há uma lista de
primeiros segmentos reservados (sponsors, features, login, marketplace,
settings, search, orgs etc.), que nenhum usuário do GitHub pode usar como nome.
Páginas como issues, pulls, commits, tree, blob, arquivos, downloads, reviews,
rss e login não casam com nenhum padrão e são descartadas.

Usamos uma lista do que é aceito, e não uma lista do que é proibido, porque
esses sites têm milhões de URLs de outros tipos. Uma lista de proibições
sempre deixaria passar algum tipo novo de página; a lista de aceitos garante
que o coletor só gasta pedidos com páginas úteis.

**3. Conjunto de URLs conhecidas:** o link só entra na fila se ainda não
estiver na tabela `conhecidas`, que guarda toda URL já enfileirada ou visitada.

Além disso, o robots.txt é conferido no momento de baixar cada URL (seção
2.10). Links de um site para o outro são aproveitados: um link para
`github.com/dono/repo` numa página do SourceForge entra na fila do GitHub.

**Ordem da fila.** O Mercator separa a fila em "filas de frente" (prioridade)
e "filas de trás" (uma por domínio). Na nossa versão simplificada, cada
domínio tem a sua fila e, dentro dela, a ordem é:

1. **prioridade 0:** página de projeto encontrada numa listagem (tópico,
   diretório ou sitemap). A listagem já entrega os projetos que queremos,
   então eles são baixados logo em seguida;
2. **prioridade 1:** todo o resto: listagens, sitemaps e projetos citados
   dentro de outros projetos (por exemplo, num README);
3. dentro da mesma prioridade, a menor profundidade vem antes (busca em
   largura) e, empatando, vale a ordem de chegada.

A distinção entre projetos vindos de listagem e projetos citados em outros
projetos é importante: no teste, um único README (`vinta/awesome-python`)
trouxe 483 links novos para repositórios. Se esses links tivessem prioridade
máxima, o coletor mergulharia em cadeias de READMEs e nunca voltaria às seeds.
Na fila normal, eles esperam a vez em busca em largura, e as seeds, que levam
aos projetos mais relevantes, são processadas primeiro.

**Profundidade.** A profundidade é o número de links seguidos desde a seed. A
próxima página de uma listagem (paginação) e os sitemaps citados por outro
sitemap herdam a profundidade da página de origem, porque são continuação da
mesma lista e não um nível mais fundo; sem isso, `--max-depth 2` cortaria uma
listagem na página 3. O destino de um redirecionamento também herda a
profundidade.

### 2.7 Política de seleção de documentos

Nem toda página baixada vira documento. Uma página só é salva como
**documento** (tabela `projetos`) quando:

1. é do tipo projeto e respondeu **200** com conteúdo **HTML**;
2. tem as marcas de uma página de projeto. No GitHub, a metatag
   `octolytics-dimension-repository_nwo`, que traz o `dono/repo`; no
   SourceForge, a metatag `og:url` apontando para `/projects/nome/` e o título
   `h1` com `itemprop="name"`. Página que responde 200 sem essas marcas é uma
   página de erro disfarçada (**soft-404**) e é descartada;
3. **não é duplicada:** a chave do projeto (`dono/repo` ou `nome`) ainda não
   existe, e o hash SHA-1 do texto principal (descrição e README no GitHub,
   resumo e descrição no SourceForge) é diferente de todos os já salvos. O
   hash só é usado quando o texto tem pelo menos 200 caracteres, para que dois
   projetos diferentes com descrição curta ou vazia não sejam confundidos.

Páginas de listagem e sitemaps são salvos em bruto (fazem parte da coleta),
mas não são documentos. Respostas de erro (4xx, 5xx), redirecionamentos,
soft-404 e duplicadas não são salvas; ficam só registradas na tabela
`visitadas` e no log.

**Campos extraídos.** Antes de escrever os seletores baixamos e inspecionamos
páginas reais de cada tipo. Os seletores se apoiam em marcações estáveis (ids,
atributos `itemprop`, metatags e títulos de seção) e não nas classes CSS
geradas automaticamente, que mudam a cada versão do site. Por exemplo, a
página do GitHub usa classes como `SidebarAbout-module__description__xTkIP`,
cujo final muda a cada nova versão; por isso localizamos a seção pelo título
"About".

| Site | Campo | De onde vem |
|------|-------|-------------|
| GitHub | nome, dono | metatag `octolytics-dimension-repository_nwo` |
| GitHub | descrição | parágrafo da seção "About" (reserva: `og:description`) |
| GitHub | tópicos | links `/topics/...` da seção "About" |
| GitHub | estrelas, forks | atributo `title` dos contadores `#repo-stars-counter-star` e `#repo-network-counter` (valor exato) |
| GitHub | licença | link da licença na seção "About" (reserva: o mesmo link nas abas acima do README); "Other" quando o GitHub não reconhece o tipo |
| GitHub | linguagem | cartão do repositório na página de tópico (ver abaixo) |
| GitHub | README | texto do `article.markdown-body` (até 100 mil caracteres) |
| SourceForge | nome | `h1[itemprop=name]` |
| SourceForge | descrição | `[itemprop=description]` |
| SourceForge | resumo | `h2.summary` do cabeçalho |
| SourceForge | categorias | `[itemprop=applicationCategory]` |
| SourceForge | licença, linguagem | seções "License" e "Programming Language" (`section.project-info`) |
| SourceForge | downloads | bloco "Downloads:" (downloads da semana) |
| SourceForge | nota | `[itemprop=ratingValue]` e `ratingCount` dentro de `aggregateRating` |
| SourceForge | última atualização | `time.dateUpdated` |

Em todos os documentos também guardamos a URL, o site de origem, a data e hora
da coleta e o código HTTP.

Dois cuidados que só apareceram na inspeção das páginas reais:

- **Linguagem no GitHub:** a página do repositório carrega a barra de
  linguagens depois, por JavaScript, e o HTML inicial não traz a linguagem em
  lugar nenhum (conferimos também com User-Agent de navegador). O cartão de
  cada repositório na página de tópico traz essa informação
  (`itemprop="programmingLanguage"`). Quando o coletor processa uma página de
  tópico, guarda a linguagem de cada cartão na tabela `pistas`; quando o
  repositório é coletado, a linguagem vem dessa pista. Como a informação vem
  de uma página também baixada pelo coletor, continua sendo coleta de HTML.
- **Resumo no SourceForge:** a página tem vários `div.summary`, mas são
  anúncios de outros produtos. O resumo verdadeiro é só o `h2.summary` do
  cabeçalho. Na primeira versão o coletor pegava o anúncio; o erro foi
  encontrado no teste e corrigido.

### 2.8 Critério de parada

Cada thread para quando acontece a primeira destas condições:

1. **meta atingida:** o site chegou ao número alvo de páginas de projeto
   salvas (`--target`, padrão 25.000 por site);
2. **fila vazia:** não há mais URLs na fila do site (e a outra thread, que
   ainda poderia achar links para ele, também terminou);
3. **interrupção:** Ctrl+C. A thread termina a página atual, salva e para. A
   coleta pode ser retomada depois.

Também é possível limitar a profundidade com `--max-depth` (padrão: sem
limite).

**Justificativa:** a meta conta só páginas de projeto salvas, e não páginas
baixadas, porque o que interessa ao sistema de busca é o tamanho do acervo de
documentos. Listagens, redirecionamentos, erros e duplicadas não contam. A meta
é por site para garantir equilíbrio entre as duas fontes: sem isso, o site que
responde mais rápido dominaria a coleção.

### 2.9 Política de revisitação

**Não há revisitação:** cada URL é baixada uma única vez. A tabela `visitadas`
e o conjunto de URLs conhecidas garantem isso, inclusive entre execuções
diferentes.

**Justificativa:** como explicado na seção 2.4, o conteúdo de uma página de
projeto muda devagar e o sistema serve para descobrir projetos, não para
acompanhar mudanças em tempo real. A coleta completa leva algumas horas, então
todas as páginas têm praticamente a mesma idade. Revisitar consumiria pedidos
que rendem mais em páginas novas. Numa versão futura, uma política simples
seria revisitar primeiro os projetos mais populares ou com atualização mais
recente.

### 2.10 Boas maneiras

**robots.txt com a biblioteca protego.** O coletor lê o robots.txt de cada site
ao iniciar e confere cada URL antes de baixá-la. Usamos o protego (a mesma
biblioteca do Scrapy) porque o `urllib.robotparser` da biblioteca padrão não
entende curingas (`*` e `$`), e os dois sites usam muitos. Exemplos reais:

- GitHub: `Disallow: /*/tree/`, `Disallow: /*?tab=*`, `Disallow: /search$`;
- SourceForge: `Disallow: /directory/*?` junto com `Allow: /directory/*?page=`,
  que só funciona com a regra da correspondência mais longa (RFC 9309), também
  implementada pelo protego.

Testamos com os arquivos reais: o protego libera `github.com/psf/requests` e
`/topics/python?page=2`, bloqueia `/psf/requests?tab=x` e `/psf/requests/tree/main`,
libera `sourceforge.net/directory/?page=2` e bloqueia
`sourceforge.net/directory/?natlanguage=x`. Se o robots.txt responder 4xx, o
site não tem regras e tudo é permitido; se responder 5xx ou houver erro de
rede, o coletor não baixa nada daquele site e tenta ler o arquivo de novo
depois de 60 segundos.

**User-Agent.** Todos os pedidos se identificam como
`ColetorRI-PUCMinas/1.0 (trabalho academico)`. Assim o administrador do site
sabe quem está coletando e pode bloquear ou limitar só o nosso coletor.

**Espera entre pedidos.** Pelo menos 1 segundo entre dois pedidos ao mesmo
domínio, configurável com `--delay` (não aceita menos de 1 s). Se o robots.txt
tiver `Crawl-delay` maior, vale o `Crawl-delay`. Hoje nenhum dos dois sites
define `Crawl-delay` para `User-agent: *`.

**Uma fila e uma thread por domínio.** É a versão simples da Fila de Mercator:
cada site tem a sua fila e uma única thread consome essa fila. Isso garante no
máximo um pedido por vez a cada site, sempre respeitando a espera, e ainda
assim os dois sites são coletados em paralelo. A coleta fica duas vezes mais
rápida sem aumentar a carga sobre nenhum dos dois.

**Backoff em 429 e 503.** Se o site responder 429 (muitos pedidos) ou 503
(indisponível), o coletor espera cada vez mais antes de tentar de novo: 5, 10
e 20 segundos (mais um pequeno valor aleatório), até 3 novas tentativas. Se o
site mandar o cabeçalho `Retry-After`, esse tempo é respeitado. Se mesmo assim
o erro continuar, a URL é registrada como erro e a thread do site faz uma
pausa de 2 minutos antes de seguir.

**Outros cuidados:**

- redirecionamentos não são seguidos automaticamente: o destino vira um link
  novo, que passa pelo filtro, pelo robots.txt e pelo conjunto de conhecidas;
- a lista de links aceitos evita pedidos desnecessários;
- as respostas vêm compactadas (gzip) quando o servidor permite, o que reduz o
  tráfego.

Observação: o robots.txt do GitHub tem um comentário pedindo contato para
coletas. O coletor acessa apenas páginas permitidas para `User-agent: *`, no
ritmo de um pedido por segundo, com identificação e para fins acadêmicos.

### 2.11 Tolerância a falhas

- **Retomada:** todo o estado fica no SQLite. Cada página é registrada numa
  única transação: sai da fila, entra em `visitadas`, grava o projeto e
  enfileira os links novos. Se o programa cair, ou a página inteira foi
  registrada ou nada foi. Rodar o mesmo comando de novo continua de onde parou:
  as seeds já conhecidas são ignoradas e a fila é a mesma.
- **Blocos de HTML:** se a queda acontecer depois de gravar o HTML no bloco e
  antes de registrar no banco, o bloco fica com um resto no fim. Ao retomar, o
  bloco é cortado no fim do último registro válido do banco.
- **Erros de rede e timeout:** até 3 novas tentativas com espera crescente;
  depois disso a URL é registrada como `erro_rede` e a coleta continua.
- **404 e outros erros HTTP:** registrados como `erro_http` no banco e no log;
  a coleta continua.
- **Soft-404 e duplicadas:** descartadas, como descrito na seção 2.7.
- **Páginas estranhas:** corpo maior que 5 MB é cortado, e conteúdo que não é
  HTML (ou XML, no caso dos sitemaps) é descartado.
- **Falha numa thread:** um erro inesperado numa thread é registrado no log e
  não derruba a outra.

**Testes feitos:**

- matamos o processo à força no meio de uma coleta (no projeto 66 de 80) e
  rodamos de novo. A coleta continuou do projeto 67, o banco passou na
  verificação de integridade do SQLite, não houve nenhum projeto duplicado e
  as 171 páginas salvas foram lidas de volta dos blocos gzip;
- um repositório inexistente e um projeto inexistente devolveram 404 e foram
  apenas registrados;
- um repositório renomeado (`twitter/bootstrap`) devolveu 301 para
  `twbs/bootstrap`; como o destino já tinha sido coletado, foi ignorado;
- com um servidor local, uma URL que responde 429 e depois 503 foi baixada na
  terceira tentativa, e uma URL que sempre responde 503 foi abandonada depois
  de 1 pedido e 3 novas tentativas.

### 2.12 Armazenamento

**SQLite (`data/coletor.db`):**

| Tabela | Conteúdo |
|--------|----------|
| `fila` | URLs a visitar, com site, tipo, prioridade, profundidade e página de origem (uma fila por domínio, separada pela coluna site) |
| `conhecidas` | conjunto de todas as URLs já vistas (na fila ou visitadas) |
| `visitadas` | cada URL processada: código HTTP, resultado, data e hora, tamanho e posição do HTML bruto no bloco |
| `projetos` | os campos extraídos de cada documento |
| `pistas` | linguagem vista no cartão do tópico, para repositórios ainda não visitados |
| `execucoes` | início e duração de cada execução, para o tempo total |

**HTML bruto em blocos gzip (`data/html/<site>/bloco_00001.gz`...):** cada
arquivo guarda até 1.000 páginas (configurável com `--block-size`). Cada
página é um membro gzip independente, e a tabela `visitadas` guarda o arquivo,
a posição e o tamanho; assim qualquer página pode ser lida de volta sem
descompactar o bloco inteiro.

**Saída (`data/projetos.jsonl`):** um projeto por linha, com os campos da
seção 2.7. É a entrada da etapa de indexação.

**Justificativa:** o SQLite é um banco embarcado, sem servidor, com transações
(o que permite a retomada segura) e consultas SQL (usadas nas estatísticas).
Os blocos evitam os dois extremos: dezenas de milhares de arquivos pequenos,
lentos de copiar e listar, ou um arquivo único gigante, que se corrompido
perderia tudo e não pode ser processado em partes.

---

## 📈 3. Escala

### 3.1 Meta

A meta é passar de **50 mil páginas de projeto**: 25 mil do GitHub e 25 mil do
SourceForge (`python run_coletor.py --target 25000`).

### 3.2 Medidas do teste

Teste com `--target 50` (50 páginas de projeto por site), partindo do zero:

- 107 páginas baixadas (100 de projeto e 7 listagens) em 57 segundos, sem
  nenhum erro;
- cerca de 3.400 páginas por hora em cada site, ou 6.700 por hora somando os
  dois;
- tamanho médio do HTML compactado: cerca de 70 KB por página do GitHub e
  32 KB por página do SourceForge.

### 3.3 Estimativa da coleta completa

Cada site precisa de cerca de 27 mil pedidos (25 mil páginas de projeto mais
listagens, sitemaps, redirecionamentos e duplicadas). No ritmo medido, isso dá
cerca de **8 horas**, com os dois sites em paralelo, e cerca de **3 a 4 GB**
em disco (HTML compactado, banco e JSONL). Como a coleta é retomável, ela pode
ser feita em várias sessões.

### 3.4 Números da coleta completa

Obtidos com `python run_coletor.py --stats` depois da coleta completa.

| Medida | Valor |
|--------|-------|
| Páginas baixadas (total) | _preencher_ |
| Páginas de projeto do GitHub | _preencher_ |
| Páginas de projeto do SourceForge | _preencher_ |
| **Total de documentos** | _preencher_ |
| Listagens e sitemaps | _preencher_ |
| Redirecionamentos | _preencher_ |
| Descartadas por duplicação | _preencher_ |
| Descartadas por soft-404 | _preencher_ |
| Erros HTTP (404 etc.) | _preencher_ |
| Erros de rede e timeout | _preencher_ |
| Bloqueadas pelo robots.txt | _preencher_ |
| URLs conhecidas ao final | _preencher_ |
| Tempo total de coleta | _preencher_ |
| Taxa média (páginas por hora) | _preencher_ |
| HTML bruto em disco (gzip) | _preencher_ |
| Banco SQLite | _preencher_ |
| `projetos.jsonl` | _preencher_ |

**Preenchimento dos campos (% dos projetos):**

| GitHub | % | SourceForge | % |
|--------|---|-------------|---|
| descrição | _preencher_ | descrição | _preencher_ |
| tópicos | _preencher_ | resumo | _preencher_ |
| linguagem | _preencher_ | categorias | _preencher_ |
| estrelas | _preencher_ | licença | _preencher_ |
| forks | _preencher_ | linguagem | _preencher_ |
| licença | _preencher_ | downloads | _preencher_ |
| README | _preencher_ | nota | _preencher_ |
| | | última atualização | _preencher_ |

---

## ▶️ 4. Como executar

```bash
# 1) Instalar as dependências
pip install -r requirements.txt

# 2) Teste rápido (100 páginas de projeto por site)
python run_coletor.py --target 100

# 3) Coleta completa (25 mil páginas de projeto por site)
python run_coletor.py --target 25000

# 4) Retomar depois de uma interrupção: rodar o mesmo comando de novo
python run_coletor.py --target 25000

# 5) Estatísticas e exportação sem coletar
python run_coletor.py --stats
python run_coletor.py --export-only
```

Opções: `--max-depth N`, `--delay S`, `--sites github sourceforge`,
`--block-size N`, `--output DIR`, `--debug`.

---

## 🔭 5. Limitações e próximos passos

- **Mudanças no HTML:** se um dos sites mudar o layout, algum seletor pode
  parar de funcionar. Os seletores usam marcações estáveis e têm alternativas
  de reserva, e o comando `--stats` mostra a porcentagem de preenchimento de
  cada campo, o que ajuda a perceber rapidamente um seletor quebrado.
- **Linguagem no GitHub:** só é conhecida para repositórios que aparecem num
  cartão de página de tópico. Repositórios encontrados por outros caminhos
  (links em README, por exemplo) ficam sem linguagem.
- **Cauda longa do SourceForge:** os projetos vindos dos sitemaps incluem
  muitos projetos pequenos ou inativos, com menos campos preenchidos (sem nota
  ou sem resumo, por exemplo).
- **Limite de 50 páginas por tópico:** cada tópico do GitHub dá no máximo 1.000
  repositórios. O coletor contorna isso descobrindo novos tópicos nas próprias
  páginas (cada página de tópico e cada repositório apontam para outros
  tópicos).
- **Sem revisitação:** a coleção é uma fotografia do momento da coleta.
- Na etapa 2, o `projetos.jsonl` será a entrada do indexador.
