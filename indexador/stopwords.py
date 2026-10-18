"""
Listas de stopwords.

Inglês: a lista do NLTK (a mesma do Snowball), sem as formas com apóstrofo,
porque o analisador separa "don't" em "don" e "t".

Português: as palavras gramaticais mais comuns, sem acento (o analisador
remove os acentos antes de comparar). Ficaram de fora palavras que também
são termos técnicos em inglês nos READMEs, como "num" (num_workers), "eu",
"sem", "tem" e "ate".

Os termos vêm do texto já em minúsculas e sem acento.
"""

INGLES = frozenset("""
i me my myself we our ours ourselves you your yours yourself yourselves he him
his himself she her hers herself it its itself they them their theirs
themselves what which who whom this that these those am is are was were be
been being have has had having do does did doing a an the and but if or
because as until while of at by for with about against between into through
during before after above below to from up down in out on off over under
again further then once here there when where why how all any both each few
more most other some such no nor not only own same so than too very s t can
will just don should now d ll m o re ve y ain aren couldn didn doesn hadn
hasn haven isn ma mightn mustn needn shan shouldn wasn weren won wouldn
""".split())

PORTUGUES = frozenset("""
de a o que e do da em um para com nao uma os no se na por mais as dos como
mas ao ele das seu sua ou quando muito nos ja tambem so pelo pela isso ela
entre depois mesmo aos seus quem nas me esse eles voce essa nem suas meu
minha pelos elas qual lhe deles essas esses pelas este dele tu te voces
vos lhes meus minhas teu tua nosso nossa nossos nossas dela delas esta estes
estas aquele aquela aqueles aquelas isto aquilo foi ser ter sao estao ha
""".split())

STOPWORDS = INGLES | PORTUGUES
