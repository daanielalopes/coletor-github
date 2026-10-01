# 🗂️ Coletor de Projetos de Software Livre (GitHub e SourceForge)

## 🎯 Objetivo

Esta é a primeira etapa de um sistema de busca de projetos de software livre.
O coletor monta o acervo de documentos que será indexado na etapa seguinte.
Cada documento é a página de um projeto:

- um repositório do GitHub (`github.com/dono/repo`);
- um projeto do SourceForge (`sourceforge.net/projects/nome/`).

A meta é passar de 50 mil páginas de projeto, cerca de 25 mil de cada site.

O coletor é um coletor web clássico, igual ao modelo visto em aula: ele baixa o
HTML das páginas com GET, extrai os links e segue esses links. Não usa nenhuma
API e não precisa de token.

## ⚙️ Como funciona

1. Começa com as seeds na fila.
2. Pega uma URL da fila, confere o robots.txt e baixa o HTML com GET.
3. Salva o conteúdo: o HTML bruto compactado e, nas páginas de projeto, os
   campos extraídos.
4. Extrai os links da página.
5. Coloca na fila só os links novos (que não estão no conjunto de URLs
   conhecidas) e que passam no filtro de seleção.
6. Repete até atingir a meta de páginas de projeto ou a fila acabar.

Cada site tem a sua própria fila e a sua própria thread (uma versão simples da
Fila de Mercator). Os dois sites são coletados ao mesmo tempo, mas cada um
recebe no máximo um pedido por vez, com pelo menos 1 segundo entre pedidos.

**Seeds**

- GitHub: `github.com/topics` e as páginas de 30 tópicos populares (python,
  javascript, machine-learning, java, linux etc.), com a paginação `?page=1`
  até `?page=50`.
- SourceForge: `sourceforge.net/directory/` e 18 categorias do diretório, com
  a paginação `?page=1` até `?page=20`, mais os sitemaps listados no
  robots.txt do SourceForge.

**Links aceitos**

- GitHub: páginas de tópico (`/topics/nome`, com no máximo `?page=N`) e páginas
  raiz de repositório (`/dono/repo`, sem nada depois).
- SourceForge: raiz de projeto (`/projects/nome/`), páginas do diretório
  (`/directory/...`, com no máximo `?page=N`) e os sitemaps de projetos e do
  diretório.

Todo o resto (login, issues, pulls, commits, arquivos, downloads, reviews,
rss etc.) é descartado antes de entrar na fila.

## 📋 Requisitos

- Python 3.9 ou mais novo
- Bibliotecas: `requests`, `protego`, `beautifulsoup4` e `lxml`

## ▶️ Execução

Instale as dependências (de preferência num ambiente virtual):

    python -m venv .venv
    .venv\Scripts\activate            (Windows)
    source .venv/bin/activate         (Linux/Mac)
    pip install -r requirements.txt

Teste rápido (100 páginas de projeto por site):

    python run_coletor.py --target 100

Coleta completa (25 mil páginas de projeto por site):

    python run_coletor.py --target 25000

Se a coleta for interrompida (Ctrl+C, queda de energia, erro), basta rodar o
mesmo comando de novo. O estado fica salvo no SQLite e a coleta continua de
onde parou, sem baixar de novo o que já foi baixado.

Ao terminar, o coletor exporta `data/projetos.jsonl` e mostra as estatísticas.

**Outras opções**

    --target N        páginas de projeto por site (padrão 25000)
    --max-depth N     profundidade máxima a partir das seeds (padrão: sem limite)
    --delay S         espera mínima entre pedidos ao mesmo domínio (padrão 1.0 s)
    --sites ...       coletar só github, só sourceforge ou os dois (padrão)
    --block-size N    páginas por arquivo de bloco de HTML (padrão 1000)
    --stats           só mostrar as estatísticas e sair
    --export-only     só exportar data/projetos.jsonl e sair
    --debug           log detalhado

Exemplo com profundidade máxima e um site só:

    python run_coletor.py --target 1000 --sites github --max-depth 3

## 📊 Estatísticas

    python run_coletor.py --stats

Mostra as páginas baixadas no total, as páginas de projeto por site, os erros,
o tempo total de coleta, o tamanho em disco e a porcentagem de projetos com
cada campo preenchido.

## 💾 Dados gerados

Tudo fica na pasta `data/`:

- `coletor.db`: banco SQLite com a fila de cada domínio, as URLs conhecidas,
  as URLs visitadas (com código HTTP e resultado) e os campos extraídos dos
  projetos;
- `html/github/` e `html/sourceforge/`: HTML bruto compactado com gzip, em
  blocos de 1000 páginas (`bloco_00001.gz`, `bloco_00002.gz`...);
- `projetos.jsonl`: um projeto por linha, entrada da etapa de indexação;
- `coletor.log`: registro da execução, inclusive os erros.

**Campos de cada projeto no JSONL**

- Todos: `site`, `url`, `coletado_em` (data e hora da coleta), `status_http`
  e `nome`.
- GitHub: `dono`, `descricao`, `topicos`, `linguagem`, `estrelas`, `forks`,
  `licenca` e `readme` (texto do README que aparece na página).
- SourceForge: `descricao`, `resumo`, `categorias`, `licenca`, `linguagem`,
  `downloads_semana`, `nota`, `num_avaliacoes` e `ultima_atualizacao`.

**Ler o HTML bruto de uma página**

Cada página é um membro gzip separado dentro do bloco. A tabela `visitadas`
guarda o arquivo, a posição e o tamanho de cada uma:

    from coletor.storage import Storage
    s = Storage("data", "coletor.db")
    html = s.read_raw("https://github.com/psf/requests")

**Consultas úteis**

    sqlite3 data/coletor.db "SELECT site, COUNT(*) FROM projetos GROUP BY site;"
    sqlite3 data/coletor.db "SELECT resultado, COUNT(*) FROM visitadas GROUP BY resultado;"

## 🧾 Evidências da coleta

A pasta `evidencias/` guarda provas da coleta completa (52.000 páginas de
projeto, 26.000 de cada site), geradas a partir de `data/` com:

    python gerar_evidencias.py

- `estatisticas.txt` e `resumo.json`: números finais da coleta;
- `urls_coletadas.csv`: as 52.000 URLs de projeto coletadas, com data e hora;
- `amostra_projetos.jsonl`: 50 projetos de cada site com todos os campos;
- `projetos_por_hora.csv`: páginas baixadas e projetos salvos por hora;
- `trechos_do_log.txt`: início, metas atingidas e fim de cada execução;
- `sha256.txt`: hash do `projetos.jsonl`, para conferir o arquivo completo.

## 📁 Organização dos arquivos

    coletor/config.py      configurações: boas maneiras, parada, seeds, armazenamento
    coletor/urls.py        normalização de URLs e filtro de links (regex de cada site)
    coletor/robots.py      leitura do robots.txt com a biblioteca protego
    coletor/fetcher.py     GET com User-Agent, espera entre pedidos e backoff
    coletor/extractors.py  extração de links e dos campos das páginas de projeto
    coletor/sites.py       seeds de cada site
    coletor/storage.py     SQLite e blocos de HTML em gzip
    coletor/crawler.py     laço do coletor, uma thread por domínio
    coletor/stats.py       estatísticas da coleta
    run_coletor.py         script principal
    gerar_evidencias.py    gera a pasta evidencias/ a partir de data/

As decisões de projeto estão justificadas no relatório
(`RELATORIO_PARTE1_COLETOR.md`).
