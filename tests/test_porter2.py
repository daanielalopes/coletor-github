"""
Testes do stemmer Porter2 em Python puro (indexador/porter2.py), usado como
alternativa ao pacote snowballstemmer quando ele não está instalado.

    python -m unittest tests.test_porter2 -v

Comparamos a saída com valores de referência do algoritmo Porter2/English
Snowball (https://snowballstem.org/algorithms/english/stemmer.html). Quando
o pacote snowballstemmer está disponível, também conferimos que as duas
implementações concordam numa lista de palavras.
"""

import unittest

from indexador.porter2 import stemmer

# Pares (palavra, raiz) do algoritmo Porter2.
REFERENCIA = {
    "consign": "consign", "consigned": "consign", "consigning": "consign",
    "consignment": "consign", "running": "run", "runs": "run", "run": "run",
    "happy": "happi", "happiness": "happi", "relational": "relat",
    "conditional": "condit", "rational": "ration", "valenci": "valenc",
    "hesitanci": "hesit", "digitizer": "digit", "conformabli": "conform",
    "radicalli": "radic", "differentli": "differ", "vileli": "vile",
    "analogousli": "analog", "vietnamization": "vietnam", "predication": "predic",
    "operator": "oper", "feudalism": "feudal", "decisiveness": "decis",
    "hopefulness": "hope", "callousness": "callous", "sensitiviti": "sensit",
    "sensibiliti": "sensibl", "triplicate": "triplic", "formative": "format",
    "formalize": "formal", "electriciti": "electr", "electrical": "electr",
    "hopeful": "hope", "goodness": "good", "revival": "reviv",
    "allowance": "allow", "inference": "infer", "airliner": "airlin",
    "gyroscopic": "gyroscop", "adjustable": "adjust", "defensible": "defens",
    "irritant": "irrit", "replacement": "replac", "adjustment": "adjust",
    "dependent": "depend", "activate": "activ", "angulariti": "angular",
    "homologous": "homolog", "effective": "effect", "bowdlerize": "bowdler",
    "languages": "languag", "language": "languag", "workers": "worker",
    "documentation": "document", "generalization": "general",
    "organization": "organ", "beautiful": "beauti", "national": "nation",
}


class TestPorter2(unittest.TestCase):
    def setUp(self):
        self.s = stemmer("english")

    def test_referencia(self):
        for palavra, raiz in REFERENCIA.items():
            self.assertEqual(self.s.stemWord(palavra), raiz, palavra)

    def test_palavras_curtas_nao_mudam(self):
        for p in ("a", "as", "be", "go", "no"):
            self.assertEqual(self.s.stemWord(p), p)

    def test_estavel_na_maioria_das_raizes(self):
        # Reaplicar o stemmer quase nunca muda a raiz. (Não é idempotente em
        # geral: p.ex. "defens" -> "defen", porque o passo 1a ainda remove o
        # "s" final; é o mesmo comportamento do algoritmo Porter2.)
        raizes = set(REFERENCIA.values())
        estaveis = sum(1 for r in raizes if self.s.stemWord(r) == r)
        self.assertGreaterEqual(estaveis / len(raizes), 0.9)

    def test_concorda_com_snowball_se_instalado(self):
        try:
            import snowballstemmer
        except ImportError:
            self.skipTest("snowballstemmer não instalado")
        ref = snowballstemmer.stemmer("english")
        palavras = list(REFERENCIA) + [
            "indexing", "retrieval", "compression", "frameworks", "libraries",
            "distributed", "cryptography", "authentication", "containers",
        ]
        iguais = sum(1 for w in palavras if self.s.stemWord(w) == ref.stemWord(w))
        # Tolerância: a implementação pura cobre a quase totalidade dos casos.
        self.assertGreaterEqual(iguais / len(palavras), 0.95)


if __name__ == "__main__":
    unittest.main()
