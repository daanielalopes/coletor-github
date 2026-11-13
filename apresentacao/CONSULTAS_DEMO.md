# Cinco consultas para a demonstração

Resultados reais sobre o **índice de amostra** (100 projetos de
`evidencias/amostra_projetos.jsonl`), medidos com:

```
mkdir -p data && cp evidencias/amostra_projetos.jsonl data/projetos.jsonl
python run_indexador.py --processos 1
python buscar.py "<consulta>" --k 3
```

> As notas e a ordem dependem do acervo. Com o índice completo (52.000
> projetos) os projetos retornados serão outros, mas o comportamento do ranking
> é o mesmo. Rode no mesmo acervo que você vai apresentar.

---

## 1. `static site generator` — o ranking BM25F em ação

```
 1.  7.83  [github]  tumblelog     A static tumblelog generator (Perl e Python)
 2.  3.23  [github]  HibiAPI       ...easy-to-use APIs for a variety of common sites
 3.  2.44  [github]  sitemap.js    Sitemap-generating framework for node.js
```

**Por que é interessante:** o 1º lugar tem os três termos, dois deles no
nome/descrição, e abre grande distância (7,83 contra 3,23). É o exemplo mais
claro do efeito dos pesos de campo do BM25F.

## 2. `game engine c++` — termos técnicos com símbolos

```
consulta -> termos ['game', 'engin', 'cpp']
 1.  3.42  [sourceforge]  Spillwords    ...board game "Spill and Spell" ... Qt 3.1
 2.  3.25  [sourceforge]  firmataplus   C++ interface library for Arduino ...
 3.  3.21  [sourceforge]  Dolphin       ...video game console emulator (GameCube/Wii)
```

**Por que é interessante:** mostre que `c++` virou o termo `cpp` (e não `c`).
É a regra de termos técnicos do analisador (c++, c#, .net, node.js...).

## 3. `machine learning` — stemming e campos

```
consulta -> termos ['machin', 'learn']
 1.  4.35  [github]  advanced-machine-learning-engineer-roadmap-2024
 2.  3.30  [github]  audio-ai-timeline
 3.  2.25  [github]  nexus-zkvm
```

**Por que é interessante:** `machine`/`learning` sofrem stemming para
`machin`/`learn`, então "learns", "learning" e "machines" caem no mesmo termo.
O 1º lugar tem os dois termos no nome.

## 4. `python web framework` — consulta com 3 termos, dois sites

```
consulta -> termos ['python', 'web', 'framework']
 1.  4.57  [sourceforge]  CEF Python   Python bindings for the Chromium Embedded Framework
 2.  3.59  [sourceforge]  Laravel      Laravel is a free, open-source PHP web framework
 3.  3.01  [github]       dash-oil-and-gas-demo
```

**Por que é interessante:** resultados dos dois sites (GitHub e SourceForge) na
mesma lista — mostra a unificação dos campos na indexação.

## 5. `password manager` — recuperação por índice invertido

```
consulta -> termos ['password', 'manag']
 1.  4.05  [github]       docs                  Lightweight document management system ...
 2.  1.62  [sourceforge]  SQL Embedded Manager
 3.  1.59  [sourceforge]  OpenResty Manager
```

**Por que é interessante:** `manager`/`management` → `manag` (stemming). Use
esta consulta para abrir o **detalhe do termo** na interface (ou
`python buscar.py --termo "password manager"`) e mostrar as postings lidas do
índice — a prova de que a recuperação vem do índice invertido.

---

### Demonstração da recuperação pelo índice (qualquer consulta)

```
python buscar.py --termo "password manager"
```
Mostra, para cada termo, `df`, `cf`, a partição e as primeiras postings (unidade
+ frequência por campo) lidas diretamente do índice no disco.
