# Roteiro de Apresentação — 10 minutos

Sistema de busca de projetos de software livre (GitHub e SourceForge).
Sugestão de divisão do tempo e do que dizer/mostrar em cada bloco.

> **Antes de começar:** deixe o índice pronto e a interface no ar.
> ```
> mkdir -p data && cp evidencias/amostra_projetos.jsonl data/projetos.jsonl
> python run_indexador.py --processos 1
> python -m interface.app --indice data/indice --porta 8000
> ```
> Abra `http://localhost:8000` numa aba e um terminal noutra janela.

---

## 0:00–1:00 — Abertura e problema (1 min)

- "Construímos um buscador de projetos de software livre: o usuário digita o que
  procura e recebe uma lista de projetos do GitHub e do SourceForge, ordenados
  por relevância."
- O ciclo completo de Recuperação da Informação: **coletar → indexar →
  recuperar e ranquear → apresentar**.
- Diga os números reais do acervo: **52.000 projetos coletados**, vocabulário de
  **779 mil termos**, índice invertido de **91,8 MB** comprimido.

## 1:00–2:30 — Arquitetura (1,5 min)

- Mostre o diagrama (do relatório final, seção 1). Três partes ligadas por
  arquivos: `data/projetos.jsonl` (coletor → indexador) e `data/indice/`
  (indexador → busca).
- Destaque a decisão: **sem banco de dados no índice** — o índice é um conjunto
  de arquivos binários (postings/posições/léxico) escritos pelo próprio sistema.
- "A busca pela linha de comando e a interface web são duas cascas sobre o mesmo
  mecanismo: as classes `Indice` e `Buscador`."

## 2:30–5:00 — Demonstração ao vivo na interface (2,5 min)

Faça 2–3 das cinco consultas preparadas (ver `CONSULTAS_DEMO.md`). Roteiro:

1. Busque **`static site generator`**.
   - Aponte o 1º lugar (**tumblelog, nota 7,83**): tem os três termos, dois no
     nome/descrição. "O ranking BM25F prioriza quem tem o termo no nome e na
     descrição, não só no README."
2. Busque **`game engine c++`**.
   - Mostre, na faixa de termos, que a consulta virou `game engin cpp`:
     "o `c++` foi tratado como um termo técnico só — senão viraria só `c`."
3. **Clique num termo** (ex.: `game`) para abrir o detalhe.
   - "Aqui está a entrada do termo **no índice invertido**: partição, df, cf e
     as postings com a frequência por campo. É a prova de que a interface
     consulta o índice, e não uma busca à parte."

## 5:00–7:00 — Como a recuperação e o ranking funcionam (2 min)

- **Recuperação:** para cada termo, vai-se direto à lista de documentos do termo
  (seek + read no arquivo de postings), sem varrer os documentos. Léxico
  dividido em 16 partições por hash; só a partição do termo é carregada.
- **Compressão:** postings guardadas como gaps + Variable Byte (91,8 MB vs
  183,6 MB sem compressão).
- **Ranking (BM25F):** mostre as três ideias em uma frase cada:
  - IDF: termo raro pesa mais que termo comum;
  - saturação: a 10ª ocorrência vale menos que a 2ª;
  - pesos de campo: nome (3) > descrição/rótulos (2) > README (1).

## 7:00–8:30 — Qualidade: testes e portabilidade (1,5 min)

- Rode ao vivo (ou mostre o resultado): `python -m unittest discover -s tests`.
  **28 testes, < 1 s.**
- Cite dois testes-chave:
  - o índice é comparado **termo a termo com um cálculo por força bruta**;
  - a **API da interface devolve exatamente o resultado do `Buscador`** (teste
    `test_busca_igual_ao_buscador`) — prova automática de que a interface não
    faz busca própria.
- Portabilidade: "roda em qualquer máquina só com o Python — o stemmer externo é
  opcional; temos um Porter2 em Python puro de reserva. A interface web não tem
  nenhuma dependência."

## 8:30–9:30 — Decisões e melhorias após a entrega parcial (1 min)

- BM25F em vez de TF-IDF/cosseno: satura a frequência e dá peso por campo.
- Interface web sem framework: zero dependências.
- **Melhorias após a parcial:** stemmer opcional (portabilidade) e testes de
  ranking e da interface.

## 9:30–10:00 — Fechamento (30 s)

- "Entregamos o ciclo completo de RI, com recuperação comprovadamente pelo
  índice invertido, ranking BM25F e uma interface que usa o mesmo mecanismo de
  busca. Tudo roda só com a biblioteca padrão do Python."
- Abra para perguntas (ver `PERGUNTAS_PROVAVEIS.md`).

---

### Plano B (se a demo ao vivo falhar)

- Use a captura `evidencias/interface/busca_machine_learning.png`.
- Mostre a busca pela linha de comando: `python buscar.py "static site generator" --k 3`.
- Os resultados esperados estão em `CONSULTAS_DEMO.md`.
