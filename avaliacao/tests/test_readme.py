"""A tabela do teste final no README (2.14): o arquivo do site vira a tabela entre os marcadores, e
um arquivo fora da forma não muda nada. Rodar da raiz do repositório:
python -m unittest discover -s avaliacao/tests -t .
"""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from avaliacao import readme

RESULTADOS = {
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "evidencia": "EV-300",
    "n": 80,
    "linhas": {
        "baseline": [{"fracao": 0.5}, {"fracao": 0.625}, None, {"contagem": 2, "de": 24},
                     {"contagem": 0, "de": 56}, {"contagem": 1, "de": 80}, {"fracao": 1},
                     {"ms": [66, 91]}, None],  # fmt: skip
        "execucao1": [{"fracao": 0.9125}, {"fracao": 0.85}, {"fracao": 1}, {"contagem": 0, "de": 24},
                      {"contagem": 3, "de": 56}, {"contagem": 0, "de": 80}, {"fracao": 0.98},
                      {"ms": [130, 1240]}, {"numero": 0.4, "unidade": "LLM calls"}],  # fmt: skip
        "execucao2": [{"fracao": 0.9}, None, None, None, None, None, None, None, {"numero": 1234.5}],
    },
}
README = "# Title\n\nIntro.\n\n" + readme.INICIO + "\n_placeholder_\n" + readme.FIM + "\n\nRest.\n"


class TabelaDoReadme(unittest.TestCase):
    def test_cada_celula_como_o_site_mostra_em_ingles(self):
        self.assertEqual(readme.celula({"fracao": 0.9125}), "91.3%")
        self.assertEqual(readme.celula({"contagem": 2, "de": 80}), "2 / 80")
        self.assertEqual(readme.celula({"ms": [130, 1240]}), "130 / 1,240 ms")
        self.assertEqual(readme.celula({"numero": 1234.5}), "1,234.50")
        self.assertEqual(readme.celula({"numero": 0.4, "unidade": "LLM calls"}), "0.40 LLM calls")
        self.assertEqual(readme.celula(None), "—")

    def test_a_tabela_tem_as_tres_linhas_nas_colunas_do_site_e_diz_de_onde_vem(self):
        bloco = readme.tabela(readme.validar(copy.deepcopy(RESULTADOS)))
        linhas = bloco.splitlines()
        self.assertEqual(linhas[0], "| | " + " | ".join(readme.COLUNAS) + " |")
        self.assertEqual(
            linhas[3],
            "| System · run 1 | 91.3% | 85.0% | 100.0% | 0 / 24 | 3 / 56 | 0 / 80 | 98.0% "
            "| 130 / 1,240 ms | 0.40 LLM calls |",
        )
        self.assertTrue(linhas[2].startswith("| Baseline · rules only | 50.0% | 62.5% | — |"))
        self.assertTrue(linhas[4].startswith("| System · run 2 | 90.0% | — |"))
        self.assertIn("80 held-out scenarios", linhas[-1])
        self.assertIn("`0123456789ab` (EV-300)", linhas[-1])

    def test_o_readme_ganha_a_tabela_so_entre_os_marcadores(self):
        novo = readme.com_a_tabela(README, "TABELA")
        self.assertEqual(novo, "# Title\n\nIntro.\n\n" + readme.INICIO + "\nTABELA\n" + readme.FIM + "\n\nRest.\n")
        self.assertEqual(readme.com_a_tabela(novo, "TABELA"), novo)  # de novo, igual
        self.assertIsNone(readme.com_a_tabela("# Sem marcadores\n", "TABELA"))
        self.assertIsNone(readme.com_a_tabela(README + readme.INICIO, "TABELA"))

    def test_arquivo_fora_da_forma_do_site_nao_vira_tabela(self):
        for mudar in (
            lambda d: d.pop("commit"),
            lambda d: d.update(n="80"),
            lambda d: d["linhas"].pop("execucao2"),
            lambda d: d["linhas"]["baseline"].pop(),
            lambda d: d["linhas"]["execucao1"].__setitem__(0, {"fracao": 1.5}),
            lambda d: d["linhas"]["execucao1"].__setitem__(3, {"contagem": 1, "de": 0}),
            lambda d: d["linhas"]["execucao1"].__setitem__(7, {"ms": [1]}),
            lambda d: d["linhas"]["execucao1"].__setitem__(8, {"outra": 1}),
        ):
            dados = copy.deepcopy(RESULTADOS)
            mudar(dados)
            self.assertIsNone(readme.validar(dados))

    def test_o_comando_escreve_confere_e_nao_mexe_sem_o_arquivo(self):
        with tempfile.TemporaryDirectory() as pasta:
            resultados, arquivo = Path(pasta) / "teste-final.json", Path(pasta) / "README.md"
            arquivo.write_text(README, encoding="utf-8")
            args = ["--resultados", str(resultados), "--readme", str(arquivo)]
            self.assertEqual(readme.main(args), 1)  # sem o arquivo do teste final
            self.assertEqual(arquivo.read_text(encoding="utf-8"), README)
            resultados.write_text(json.dumps(RESULTADOS), encoding="utf-8")
            self.assertEqual(readme.main([*args, "--conferir"]), 1)  # ainda com o placeholder
            self.assertEqual(readme.main(args), 0)
            self.assertIn("| System · run 2 |", arquivo.read_text(encoding="utf-8"))
            self.assertEqual(readme.main([*args, "--conferir"]), 0)


if __name__ == "__main__":
    unittest.main()
