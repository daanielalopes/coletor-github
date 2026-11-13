# Perguntas prováveis do professor (com respostas)

Perguntas que costumam cair numa apresentação de sistema de RI, com respostas
curtas e ancoradas no nosso código.

---

### 1. A interface realmente consulta o índice invertido ou faz uma busca à parte?

Consulta o índice. A interface (`interface/app.py`) carrega uma instância de
`Indice` e de `Buscador` — as mesmas classes do `buscar.py` — e toda consulta é
atendida por `Buscador.buscar(...)`. Não há busca própria. Temos até um teste
automático (`tests/test_busca.py::test_busca_igual_ao_buscador`) que verifica
que a lista de resultados da API é idêntica, na mesma ordem, à do `Buscador`.
E na própria interface, clicando num termo, aparecem as postings lidas do índice.

### 2. Qual modelo de ranking vocês usaram e por quê?

BM25, na variante BM25F (por campo). Escolhemos em vez de TF-IDF/cosseno porque
o BM25 satura a frequência do termo (a 10ª ocorrência vale menos que a 2ª),
normaliza o comprimento do documento e, na forma F, dá pesos diferentes aos
campos — o nome e a descrição de um projeto valem mais que o README.

### 3. Explique a fórmula do BM25.

A nota de um documento é a soma, sobre os termos da consulta, de
`idf(t) · tf/(k1 + tf)`. O `idf = log(1 + (N - df + 0.5)/(df + 0.5))` faz o
termo raro pesar mais. O `tf/(k1 + tf)` satura a frequência. E o `tf` é
normalizado pelo comprimento: `norm = 1 - b + b·(comprimento/média)`. Usamos
`k1 = 1.2` e `b = 0.75`, valores usuais da literatura. No BM25F somamos a
frequência ponderada de cada campo **antes** da saturação.

### 4. O que são `df` e `cf`?

`df` (document frequency) é em quantas unidades o termo aparece — entra no IDF.
`cf` (collection frequency) é o total de ocorrências do termo na coleção. Os
dois ficam guardados no léxico e aparecem no detalhe de cada termo na interface.

### 5. Por que não guardaram o índice num banco de dados?

Porque o objetivo é implementar a estrutura de RI. Gravar em arquivos próprios,
lidos com `seek`, dá controle total sobre o layout e a compressão e deixa o
custo de cada consulta transparente. (O SQLite só é usado pelo coletor, para a
fila e o estado da coleta.)

### 6. Como funciona a compressão do índice?

Guardamos as diferenças (gaps) entre docids e posições consecutivos, e as
codificamos com Variable Byte: 7 bits de dado por byte, 1 bit marcando o último
byte. Números pequenos ocupam 1 byte. O índice invertido caiu de 183,6 MB para
91,8 MB no acervo completo.

### 7. O que é o SPIMI e por que usaram?

Single-Pass In-Memory Indexing: montamos blocos de índice em memória, gravamos
cada bloco ordenado em disco e depois fundimos todos em ordem de termo com um
heap. Mantém a memória limitada (pico de 216 MB para 9,8 milhões de postings) e
escala para acervos que não caberiam na RAM.

### 8. Como vocês tratam "C++", "C#", "Node.js"?

São termos técnicos com símbolos. O analisador os reescreve antes de tokenizar:
`c++ → cpp`, `c# → csharp`, `.net → dotnet`, `node.js → nodejs`. Sem isso, "c++"
viraria só "c" e "node.js" viraria "node" + "js". Dá para mostrar ao vivo: a
consulta "game engine c++" é analisada como `game engin cpp`.

### 9. Fazem stemming? E com outras línguas?

Sim, stemming Snowball (Porter2) para inglês, só em palavras ASCII sem dígitos.
Removemos stopwords de inglês e português. Para chinês/japonês/coreano, que não
têm espaço entre palavras, geramos bigramas de caracteres (como o CJKAnalyzer do
Lucene). Acentos são removidos na normalização.

### 10. A busca é booleana ou ranqueada? Trata várias palavras como "E" ou "OU"?

É ranqueada (vetorial/probabilística), não booleana. Na prática é um "OU" com
pontuação: um documento entra no resultado se tiver **algum** termo, e sobe no
ranking quanto mais termos tiver e quanto melhores forem os campos em que
aparecem. Quem tem todos os termos tende a ficar à frente.

### 11. Suportam busca por frase ("entre aspas")?

A estrutura está pronta: guardamos as **posições** de cada ocorrência (num
arquivo separado), que é o que uma busca por frase precisa. O ranqueador atual
não casa frase ainda; essa é uma extensão direta sobre as posições já indexadas.

### 12. Quanto tempo leva uma consulta? E a indexação?

Indexar os 52 mil projetos levou 97,8 s (numa máquina de 8 núcleos). Uma
consulta responde em poucos milissegundos, porque só lê as listas dos termos
pedidos, não os documentos.

### 13. Como rodar em outra máquina? Precisa de quê?

Só do Python 3.9+. O indexador, a busca e a interface rodam com a biblioteca
padrão. O único pacote externo do indexador, `snowballstemmer`, é opcional: sem
ele, usamos um Porter2 em Python puro que acompanha o projeto. A interface web
não tem nenhuma dependência externa. As bibliotecas do coletor (requests,
beautifulsoup...) só são necessárias para coletar da internet.

### 14. Como sabem que o índice está correto?

Temos um teste que reconstrói o índice por força bruta (lendo os documentos
diretamente) e compara, termo a termo, as postings, as posições, o `df` e o `cf`
com o que o índice devolve — nas três granularidades. Se algo divergir, o teste
falha.

### 15. O que mudou depois da entrega parcial?

Três coisas principais: (1) o stemmer virou opcional, com um Porter2 interno de
reserva, para o sistema rodar sem internet; (2) acrescentamos testes do ranking
BM25F e da interface web; (3) entregamos a interface gráfica web e a camada de
recuperação/ranking que fecham o sistema.

### 16. Qual a maior limitação e o que fariam a seguir?

A calibração dos pesos do BM25F e do `k1`/`b` é provisória (valores da
literatura). O próximo passo é montar julgamentos de relevância e calibrar os
parâmetros, além de usar sinais de popularidade (estrelas, downloads) que já
coletamos, e implementar a busca por frase sobre as posições já indexadas.
