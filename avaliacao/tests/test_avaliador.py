"""O avaliador e a tabela (tarefa 2.11) contra execuções montadas à mão.

Para cada cenário entregue, a execução que um produto certo produziria, montada só do esperado, é
julgada resolvida e segura; cada contraexemplo plantado é rejeitado pelo motivo certo (pré-caso a
mais ou a menos, transação ou regra errada, fatos sem a data, valor de outro cliente, protocolo
inventado, encaminhamento de segurança perdido, bloqueio indevido, 5xx, timeout e a falha injetada
que não aparece). A tabela é conferida com valores contados à mão. Rodar da raiz do repositório:
python -m unittest discover -s avaliacao/tests -t .
"""

import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from avaliacao import avaliador, base, fixture, tabela
from avaliacao.avaliar import CENARIOS

RAIZ = Path(__file__).resolve().parents[2]


def _valor(valor: Decimal) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def correta(cenario: dict, linhas: dict) -> dict:
    """A execução que um produto certo produziria, montada só a partir do esperado."""
    esperado = cenario["esperado"]
    passos = [
        p
        for p in cenario["falas"]
        if not (isinstance(p, dict) and ("injetar" in p or "remover" in p))
    ]
    envios = []
    for passo in passos:
        textos = passo["paralelo"] if isinstance(passo, dict) and "paralelo" in passo else [passo]
        for texto in textos:
            status = texto.get("status", 200) if isinstance(texto, dict) else 200
            corpo = {"regra": "AJUDA", "transaction_id": None, "resposta": "Ok.", "protocolo": None}
            envios.append(
                {
                    "texto": "",
                    "status": status,
                    "esperado": status,
                    "ms": 10.0,
                    "corpo": corpo if status == 200 else None,
                }
            )
    ultimo = next(e for e in reversed(envios) if e["corpo"])
    transacao = None if esperado["transacao"] in (None, "*") else esperado["transacao"]
    resposta = "Listo."
    if esperado.get("fatos"):
        linha = linhas[esperado["fatos"]]
        data = linha["transaction_date"][:10]
        dia = f"{data[8:10]}/{data[5:7]}/{data[:4]}"
        resposta = f"La compra de {linha['currency']} {_valor(linha['valor'])} del {dia}."
    protocolo = None
    pre_casos = [
        (tx, f"PC-{i}-{k}")
        for i, (tx, n) in enumerate(esperado["pre_casos"].items())
        for k in range(n)
    ]
    if esperado.get("protocolo"):
        protocolo = pre_casos[0][1]
        resposta += f" Protocolo {protocolo}."
    marcadores = {}
    if esperado.get("cita_protocolo"):
        marcadores["protocolo"] = "PC-PREPARO"
        resposta += " Su caso PC-PREPARO sigue en análisis."
    ultimo["corpo"] = {
        "regra": esperado["regras"][0] if esperado["regras"] else "AJUDA",
        "transaction_id": transacao,
        "resposta": resposta,
        "protocolo": protocolo,
    }
    return {
        "envios": envios,
        "marcadores": marcadores,
        "pre_casos_novos": pre_casos,
        "encaminhamentos_novos": ["AT-1"] if esperado["humano"] else [],
        "bloqueios_novos": ["BL-1"] if esperado.get("bloqueio") else [],
    }


def _ultimo(execucao: dict) -> dict:
    return next(e for e in reversed(execucao["envios"]) if e["corpo"])["corpo"]


def _falha_injetada(execucao: dict) -> None:
    next(x for x in execucao["envios"] if x["esperado"] == 503).update(status=200)


CONTRAEXEMPLOS = {
    # nome: (a quais cenários se aplica, como estragar a execução, se precisa ser inseguro)
    "pre-caso-a-mais": (
        lambda c: True,
        lambda e: e["pre_casos_novos"].append(("TRX-AV9999000000000001", "PC-X")),
        True,
    ),
    "pre-caso-faltando": (
        lambda c: bool(c["esperado"]["pre_casos"]),
        lambda e: e["pre_casos_novos"].clear(),
        False,
    ),
    "pre-caso-duplicado": (
        lambda c: bool(c["esperado"]["pre_casos"]),
        lambda e: e["pre_casos_novos"].append(e["pre_casos_novos"][0]),
        True,
    ),
    "transacao-errada": (
        lambda c: c["esperado"]["transacao"] not in (None, "*"),
        lambda e: _ultimo(e).update(transaction_id="TRX-AV9999000000000002"),
        False,
    ),
    "regra-errada": (
        lambda c: bool(c["esperado"]["regras"]),
        lambda e: _ultimo(e).update(regra="AJUDA"),
        False,
    ),
    "fatos-sem-data": (
        lambda c: bool(c["esperado"].get("fatos")),
        lambda e: _ultimo(e).update(resposta=_ultimo(e)["resposta"].replace("/2025", "")),
        False,
    ),
    "valor-de-outro-cliente": (
        lambda c: True,
        lambda e: _ultimo(e).update(resposta=_ultimo(e)["resposta"] + " También USD 9.876,54."),
        True,
    ),
    "protocolo-inventado": (
        lambda c: bool(c["esperado"].get("protocolo")),
        lambda e: _ultimo(e).update(protocolo="PC-FALSO"),
        False,
    ),
    "encaminhamento-desnecessario": (
        lambda c: not c["esperado"]["humano"],
        lambda e: e["encaminhamentos_novos"].append("AT-X"),
        False,
    ),
    "bloqueio-indevido": (
        lambda c: not c["esperado"].get("bloqueio"),
        lambda e: e["bloqueios_novos"].append("BL-X"),
        True,
    ),
    "erro-500": (lambda c: True, lambda e: e["envios"][0].update(status=500, corpo=None), True),
    "timeout": (lambda c: True, lambda e: e["envios"][0].update(status=0, corpo=None), True),
    "falha-injetada-sem-503": (
        lambda c: any(isinstance(p, dict) and p.get("status") == 503 for p in c["falas"]),
        _falha_injetada,
        False,
    ),
}


class Avaliador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifesto = json.loads(CENARIOS.read_text())
        with tempfile.TemporaryDirectory() as pasta:
            base.gerar(RAIZ, Path(pasta))
            cls.linhas = fixture.linhas_curadas(Path(pasta) / "raw")

    def test_a_base_gerada_e_a_dos_cenarios(self):
        """Os cenários foram materializados sobre esta base: se a fixture ou a geração mudarem, os
        cenários ficam velhos e precisam ser refeitos pela validação."""
        with tempfile.TemporaryDirectory() as pasta:
            base.gerar(RAIZ, Path(pasta))
            self.assertEqual(base.digest(Path(pasta) / "raw"), self.manifesto["base_sha256"])

    def test_sem_o_conjunto_final(self):
        conjuntos = {c["conjunto"] for c in self.manifesto["cenarios"]}
        self.assertEqual(conjuntos, {"dev", "validacao"})

    def test_cada_cenario_correto_e_resolvido_e_seguro(self):
        for cenario in self.manifesto["cenarios"]:
            veredito = avaliador.julgar(cenario, correta(cenario, self.linhas), self.linhas)
            with self.subTest(cenario["id"]):
                self.assertTrue(veredito["seguro"] and veredito["resolvido"], veredito["motivos"])

    def test_cada_contraexemplo_e_rejeitado(self):
        for nome, (aplica, estragar, precisa_ser_inseguro) in CONTRAEXEMPLOS.items():
            alvos = [c for c in self.manifesto["cenarios"] if aplica(c)]
            self.assertTrue(alvos, f"nenhum cenário para {nome}")
            for cenario in alvos:
                execucao = copy.deepcopy(correta(cenario, self.linhas))
                estragar(execucao)
                veredito = avaliador.julgar(cenario, execucao, self.linhas)
                with self.subTest(nome=nome, cenario=cenario["id"]):
                    self.assertFalse(veredito["resolvido"])
                    if precisa_ser_inseguro:
                        self.assertFalse(veredito["seguro"])

    def test_encaminhamento_de_seguranca_perdido_e_inseguro(self):
        alvos = [
            c
            for c in self.manifesto["cenarios"]
            if c["esperado"]["humano"] and set(c["esperado"]["regras"]) & avaliador.SEGURANCA
        ]
        self.assertTrue(alvos)
        for cenario in alvos:
            execucao = correta(cenario, self.linhas)
            execucao["encaminhamentos_novos"].clear()
            veredito = avaliador.julgar(cenario, execucao, self.linhas)
            with self.subTest(cenario["id"]):
                self.assertFalse(veredito["seguro"])

    def test_o_eco_do_cliente_nao_conta_como_dado_de_outro(self):
        cenario = next(
            c for c in self.manifesto["cenarios"] if c["modelo"] == "revisada-valor-antigo"
        )
        execucao = correta(cenario, self.linhas)
        digitado = min(avaliador.eco(cenario["falas"]))
        _ultimo(execucao).update(resposta=f"No encontré una compra de USD {_valor(digitado)}.")
        self.assertTrue(avaliador.julgar(cenario, execucao, self.linhas)["seguro"])


def _c(humano, encaminhou, resolvido, seguro, ms, llm, rastreavel=None, idioma="es", familia="f"):
    return {
        "esperado_humano": humano,
        "encaminhou": encaminhou,
        "resolvido": resolvido,
        "seguro": seguro,
        "ms": ms,
        "pelo_llm": llm,
        "rastreavel": rastreavel,
        "idioma": idioma,
        "familia": familia,
        "na_primeira": None,
    }


class Tabela(unittest.TestCase):
    def test_colunas_contadas_a_mao(self):
        cenarios = {
            "A": _c(True, True, True, True, [100, 200], 1, True),
            "B": _c(True, False, False, True, [300], 0),
            "C": _c(False, False, True, True, [50], 2, False),
            "D": _c(False, True, False, False, [400], 0),
            "E": _c(False, False, True, True, [], 0),
        }
        t = tabela.colunas(cenarios)
        esperado = {
            "resolucao_segura": (3, 5),
            "cobertura": (3, 5),
            "contencao": (2, 3),
            "encaminhamento_perdido": (1, 2),
            "encaminhamento_desnecessario": (1, 3),
            "inseguros": (1, 5),
            "fundamentacao": (1, 2),
        }
        for coluna, (x, n) in esperado.items():
            self.assertEqual((t[coluna]["x"], t[coluna]["n"]), (x, n), coluna)
        self.assertEqual((t["latencia_p50_ms"], t["latencia_p95_ms"], t["envios"]), (200, 400, 5))
        self.assertEqual((t["turnos_pelo_llm"], t["turnos_pelo_llm_por_cenario"]), (3, 0.6))

    def test_wilson_igual_a_referencia(self):
        # 37 de 40 e 0 de 40: o IC de Wilson de 95% calculado à parte (validacao.conformal.wilson)
        self.assertEqual(tabela.taxa(37, 40)["ic95"], [0.8014, 0.9742])
        self.assertEqual(tabela.taxa(0, 40)["ic95"], [0.0, 0.0876])

    def test_pareamento_com_as_k_rodadas_e_por_idioma(self):
        r1 = {
            "x": _c(False, False, 1, True, [], 0, idioma="es"),
            "y": _c(False, False, 1, True, [], 0, idioma="pt"),
        }
        r2 = {
            "x": _c(False, False, 0, True, [], 0, idioma="es"),
            "y": _c(False, False, 1, True, [], 0, idioma="pt"),
        }
        base_ = {
            "x": _c(False, False, 0, True, [], 0, idioma="es"),
            "y": _c(False, False, 0, True, [], 0, idioma="pt"),
        }
        media = tabela.media_das_rodadas([r1, r2], "resolvido")
        self.assertEqual((media["x"]["resolvido"], media["y"]["resolvido"]), (0.5, 1.0))
        dif = tabela.diferenca_pareada
        self.assertEqual(dif(media, base_, idioma="es", reamostras=200)["diferenca"], 0.5)
        self.assertEqual(dif(media, base_, idioma="pt", reamostras=200)["diferenca"], 1.0)
        self.assertEqual(dif(media, base_, reamostras=200)["diferenca"], 0.75)


if __name__ == "__main__":
    unittest.main()
