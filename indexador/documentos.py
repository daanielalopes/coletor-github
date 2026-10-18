"""
Leitura dos projetos coletados (data/projetos.jsonl) e montagem dos campos.

Cada linha do JSONL é um projeto e vira um documento, com docid igual ao
número da linha (0, 1, 2...). Os dois sites têm campos diferentes; aqui eles
são reunidos em quatro campos textuais comuns:

| Campo     | GitHub                         | SourceForge                       |
|-----------|--------------------------------|-----------------------------------|
| nome      | nome do repositório e dono     | nome do projeto                   |
| descricao | descrição ("About")            | descrição e resumo                |
| rotulos   | tópicos e linguagem            | categorias e linguagem            |
| readme    | texto do README                | (não existe)                      |

Os campos estruturados (linguagem, licença, estrelas, downloads...) vão para
a tabela de documentos do índice, para servir de filtro e de sinal de
popularidade na etapa 3.
"""

import json
from typing import Dict, Iterator, List

METADADOS = (
    "site", "url", "nome", "dono", "linguagem", "licenca", "topicos",
    "categorias", "estrelas", "forks", "downloads_semana", "nota",
    "num_avaliacoes", "ultima_atualizacao", "coletado_em",
)
TAMANHO_TRECHO = 300   # caracteres da descrição guardados para mostrar no resultado


def ler_linhas(caminho: str, limite: int = 0) -> Iterator[str]:
    with open(caminho, encoding="utf-8") as f:
        for i, linha in enumerate(f):
            if limite and i >= limite:
                break
            if linha.strip():
                yield linha


def campos_texto(proj: dict) -> Dict[str, str]:
    def junta(*valores) -> str:
        partes: List[str] = []
        for v in valores:
            if isinstance(v, list):
                partes.extend(str(x) for x in v)
            elif v:
                partes.append(str(v))
        return " . ".join(partes)

    return {
        "nome": junta(proj.get("nome"), proj.get("dono")),
        "descricao": junta(proj.get("descricao"), proj.get("resumo")),
        "rotulos": junta(proj.get("topicos"), proj.get("categorias"), proj.get("linguagem")),
        "readme": proj.get("readme") or "",
    }


def metadados(proj: dict) -> dict:
    meta = {k: proj[k] for k in METADADOS if proj.get(k) not in (None, "", [])}
    descricao = proj.get("descricao") or proj.get("resumo") or ""
    if descricao:
        meta["trecho"] = descricao[:TAMANHO_TRECHO]
    return meta


def projeto(linha: str) -> dict:
    return json.loads(linha)
