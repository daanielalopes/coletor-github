# Explicação técnica das decisões de projeto

Resumo das principais decisões, com a alternativa considerada e o porquê da
escolha. O detalhamento completo está nos três relatórios.

---

## 1. Coletor web clássico (sem API)

- **Decisão:** baixar o HTML das páginas com GET e seguir os links, como o
  modelo de coletor visto em aula; uma fila e uma thread por domínio (versão
  simples da Fila de Mercator), respeitando robots.txt e 1 s entre pedidos.
- **Alternativa:** usar a API do GitHub. **Por que não:** o trabalho pede um
  coletor web; a API exige token e limita a taxa.

## 2. Índice invertido em arquivos próprios (sem banco de dados)

- **Decisão:** gravar o índice como arquivos binários/texto escritos pelo
  próprio sistema (postings, posições, léxico, documentos, comprimentos, meta).
- **Alternativa:** guardar o índice num SQLite/Postgres. **Por que não:** o
  objetivo didático é implementar a estrutura de RI; arquivos com `seek` dão
  controle total sobre o layout e a compressão, e deixam o custo de cada
  consulta transparente.

## 3. Construção com SPIMI + fusão em k vias

- **Decisão:** SPIMI — montar blocos de índice em memória, gravar cada bloco
  ordenado em disco e depois fundir os blocos em ordem de termo (heap).
- **Alternativa:** índice inteiro em memória. **Por que não:** 52 mil projetos
  geram ~9,8 milhões de postings; o SPIMI mantém a memória limitada (pico de
  216 MB) e escala para acervos maiores.

## 4. Compressão por gaps + Variable Byte

- **Decisão:** guardar as diferenças (gaps) entre docids/posições e codificar
  com Variable Byte.
- **Alternativa:** guardar números inteiros de 4 bytes. **Por que não:** os gaps
  são pequenos e o VB usa 1–2 bytes para a maioria; o índice invertido caiu de
  183,6 MB para 91,8 MB (≈ metade), com decodificação simples e rápida.

## 5. Postings e posições em arquivos separados

- **Decisão:** as posições (para consulta por frase) ficam num arquivo à parte.
- **Vantagem:** uma consulta normal nunca lê nem decodifica posições —
  recuperação mais leve. **Custo:** um arquivo a mais por partição.

## 6. Granularidade por campo + BM25F

- **Decisão:** indexar cada projeto como uma unidade, guardando a frequência de
  cada campo (nome, descrição, rótulos, README) separada, e ranquear com BM25F.
- **Alternativa:** juntar tudo num campo só (BM25 simples) ou TF-IDF/cosseno.
  **Por que BM25F:** satura a frequência (não premia repetição), normaliza o
  comprimento e dá peso por campo — o nome de um projeto vale muito mais que uma
  menção perdida no README.
- **Fórmulas** (detalhe no relatório final, seção 3):
  - `idf(t) = log(1 + (N - df + 0.5)/(df + 0.5))`
  - `norm_campo = 1 - b + b·(comprimento_campo / média_campo)`, `b = 0.75`
  - `nota = Σ_t idf(t)·qtf(t)· tf_f/(k1 + tf_f)`, com
    `tf_f = Σ_campo peso_campo·tf_campo/norm_campo`, `k1 = 1.2`.

## 7. Recuperação dirigida pelo índice

- **Decisão:** léxico particionado por `crc32(termo) % 16`; só a partição do
  termo é carregada, e as postings do termo são lidas com `seek`/`read`.
- **Vantagem:** não se carrega o vocabulário inteiro (779 mil termos) nem se
  varrem documentos para responder a uma consulta.

## 8. Interface web com a biblioteca padrão

- **Decisão:** servidor `http.server` servindo uma página única + endpoints
  JSON que chamam o `Buscador`.
- **Alternativa:** Flask/Streamlit. **Por que não:** acrescentariam
  dependências; a interface é pequena e a biblioteca padrão basta. **Vantagem:**
  instalação trivial e portável. A interface **reusa** `Indice` e `Buscador` —
  não tem busca própria (garantido por teste).

## 9. Stemmer opcional (melhoria após a entrega parcial)

- **Decisão:** usar `snowballstemmer` se estiver instalado; senão, o Porter2 em
  Python puro que acompanha o projeto (`indexador/porter2.py`).
- **Motivo:** antes, sem o pacote, o sistema não rodava. Agora roda em qualquer
  máquina só com a biblioteca padrão. O stemmer interno coincide com o pacote na
  quase totalidade das palavras (testado).

## 10. Testes de ranking e interface (melhoria após a entrega parcial)

- **Decisão:** além dos testes do índice, testar o comportamento do BM25F e
  provar que a interface devolve o mesmo que o `Buscador`.
- **Motivo:** garantir, de forma automática, os dois pontos centrais da
  avaliação — ranking correto e interface ligada ao índice.
