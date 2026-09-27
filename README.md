# Coletor de Repositórios do GitHub

Primeira etapa do trabalho de Recuperação da Informação: o coletor de dados.

## Objetivo

Esta etapa tem como objetivo construir um acervo de repositórios públicos do
GitHub, que será utilizado posteriormente nas fases de indexação e de busca. No
momento, o foco está exclusivamente na coleta e no armazenamento dos dados.

A coleta é realizada por meio da API oficial do GitHub, e não por extração de
conteúdo das páginas HTML. Essa decisão se justifica porque a API retorna os
dados de forma estruturada em JSON e não impõe bloqueios de acesso automatizado.

Para cada repositório são armazenados os seguintes campos: descrição, README,
linguagem, tópicos, número de estrelas, número de forks, licença, datas
relevantes e informações do proprietário (usuário ou organização).

## Requisitos

- Python 3
- Biblioteca `requests` (instalada via `pip install -r requirements.txt`)
- Um token de acesso pessoal do GitHub (gratuito)

## Token do GitHub

Sem autenticação, a API do GitHub permite apenas 60 requisições por hora, o que
é insuficiente para uma coleta em larga escala. Com um token pessoal, esse
limite aumenta para 5000 requisições por hora.

Para gerar o token, acesse https://github.com/settings/tokens e crie um token
clássico. Para acesso a dados públicos não é necessário selecionar nenhuma
permissão adicional.

Em seguida, defina o token antes da execução:

    export GITHUB_TOKEN=seu_token_aqui        (Linux/Mac)
    $env:GITHUB_TOKEN="seu_token_aqui"        (Windows PowerShell)

Alternativamente, copie o arquivo `.env.example` para `.env` e informe o token
nesse arquivo.

## Execução

Instalação das dependências:

    pip install -r requirements.txt

Recomenda-se iniciar com uma coleta reduzida, para verificar o funcionamento:

    python run_coletor.py --target 200

Para a coleta completa (acima de 50 mil repositórios). A execução sem o
download dos READMEs é consideravelmente mais rápida:

    python run_coletor.py --target 50000 --no-readme --export

Caso deseje incluir os READMEs (execução mais demorada):

    python run_coletor.py --target 50000 --export

Se a coleta for interrompida, basta executar o mesmo comando novamente: o
progresso é salvo no banco de dados e a coleta prossegue a partir do ponto em
que parou.

## Dados gerados

Todos os arquivos são gravados no diretório `data/`:

- `github.db` — banco de dados SQLite com os repositórios e usuários coletados
- `raw_readme/` — arquivos de README obtidos durante a coleta
- `repositories.jsonl` — dados exportados, um repositório por linha (formato
  utilizado na etapa de indexação)
- `crawler.log` — registro da execução

Para consultar a quantidade de itens coletados:

    sqlite3 data/github.db "SELECT COUNT(*) FROM repositories;"
    sqlite3 data/github.db "SELECT COUNT(*) FROM users;"

## Estratégia de escala

A API de busca do GitHub retorna no máximo 1000 resultados por consulta. Para
superar esse limite, a coleta é dividida em diversas consultas segmentadas pelo
número de estrelas dos repositórios (repositórios com 5000 estrelas, com 4999,
com 4998, e assim sucessivamente). Cada consulta permanece abaixo do limite de
1000 resultados e, somadas, permitem ultrapassar com folga a marca de 50 mil
repositórios.

Os detalhes completos estão descritos no relatório
(`RELATORIO_PARTE1_COLETOR.md`).

## Organização dos arquivos

    coletor/config.py    configurações (token, limites e estratégia de busca)
    coletor/fetcher.py   requisições à API e tratamento do limite de uso
    coletor/storage.py   armazenamento em SQLite e em arquivos
    coletor/crawler.py   orquestração e controle da coleta
    run_coletor.py       script principal de execução
