"""
Testes do indexador.

    python -m unittest discover -s tests -v

O teste principal constrói índices pequenos (os 400 primeiros projetos, em
blocos de 97 documentos e 7 partições, para exercitar a fusão) e compara
cada lista de postings e de posições com o resultado calculado por força
bruta, termo a termo, nas três granularidades.
"""

import os
import random
import shutil
import tempfile
import unittest
from collections import defaultdict

from indexador import vbyte
from indexador.analisador import Analisador
from indexador.config import IndexConfig
from indexador.construtor import ConstrutorIndice, analisar_linha, criar_analisador, unidades
from indexador.documentos import ler_linhas
from indexador.indice import Indice

ENTRADA = os.path.join(os.path.dirname(__file__), "..", "data", "projetos.jsonl")


class TestVByte(unittest.TestCase):
    def test_ida_e_volta(self):
        random.seed(7)
        numeros = [0, 1, 127, 128, 16383, 16384, 2**21, 2**32 - 1] + [random.randrange(10**7) for _ in range(5000)]
        buf = vbyte.codificar_lista(numeros)
        self.assertEqual(vbyte.decodificar_tudo(buf), numeros)
        pos, lidos = 0, []
        while pos < len(buf):
            n, pos = vbyte.decodificar(buf, pos)
            lidos.append(n)
        self.assertEqual(lidos, numeros)

    def test_tamanho(self):
        self.assertEqual(len(vbyte.codificar(127)), 1)
        self.assertEqual(len(vbyte.codificar(128)), 2)
        self.assertEqual(len(vbyte.codificar(16384)), 3)
        self.assertEqual(vbyte.codificar(5), bytes([0x85]))          # exemplo do livro
        self.assertEqual(vbyte.codificar(824), bytes([0x06, 0xB8]))


class TestAnalisador(unittest.TestCase):
    def setUp(self):
        self.a = Analisador()

    def test_termos_tecnicos(self):
        self.assertEqual(self.a.analisar("C++ and C# on .NET with Node.js"),
                         ["cpp", "csharp", "dotnet", "nodejs"])
        self.assertEqual(self.a.analisar("C++17 apps for iOS and macOS"), ["cpp", "17", "app", "ios", "macos"])

    def test_limpeza(self):
        texto = "Docs at https://example.com/x?y=1 <img src='a.png'> mail me@x.org &amp; python"
        self.assertEqual(self.a.analisar(texto), ["doc", "mail", "python"])

    def test_invisiveis_e_largura_total(self):
        self.assertEqual(self.a.analisar("Ｐｙｔｈｏｎ file​name"), ["python", "filenam"])

    def test_compostos_e_camel(self):
        self.assertEqual(self.a.analisar("tcp-server num_workers"), ["tcp", "server", "num", "worker"])
        self.assertEqual(self.a.analisar("FileWizardAI", "nome"), ["filewizardai", "file", "wizard", "ai"])
        self.assertEqual(self.a.analisar("JavaScript"), ["javascript"])   # fora do nome não quebra

    def test_ideogramas_e_acentos(self):
        self.assertEqual(self.a.analisar("简体中文 Português"), ["简体", "体中", "中文", "portugu"])

    def test_filtros_e_stopwords(self):
        self.assertEqual(self.a.analisar("the R and c language v2 2024 1234567 a"),
                         ["r", "c", "languag", "v2", "2024"])

    def test_sem_stemming_sem_stopwords(self):
        a = Analisador(remover_stopwords=False, stemming=False)
        self.assertEqual(a.analisar("The running dogs"), ["the", "running", "dogs"])


@unittest.skipUnless(os.path.exists(ENTRADA), "data/projetos.jsonl não encontrado")
class TestIndiceContraForcaBruta(unittest.TestCase):
    N = 400

    @classmethod
    def setUpClass(cls):
        cls.pasta = tempfile.mkdtemp(prefix="indice_teste_")
        cls.linhas = list(ler_linhas(ENTRADA, cls.N))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.pasta, ignore_errors=True)

    def _verificar(self, **opcoes):
        cfg = IndexConfig(saida=os.path.join(self.pasta, "_".join(f"{k}{v}" for k, v in opcoes.items())),
                          documentos_por_bloco=97, particoes=7, processos=1, **opcoes)
        analisador = criar_analisador(cfg)
        docs = [analisar_linha(analisador, linha) for linha in self.linhas]
        meta = ConstrutorIndice(cfg).construir(iter(docs))
        self.assertGreater(meta["n_blocos"], 1)

        # Força bruta: termo -> unidade -> posições em cada campo
        nf = len(cfg.campos())
        esperado = defaultdict(dict)
        uid = 0
        unidade_doc = []
        for docid, (_, termos) in enumerate(docs):
            for segs in unidades(cfg, termos):
                for f, lst, base in segs:
                    for p, t in enumerate(lst, base):
                        esperado[t].setdefault(uid, [[] for _ in range(nf)])[f].append(p)
                unidade_doc.append(docid)
                uid += 1

        idx = Indice(cfg.saida)
        self.assertEqual(idx.n_unidades, uid)
        self.assertEqual(idx.carregar_lexico_inteiro(), len(esperado))
        for termo, por_unidade in esperado.items():
            unidades_lidas, tfs = idx.postings(termo)
            self.assertEqual(unidades_lidas, sorted(por_unidade), termo)
            self.assertEqual(tfs, [tuple(len(l) for l in por_unidade[u]) for u in unidades_lidas], termo)
            if cfg.posicoes:
                self.assertEqual(idx.posicoes(termo), [por_unidade[u] for u in unidades_lidas], termo)
            df, cf, *_ = idx.entrada(termo)
            self.assertEqual(df, len(por_unidade))
            self.assertEqual(cf, sum(len(l) for ps in por_unidade.values() for l in ps))
        for u in range(uid):
            self.assertEqual(idx.doc_da_unidade(u), unidade_doc[u])
        self.assertEqual(len(idx.documentos), len(self.linhas))
        idx.fechar()

    def test_campo(self):
        self._verificar(granularidade="campo")

    def test_documento_sem_posicoes(self):
        self._verificar(granularidade="documento", posicoes=False)

    def test_chunk_com_sobreposicao(self):
        self._verificar(granularidade="chunk", tamanho_chunk=50, sobreposicao=10)


if __name__ == "__main__":
    unittest.main()
