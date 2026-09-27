# Coletor de repositórios do GitHub

Primeira parte do trabalho de Recuperação da Informação (o coletor).

A ideia é montar um acervo de repositórios públicos do GitHub para depois
indexar e permitir busca. Nesta etapa só coletamos os dados.

Usamos a API oficial do GitHub em vez de ficar raspando HTML, porque a API
devolve tudo em JSON e não bloqueia acesso. De cada repositório a gente guarda
descrição, README, linguagem, tópicos, estrelas, forks, licença, datas e o dono
(usuário ou organização).

## O que precisa

- Python 3
- A biblioteca `requests` (`pip install -r requirements.txt`)
- Um token do GitHub (é de graça)

## Token do GitHub

Sem token a API só deixa fazer 60 requisições por hora, o que é pouco. Com um
token pessoal sobe para 5000 por hora.

Para gerar: entre em https://github.com/settings/tokens, crie um token clássico.
Para repositório público não precisa marcar nenhuma permissão.

Depois é só definir o token antes de rodar:

    export GITHUB_TOKEN=seu_token_aqui        (Linux/Mac)
    $env:GITHUB_TOKEN="seu_token_aqui"        (Windows PowerShell)

Ou então copie o arquivo `.env.example` para `.env` e cole o token lá dentro.

## Como rodar

Instalar:

    pip install -r requirements.txt

Teste com poucos repositórios primeiro, só pra ver se está tudo certo:

    python run_coletor.py --target 200

Coleta grande (mais de 50 mil). Sem baixar os READMEs fica bem mais rápido:

    python run_coletor.py --target 50000 --no-readme --export

Se quiser os READMEs junto (demora mais):

    python run_coletor.py --target 50000 --export

Se a coleta parar no meio, é só rodar de novo o mesmo comando que ela continua
de onde estava (o progresso fica salvo no banco).

## Onde ficam os dados

Tudo dentro da pasta `data/`:

- `github.db` - banco SQLite com os repositórios e usuários
- `raw_readme/` - os READMEs baixados
- `repositories.jsonl` - os dados exportados, um repositório por linha (é o que
  vamos usar na parte de indexação)
- `crawler.log` - log do que aconteceu

Para ver quantos itens já foram coletados:

    sqlite3 data/github.db "SELECT COUNT(*) FROM repositories;"
    sqlite3 data/github.db "SELECT COUNT(*) FROM users;"

## Sobre a escala (chegar nos 50 mil)

A busca do GitHub só devolve no máximo 1000 resultados por pesquisa. Para passar
disso, a gente divide a coleta em várias pesquisas por número de estrelas
(repos com 5000 estrelas, com 4999, com 4998... e assim por diante). Cada
pesquisa dessas fica abaixo do limite de 1000 e, somando todas, dá pra passar
tranquilo dos 50 mil repositórios.

Os detalhes estão no relatório (`RELATORIO_PARTE1_COLETOR.md`).

## Organização dos arquivos

    coletor/config.py    - configurações (token, limites, estratégia de busca)
    coletor/fetcher.py   - faz as requisições pra API e trata o limite de uso
    coletor/storage.py   - salva no SQLite e nos arquivos
    coletor/crawler.py   - junta tudo e controla a coleta
    run_coletor.py       - arquivo que você executa
