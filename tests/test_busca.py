"""
Testes do mecanismo de busca (ranqueamento BM25/BM25F) e da interface web.

    python -m unittest tests.test_busca -v

Os testes constroem um índice pequeno em memória (sobre um conjunto de
projetos sintéticos) e verificam:

- que o Buscador recupera só os documentos que contêm algum termo da consulta
  (recuperação pelo índice invertido);
- que o ranking põe na frente o documento com o termo em campo de maior peso
  (BM25F) e o documento mais "sobre o assunto" (mais ocorrências);
- que o IDF cai quando o df cresce (termo mais comum pesa menos);
- que a API da interface web devolve exatamente os resultados do Buscador e
  expõe a entrada do índice invertido (df/cf) de cada termo.
"""

import json
import os
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from indexador.busca import Buscador
from indexador.config import IndexConfig
from indexador.construtor import ConstrutorIndice, criar_analisador, analisar_linha
from indexador.indice import Indice


# Projetos sintéticos: controlam em que campo cada termo aparece e quantas vezes.
PROJETOS = [
    # 0: "python" no NOME (peso 3) -> deve vencer para a consulta "python"
    {"site": "github", "url": "u0", "nome": "python", "descricao": "a tool", "readme": "x"},
    # 1: "python" só na DESCRIÇÃO (peso 2)
    {"site": "github", "url": "u1", "nome": "tool", "descricao": "python library", "readme": "x"},
    # 2: "python" só no README (peso 1), uma vez
    {"site": "github", "url": "u2", "nome": "tool", "descricao": "a tool", "readme": "python"},
    # 3: "python" muitas vezes no README (mais sobre o assunto que o doc 2)
    {"site": "github", "url": "u3", "nome": "tool", "descricao": "a tool",
     "readme": "python python python python python"},
    # 4: não contém "python" (não deve ser recuperado)
    {"site": "github", "url": "u4", "nome": "rust", "descricao": "systems", "readme": "fast"},
    # termos extras para variar o df
    {"site": "github", "url": "u5", "nome": "java", "descricao": "jvm", "readme": "common common"},
    {"site": "github", "url": "u6", "nome": "common", "descricao": "common thing", "readme": "common"},
]


def _construir(pasta, **opcoes):
    cfg = IndexConfig(saida=pasta, documentos_por_bloco=3, particoes=3, processos=1, **opcoes)
    analisador = criar_analisador(cfg)
    docs = [analisar_linha(analisador, json.dumps(p)) for p in PROJETOS]
    ConstrutorIndice(cfg).construir(iter(docs))
    return Indice(pasta)


class TestRanqueamento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="busca_teste_")
        cls.idx = _construir(os.path.join(cls.pasta, "campo"), granularidade="campo")
        cls.b = Buscador(cls.idx)

    @classmethod
    def tearDownClass(cls):
        cls.idx.fechar()
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def _docids(self, consulta, k=10):
        return [d for d, _ in self.b.buscar(consulta, k)]

    def test_recupera_so_quem_tem_o_termo(self):
        # "python" aparece nos docs 0..3, nunca no 4,5,6.
        ids = set(self._docids("python"))
        self.assertTrue(ids.issubset({0, 1, 2, 3}))
        self.assertNotIn(4, ids)
        self.assertEqual(ids, {0, 1, 2, 3})

    def test_termo_ausente_nao_retorna_nada(self):
        self.assertEqual(self.b.buscar("inexistentexyz", 10), [])

    def test_peso_de_campo_bm25f(self):
        # "python" no nome (peso 3) deve ranquear acima de "python" só no README.
        ranking = self._docids("python")
        self.assertEqual(ranking[0], 0)            # nome vence
        self.assertLess(ranking.index(0), ranking.index(2))   # nome antes de README único
        self.assertLess(ranking.index(1), ranking.index(2))   # descrição antes de README único

    def test_mais_ocorrencias_ranqueia_acima(self):
        # doc 3 (python x5 no README) deve ficar acima do doc 2 (python x1 no README).
        ranking = self._docids("python")
        self.assertLess(ranking.index(3), ranking.index(2))

    def test_idf_decresce_com_df(self):
        # termo raro (df pequeno) tem IDF maior que termo comum (df grande).
        idf_raro = self.b.idf(1)
        idf_comum = self.b.idf(self.idx.n_unidades)
        self.assertGreater(idf_raro, idf_comum)

    def test_notas_ordenadas_desc(self):
        notas = [n for _, n in self.b.buscar("python", 10)]
        self.assertEqual(notas, sorted(notas, reverse=True))
        self.assertTrue(all(n > 0 for n in notas))

    def test_respeita_k(self):
        self.assertLessEqual(len(self.b.buscar("python", 2)), 2)


class TestInterfaceWeb(unittest.TestCase):
    """A API da interface deve devolver exatamente o resultado do Buscador."""

    @classmethod
    def setUpClass(cls):
        from interface import app
        cls.app = app
        cls.pasta = tempfile.mkdtemp(prefix="iface_teste_")
        cls.idx = _construir(os.path.join(cls.pasta, "campo"), granularidade="campo")
        app.INDICE = cls.idx
        app.BUSCADOR = Buscador(cls.idx)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        cls.porta = cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.idx.fechar()
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def _get(self, path):
        url = f"http://127.0.0.1:{self.porta}{path}"
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read().decode("utf-8")

    def test_info(self):
        status, corpo = self._get("/api/info")
        self.assertEqual(status, 200)
        d = json.loads(corpo)
        self.assertEqual(d["n_documentos"], len(PROJETOS))
        self.assertEqual(d["granularidade"], "campo")

    def test_busca_igual_ao_buscador(self):
        status, corpo = self._get("/api/buscar?q=python&k=10")
        self.assertEqual(status, 200)
        d = json.loads(corpo)
        urls_api = [r["url"] for r in d["resultados"]]
        esperado = [self.idx.documentos[docid]["url"]
                    for docid, _ in self.app.BUSCADOR.buscar("python", 10)]
        self.assertEqual(urls_api, esperado)       # mesma ordem, mesmos documentos

    def test_busca_expoe_entrada_do_indice(self):
        # A API deve mostrar df/cf de cada termo, provando que consulta o índice.
        _, corpo = self._get("/api/buscar?q=python&k=10")
        lex = {l["termo"]: l for l in json.loads(corpo)["lexico"]}
        self.assertIn("python", lex)
        self.assertTrue(lex["python"]["no_indice"])
        self.assertEqual(lex["python"]["df"], self.idx.entrada("python")[0])

    def test_termo_devolve_postings_do_indice(self):
        _, corpo = self._get("/api/termo?t=python")
        t = json.loads(corpo)["termos"][0]
        unidades_idx, _ = self.idx.postings("python")
        unidades_api = [p["unidade"] for p in t["postings"]]
        self.assertEqual(unidades_api, unidades_idx[: len(unidades_api)])
        self.assertEqual(t["df"], self.idx.entrada("python")[0])

    def test_consulta_vazia_400(self):
        try:
            self._get("/api/buscar?q=")
            self.fail("esperava erro HTTP 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)


if __name__ == "__main__":
    unittest.main()
