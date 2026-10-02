"""Leitor e5, lado do treino: fontes fixadas, corpus alinhado, calibração e artefato.

Tudo com arquivos pequenos escritos aqui (servidos por file://, sem rede) e um codificador falso e
determinístico no lugar do e5 (a imagem de testes não tem torch): o que se testa é o código do
leitor, não os pesos do modelo.
"""

import csv
import hashlib
from pathlib import Path
from typing import get_args

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from jeje.interpretacao import Intencao
from jeje.leitor import __main__ as cli
from jeje.leitor import codificador, corpus, fontes
from jeje.leitor.corpus import Corpus, CorpusInvalido, Exemplo, Tabela
from jeje.leitor.fluxos import (
    FLUXO_DO_BANKING77,
    FLUXO_DO_MINDS14,
    FLUXOS,
    LEITURA_DO_FLUXO,
    fluxo_do_banking77,
    fluxo_do_minds14,
)
from jeje.leitor.fontes import Arquivo, FonteInvalida
from jeje.leitor.modelo import ModeloInvalido, ModeloLeitor, versao


def codificar(textos) -> np.ndarray:
    """Codificador falso: saco de palavras com hash em 64 posições, normalizado (como o e5)."""
    vetores = np.zeros((len(textos), 64), dtype=np.float32)
    for i, texto in enumerate(textos):
        for palavra in texto.lower().split():
            vetores[i, int(hashlib.md5(palavra.encode()).hexdigest(), 16) % 64] += 1
    normas = np.linalg.norm(vetores, axis=1, keepdims=True)
    return vetores / np.where(normas == 0, 1, normas)


def arquivo_de(caminho: Path, nome: str) -> Arquivo:
    conteudo = caminho.read_bytes()
    return Arquivo(nome, caminho.as_uri(), len(conteudo), hashlib.sha256(conteudo).hexdigest())


# ---- fontes ----


def test_baixar_confere_o_hash_e_nao_baixa_de_novo_o_que_ja_esta_integro(tmp_path):
    origem = tmp_path / "origem.txt"
    origem.write_text("pesos")
    arquivos = (arquivo_de(origem, "sub/pesos.txt"),)
    assert fontes.baixar(tmp_path / "destino", arquivos) == 1
    assert (tmp_path / "destino" / "sub" / "pesos.txt").read_text() == "pesos"
    assert fontes.baixar(tmp_path / "destino", arquivos) == 0


def test_baixar_recusa_conteudo_diferente_do_fixado_sem_deixar_arquivo(tmp_path):
    origem = tmp_path / "origem.txt"
    origem.write_text("pesos")
    adulterado = Arquivo("pesos.txt", origem.as_uri(), 5, "0" * 64)
    with pytest.raises(FonteInvalida, match="difere do fixado"):
        fontes.baixar(tmp_path / "destino", (adulterado,))
    assert list((tmp_path / "destino").iterdir()) == []


def test_e5_recusa_diretorio_com_peso_adulterado_antes_de_carregar(tmp_path):
    with pytest.raises(FonteInvalida, match=r"config\.json"):
        codificador.E5(tmp_path)
    for peso in codificador.PESOS:
        (tmp_path / peso.nome).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / peso.nome).write_bytes(b"x" * min(peso.bytes, 10))
    with pytest.raises(FonteInvalida, match="diferente do fixado"):
        codificador.E5(tmp_path)


def test_pesos_do_e5_fixados_pela_revisao():
    assert all(f"/resolve/{codificador.REVISAO}/" in p.url for p in codificador.PESOS)
    assert {"model.safetensors", "tokenizer.json", "modules.json"} <= {
        p.nome for p in codificador.PESOS
    }


# ---- fluxos ----


def test_intencao_fora_do_mapeamento_e_fora_de_escopo():
    assert fluxo_do_banking77("balance") == "fora_de_escopo"
    assert fluxo_do_banking77("declined_transfer") == "explicar_recusa"
    assert fluxo_do_minds14("pay_bill") == "fora_de_escopo"
    assert fluxo_do_minds14("freeze") == "relato_de_fraude"
    cobertos = set(FLUXO_DO_BANKING77.values()) | set(FLUXO_DO_MINDS14.values())
    assert cobertos == set(FLUXOS) - {"fora_de_escopo"}


def test_todo_fluxo_vira_uma_intencao_do_interpretador_com_status_so_na_consulta():
    assert set(LEITURA_DO_FLUXO) == set(FLUXOS)
    for intencao, status in LEITURA_DO_FLUXO.values():
        assert intencao in get_args(Intencao)
        assert status is None or intencao == "consultar"
    assert LEITURA_DO_FLUXO["explicar_estorno"] == ("consultar", "Reversed")


# ---- corpus ----

# (texto en, intenção en, texto es, rótulo es inconsistente, texto pt, rótulo pt traduzido)
ALINHADO = [
    ("my card was declined", "declined_card_payment", "rechazaron mi tarjeta", "rech_x",
     "meu cartão foi recusado", "pagamento_recusado"),
    ("transfer still pending", "pending_transfer", "transferencia pendiente", "pend",
     "transferência pendente", "transferencia_pendente"),
    ("what is my balance", "balance", "cuál es mi saldo", "saldo!!", "qual meu saldo", "saldo"),
    ("card declined again", "declined_card_payment", "tarjeta rechazada", "otro",
     "cartão recusado de novo", "pagamento_recusado"),
    ("someone stole my card", "lost_or_stolen_card", "me robaron la tarjeta", "robo",
     "roubaram meu cartão", "cartao_roubado"),
]  # fmt: skip


def escrever_csv(caminho: Path, cabecalho: list[str], linhas: list[tuple]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(cabecalho)
        escritor.writerows(linhas)


def tabelas_de_teste(origem: Path, linhas=ALINHADO, pt_teste_extra=()) -> tuple[Tabela, ...]:
    """Seis CSVs no formato das fontes reais; o teste PT termina com uma linha sem texto."""
    tabelas = []
    for particao in ("treino", "teste"):
        caminhos = {i: origem / f"{i}_{particao}.csv" for i in ("en", "es", "pt")}
        escrever_csv(caminhos["en"], ["text", "category"], [(a, b) for a, b, *_ in linhas])
        escrever_csv(caminhos["es"], ["frase", "rotulo", "cambiado"],
                     [(c, d, 0) for _, _, c, d, _, _ in linhas])  # fmt: skip
        extra = [*pt_teste_extra, ("", "")] if particao == "teste" else []
        escrever_csv(caminhos["pt"], ["frase", "rotulo", "modelo_tradutor", "alterado"],
                     [(e, f, "gpt", 0) for *_, e, f in linhas]
                     + [(t, r, "gpt", 0) for t, r in extra])  # fmt: skip
        colunas = {"en": ("text", "category"), "es": ("frase", "rotulo"), "pt": ("frase", "rotulo")}
        for idioma, caminho in caminhos.items():
            nome = f"banking77/{idioma}_{particao}.csv"
            tabelas.append(Tabela(idioma, particao, arquivo_de(caminho, nome), *colunas[idioma]))
    return tuple(tabelas)


def parquet_minds14(caminho: Path, linhas: list[tuple[str, str, int]]) -> None:
    """(caminho do áudio, transcrição, classe) no formato do MInDS-14 (o áudio não é lido)."""
    tabela = pa.table({
        "path": [p for p, _, _ in linhas], "audio": [b"" for _ in linhas],
        "transcription": [t for _, t, _ in linhas], "intent_class": [c for *_, c in linhas],
    })  # fmt: skip
    caminho.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tabela, caminho)


MINDS = [
    ("es-ES~CARD_ISSUES/a.wav", "mi tarjeta no funciona", 6),
    ("es-ES~FREEZE/b.wav", "quiero bloquear la tarjeta", 9),
    ("es-ES~LATEST_TRANSACTIONS/c.wav", "ver mis movimientos", 12),
    ("es-ES~PAY_BILL/d.wav", "pagar una factura", 13),
    ("es-ES~BALANCE/e.wav", "   ", 4),  # transcrição vazia: não vira exemplo
]


def fontes_de_teste(origem: Path, minds=MINDS, **kwargs):
    tabelas = tabelas_de_teste(origem, **kwargs)
    parquet_minds14(origem / "es.parquet", minds)
    return tabelas, (("es", arquivo_de(origem / "es.parquet", "minds14/es-ES.parquet")),)


def lido(tmp_path, **kwargs) -> Corpus:
    tabelas, minds = fontes_de_teste(tmp_path / "origem", **kwargs)
    fontes.baixar(tmp_path / "d", corpus.arquivos(tabelas, minds))
    return corpus.ler(tmp_path / "d", tabelas, minds)


def test_espanhol_herda_a_intencao_do_ingles_pela_posicao(tmp_path):
    lidos = lido(tmp_path)
    espanhol = {e.texto: e.fluxo for e in lidos.teste if e.idioma == "es"}
    assert espanhol == {
        "rechazaron mi tarjeta": "explicar_recusa",
        "transferencia pendiente": "explicar_pendencia",
        "cuál es mi saldo": "fora_de_escopo",
        "tarjeta rechazada": "explicar_recusa",
        "me robaron la tarjeta": "relato_de_fraude",
    }


def test_corpus_guarda_o_treino_oficial_inteiro_na_ordem_do_arquivo(tmp_path):
    """A garantia de fraude refaz nele a divisão da validação, pela posição de cada frase."""
    oficial = [(e.idioma, e.texto) for e in lido(tmp_path).oficial]
    assert oficial == ([("en", a) for a, *_ in ALINHADO] + [("es", c) for _, _, c, *_ in ALINHADO]
                       + [("pt", e) for *_, e, _ in ALINHADO])  # fmt: skip


def test_cada_frase_guarda_o_rotulo_do_corpus_de_onde_veio_o_fluxo(tmp_path):
    """Os exemplos do LLM do "não entendi" (DEV-042) usam o rótulo do corpus, não o fluxo."""
    lidos = lido(tmp_path, pt_teste_extra=[("pix recusado", "pagamento_recusado")])
    rotulo = {(e.idioma, e.texto): e.intencao for e in lidos.teste + lidos.treino}
    assert rotulo["es", "cuál es mi saldo"] == rotulo["en", "what is my balance"] == "balance"
    assert rotulo["pt", "pix recusado"] == "declined_card_payment"
    assert rotulo["pt", "roubaram meu cartão"] == "lost_or_stolen_card"
    assert rotulo["es", "quiero bloquear la tarjeta"] == "freeze"


def test_portugues_mapeia_rotulo_pelo_treino_alinhado_e_ignora_linha_sem_texto(tmp_path):
    lidos = lido(tmp_path, pt_teste_extra=[("pix recusado", "pagamento_recusado")])
    portugues = [(e.texto, e.fluxo) for e in lidos.teste if e.idioma == "pt"]
    assert portugues[-1] == ("pix recusado", "explicar_recusa")
    assert len(portugues) == len(ALINHADO) + 1  # a linha vazia do fim não vira exemplo


def test_espanhol_desalinhado_do_ingles_e_erro(tmp_path):
    tabelas, minds = fontes_de_teste(tmp_path / "origem")
    es_treino = tmp_path / "origem" / "es_treino.csv"
    escrever_csv(es_treino, ["frase", "rotulo", "cambiado"], [("só uma", "x", 0)])
    curta = Tabela("es", "treino", arquivo_de(es_treino, "banking77/es_treino.csv"), "frase",
                   "rotulo")  # fmt: skip
    tabelas = tuple(curta if t.arquivo.nome == curta.arquivo.nome else t for t in tabelas)
    fontes.baixar(tmp_path / "d", corpus.arquivos(tabelas, minds))
    with pytest.raises(CorpusInvalido, match="ES treino"):
        corpus.ler(tmp_path / "d", tabelas, minds)


def test_rotulo_portugues_com_duas_intencoes_e_erro(tmp_path):
    ambiguo = [*ALINHADO[:3], (*ALINHADO[3][:4], "cartão recusado", "saldo"), ALINHADO[4]]
    with pytest.raises(CorpusInvalido, match="mais de uma intenção"):
        lido(tmp_path, linhas=ambiguo)


def test_minds14_entra_so_no_treino_com_o_fluxo_da_intencao(tmp_path):
    lidos = lido(tmp_path)
    minds = [(e.texto, e.fluxo) for e in lidos.treino if e.origem == "minds14"]
    assert minds == [
        ("mi tarjeta no funciona", "explicar_recusa"),
        ("quiero bloquear la tarjeta", "relato_de_fraude"),
        ("ver mis movimientos", "ver_transacoes"),
        ("pagar una factura", "fora_de_escopo"),
    ]
    assert all(e.origem == "banking77" for e in lidos.calibracao + lidos.teste)


def test_minds14_com_classe_que_nao_bate_com_o_audio_e_erro(tmp_path):
    trocado = [("es-ES~FREEZE/b.wav", "quiero bloquear la tarjeta", 6)]
    with pytest.raises(CorpusInvalido, match="não bate"):
        lido(tmp_path, minds=trocado)


def test_calibracao_leva_as_tres_linguas_da_mesma_frase_juntas():
    frases = [f"frase {i}" for i in range(50)]
    treino = [Exemplo(f"{i} {t}", "fora_de_escopo", i) for i in ("en", "es", "pt") for t in frases]
    fica, calibracao = corpus.separar_calibracao(treino, fracao=0.2)
    assert len(calibracao) == 3 * 10 and len(fica) == 3 * 40
    posicoes = {i: {e.texto.split(" ", 1)[1] for e in calibracao if e.idioma == i}
                for i in ("en", "es", "pt")}  # fmt: skip
    assert posicoes["en"] == posicoes["es"] == posicoes["pt"]


# ---- modelo ----

FRASES = {
    "explicar_recusa": ["me rechazaron la tarjeta", "pago rechazado", "cartão recusado",
                        "compra recusada", "tarjeta rechazada otra vez"],
    "explicar_pendencia": ["transferencia pendiente", "pagamento pendente", "compra pendiente",
                           "saque pendente", "sigue pendiente"],
    "explicar_estorno": ["reembolso no aparece", "estorno não caiu", "reembolso no llega",
                         "estorno sumiu", "cadê o estorno"],
    "ver_transacoes": ["ver mis movimientos", "ver extrato", "últimos movimientos",
                       "mostrar extrato", "movimientos recientes"],
    "abrir_disputa": ["no reconozco este cargo", "não reconheço a compra", "cargo no reconocido",
                      "cobrança não reconhecida", "no reconozco la compra"],
    "relato_de_fraude": ["me robaron la tarjeta", "roubaram meu cartão", "robaron mi celular",
                         "roubaram o celular", "clonaron mi tarjeta"],
    "fora_de_escopo": ["quiero ver mi saldo", "aumentar limite", "cambiar el pin",
                       "mudar a senha", "abrir una cuenta"],
}  # fmt: skip
EXEMPLOS = [Exemplo(t, fluxo, "es") for fluxo, textos in FRASES.items() for t in textos]


@pytest.fixture(scope="module")
def pequeno() -> ModeloLeitor:
    return ModeloLeitor.treinado(Corpus(EXEMPLOS, EXEMPLOS, EXEMPLOS), codificar, "v-teste")


def test_le_mensagens_obvias_do_corpus_pequeno(pequeno):
    lidas = pequeno.ler(["pago rechazado hoy", "roubaram meu celular", "no reconozco este cargo"],
                        codificar)  # fmt: skip
    assert [lida.fluxo for lida in lidas] == ["explicar_recusa", "relato_de_fraude",
                                              "abrir_disputa"]  # fmt: skip


def test_confianca_e_a_maior_probabilidade_calibrada(pequeno):
    p = pequeno.probabilidades(codificar(["reembolso pendiente"]))
    assert p.sum() == pytest.approx(1, abs=1e-6)
    (lida,) = pequeno.ler(["reembolso pendiente"], codificar)
    assert lida.confianca == pytest.approx(p.max(), abs=1e-4)
    assert lida.fluxo == pequeno.fluxos[int(p.argmax())]


def test_temperatura_ajustada_na_calibracao_melhora_a_perda():
    # Rótulos da calibração trocados: o modelo acerta o treino com confiança alta e erra a
    # calibração; a temperatura que minimiza a perda achata as probabilidades (T > 1).
    trocados = [Exemplo(e.texto, "fora_de_escopo" if e.fluxo != "fora_de_escopo"
                        else "abrir_disputa", "es") for e in EXEMPLOS]  # fmt: skip
    modelo = ModeloLeitor.treinado(Corpus(EXEMPLOS, trocados, EXEMPLOS), codificar, "v")
    assert modelo.temperatura > 1.5


def test_treino_sem_algum_fluxo_e_erro():
    sem_fraude = [e for e in EXEMPLOS if e.fluxo != "relato_de_fraude"]
    with pytest.raises(ModeloInvalido, match="relato_de_fraude"):
        ModeloLeitor.treinado(Corpus(sem_fraude, sem_fraude, sem_fraude), codificar, "v")


def test_metricas_por_idioma_e_na_faixa_da_cascata(pequeno):
    assert set(pequeno.metricas) == {"acuracia_es", "cobertura_0_8", "acuracia_0_8"}
    assert 0 <= pequeno.metricas["cobertura_0_8"] <= 1


def test_artefato_salvo_e_carregado_le_igual(tmp_path, pequeno):
    pequeno.salvar(tmp_path / "leitor.joblib")
    carregado = ModeloLeitor.carregar(tmp_path / "leitor.joblib")
    textos = ["reembolso no aparece", "quiero un préstamo"]
    assert carregado.ler(textos, codificar) == pequeno.ler(textos, codificar)
    assert (carregado.versao, carregado.temperatura) == (pequeno.versao, pequeno.temperatura)


def test_artefato_ausente_ou_de_outro_formato_e_recusado(tmp_path):
    with pytest.raises(ModeloInvalido, match="ausente"):
        ModeloLeitor.carregar(tmp_path / "nao-existe.joblib")
    import joblib

    joblib.dump({"formato": 99}, tmp_path / "velho.joblib")
    with pytest.raises(ModeloInvalido, match="formato"):
        ModeloLeitor.carregar(tmp_path / "velho.joblib")


def test_versao_muda_com_os_dados_ou_com_os_pesos():
    dados = (Arquivo("a", "file:///a", 1, "1" * 64),)
    outros = (Arquivo("a", "file:///a", 1, "2" * 64),)
    assert versao(dados) == versao(dados)
    assert versao(dados) != versao(outros)
    assert versao(dados) != versao(dados, pesos=outros)


def test_cli_sem_argumentos_certos_mostra_o_uso(capsys):
    assert cli.main(["jeje.leitor"]) == 2
    assert "treinar" in capsys.readouterr().err
