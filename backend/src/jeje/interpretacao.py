"""Interpretação baseline da mensagem do cliente, por regras (ES/PT), sem modelo (G10).

Só classifica: língua, intenção, resposta a uma pergunta (sim/não, opção de uma lista) e pistas
(valor, data, status citado). Não decide nada — a política decide com fatos verificados — e não
carrega identidade de cliente nem ID de transação: identificador digitado no chat só é sinalizado
(POL-ID-02). É o contrato que um interpretador por modelo (G14) também precisa cumprir.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import product
from typing import Literal

from jeje.mensagens import Idioma, Status

Intencao = Literal["fraude", "humano", "fora_de_escopo", "contestar", "consultar", "desconhecida"]
Resposta = Literal["sim", "nao"]


@dataclass(frozen=True)
class Interpretacao:
    idioma: Idioma
    intencao: Intencao
    resposta: Resposta | None = None  # a mensagem inteira é um sim ou um não
    escolha: int | None = None  # posição (1..9) numa lista de opções apresentada antes
    valor: Decimal | None = None
    data: date | None = None
    status: Status | None = None  # status citado (ex.: "rechazaron" → Declined)
    id_digitado: bool = False  # parece identificador de sistema (POL-ID-02)
    sinais: tuple[str, ...] = ()  # termos que decidiram a intenção (auditoria)


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e sem pontuação: comparações estáveis entre variantes de escrita."""
    decomposto = unicodedata.normalize("NFKD", texto.casefold())
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", sem_acento))


def _padrao(termo: str) -> str:
    """Termo inteiro (ou prefixo, com `*` no fim) como expressão sobre a mensagem normalizada."""
    if termo.endswith("*"):
        return rf"(?<![a-z0-9]){re.escape(termo[:-1])}[a-z0-9]*"
    return rf"(?<![a-z0-9]){re.escape(termo)}(?![a-z0-9])"


def _casa(termo: str, limpo: str) -> bool:
    return re.search(_padrao(termo), limpo) is not None


@dataclass(frozen=True)
class Perto:
    """Termo composto: um termo de cada grupo, em qualquer ordem, separados por no máximo
    `PALAVRAS_ENTRE` palavras."""

    um: tuple[str, ...]
    outro: tuple[str, ...]


PALAVRAS_ENTRE = 3


def _casou(termo: str | Perto, limpo: str) -> str | None:
    """O termo que casou na mensagem (no composto, o par, unido por `+`) ou None."""
    if isinstance(termo, str):
        return termo if _casa(termo, limpo) else None
    entre = rf"(?: [a-z0-9]+){{0,{PALAVRAS_ENTRE}}} "
    for a, b in product(termo.um, termo.outro):
        x, y = _padrao(a), _padrao(b)
        if re.search(f"{x}{entre}{y}|{y}{entre}{x}", limpo):
            return f"{a}+{b}"
    return None


# Perda ou extravio só é relato de fraude com cartão, carteira ou celular perto: "perdí la
# conexión" e "no encuentro la compra en mi tarjeta" continuam consulta (ACH-101).
PERDA_DE_MEIO = Perto(
    ("perdi*", "extravi*", "no encuentro", "nao encontro", "sumiu", "desapareci*"),
    ("tarjeta*", "cartao", "cartoes", "cartera", "carteira", "billetera", "celular"),
)

# Ordem importa: vence a primeira intenção que casar (segurança antes de autosserviço).
TERMOS: tuple[tuple[Intencao, tuple[str | Perto, ...]], ...] = (
    ("fraude", ("fraude", "robaron", "robo de", "un robo", "robada", "robado", "roubaram",
                "roubo", "roubado", "roubada", "clonaron", "clonada", "clonado", "clonaram",
                "hackearon", "hackearam", "invadiram", "asalt*", "assalt*", PERDA_DE_MEIO,
                "usaron mi tarjeta", "usaram meu cartao", "alguien uso mi tarjeta",
                "alguem usou meu cartao",
                "no fui yo", "nao fui eu")),
    ("humano", ("agente", "asesor", "atendente", "humano", "operador", "gerente", "ejecutivo",
                "supervisor", "persona real",
                "pessoa de verdade", "hablar con alguien", "falar com alguem",
                "hablar con una persona", "falar com uma pessoa", "una persona", "uma pessoa",
                "alguien", "alguem")),
    # "Tarjeta de crédito" é comum numa contestação: crédito sozinho não é fora de escopo.
    ("fora_de_escopo", ("prestamo", "emprestimo", "linea de credito", "limite de credito",
                        "inversion", "invertir", "investimento", "investir", "contrasena", "senha",
                        "clave", "tasa de interes", "taxa de juros", "abrir cuenta", "abrir conta",
                        "seguro de vida", "cripto*")),
    ("contestar", ("no reconozco", "no la reconozco", "no lo reconozco", "nao reconheco",
                   "nao a reconheco", "nao o reconheco", "desconozco", "desconheco", "contestar",
                   "contesto", "disputar", "impugnar", "cobro indebido", "cobranca indevida",
                   "cargo no reconocido", "no hice", "nao fiz", "no autorice", "nao autorizei")),
    # Reembolso e devolução sozinhos são pergunta sobre a transação: contestar é não reconhecer.
    ("consultar", ("por que", "porque", "rechaz*", "recusad*", "recusaram", "recusou", "negad*",
                   "negaram", "pendiente*", "pendente*", "revertid*", "estornad*", "estado",
                   "status", "situacion", "situacao", "que paso", "o que aconteceu", "transac*",
                   "compra", "pago", "pagamento", "cobro", "cobranca", "cargo", "consultar",
                   "aprobad*", "aprovad*", "reembolso", "devolucion", "devolucao")),
)  # fmt: skip

STATUS_CITADO: tuple[tuple[Status, tuple[str, ...]], ...] = (
    ("Declined", ("rechaz*", "recusad*", "recusaram", "recusou", "negad*", "negaram", "declin*")),
    ("Pending", ("pendiente*", "pendente*")),
    ("Reversed", ("revertid*", "revers*", "estornad*")),
    ("Approved", ("aprobad*", "aprovad*")),
)

# Palavras sem ambiguidade entre as duas línguas; empate mantém a língua anterior.
MARCAS: dict[Idioma, tuple[str, ...]] = {
    "pt": ("nao", "voce", "transacao", "transacoes", "reconheco", "obrigado", "obrigada", "minha",
           "meu", "cartao", "atendente", "ola", "quero", "pagamento", "cobranca", "estorno",
           "estornada", "falar", "pessoa", "recusada", "recusaram", "recusou", "foi", "isso",
           "sim", "conta", "fiz", "ajuda", "essa", "esse", "aconteceu", "cade", "com", "um",
           "uma", "estou", "tenho", "voces"),
    "es": ("usted", "transaccion", "transacciones", "reconozco", "gracias", "quiero", "mi",
           "tarjeta", "hola", "cobro", "rechazaron", "rechazada", "hablar", "persona", "fue",
           "hice", "cuenta", "si", "eso", "ayuda", "esa", "ese", "paso", "donde", "con", "un",
           "una", "estoy", "tengo", "ustedes"),
}  # fmt: skip
CARACTERES: dict[Idioma, str] = {"pt": "ãõç", "es": "ñ¿¡"}


def _idioma(texto: str, limpo: str, anterior: Idioma) -> Idioma:
    bruto = texto.casefold()
    pontos = {
        idioma: sum(_casa(m, limpo) for m in MARCAS[idioma])
        + sum(c in bruto for c in CARACTERES[idioma])
        for idioma in MARCAS
    }
    if pontos["pt"] == pontos["es"]:
        return anterior
    return "pt" if pontos["pt"] > pontos["es"] else "es"


# ---- Resposta curta (sim/não) e escolha numa lista -----------------------------------------------

AFIRMATIVAS = ("si", "sim", "claro", "claro que si", "claro que sim", "si quiero", "sim quero",
               "confirmo", "confirmar", "confirma", "ok", "okay", "dale", "isso", "vale",
               "perfecto", "perfeito", "de acuerdo", "pode registrar", "puede registrar",
               "registra", "registre", "correcto", "correto", "exacto", "exato", "certo",
               "esta bien", "ta bom", "pode", "puede")  # fmt: skip
NEGATIVAS = ("no", "nao", "no quiero", "nao quero", "cancelar", "cancela", "cancele", "mejor no",
             "melhor nao", "deja", "dejalo", "deixa", "deixa pra la", "nunca",
             "negativo")  # fmt: skip
CORTESIA = ("por favor", "gracias", "muchas gracias", "obrigado", "obrigada", "muito obrigado",
            "pues", "entonces", "entao", "bueno", "bom", "ya", "ja", "senor", "senhor")  # fmt: skip


def _resposta(limpo: str) -> Resposta | None:
    """Sim/não só quando a mensagem inteira é isso (cortesia à parte): "sí, pero no esa" ou
    "¿y si me rechazaron?" não confirmam nada."""
    vocabulario = [(p, "sim") for p in AFIRMATIVAS] + [(p, "nao") for p in NEGATIVAS]
    vocabulario += [(p, "cortesia") for p in CORTESIA]
    vocabulario.sort(key=lambda par: -len(par[0].split()))  # frase mais longa primeiro
    palavras, achados = limpo.split(), set()
    i = 0
    while i < len(palavras):
        for frase, tipo in vocabulario:
            partes = frase.split()
            if palavras[i : i + len(partes)] == partes:
                achados.add(tipo)
                i += len(partes)
                break
        else:
            return None  # palavra fora do vocabulário: não é resposta curta
    achados.discard("cortesia")
    return achados.pop() if len(achados) == 1 else None


ORDINAIS = {
    "primera": 1, "primero": 1, "primeira": 1, "primeiro": 1, "segunda": 2, "segundo": 2,
    "tercera": 3, "tercero": 3, "terceira": 3, "terceiro": 3, "cuarta": 4, "cuarto": 4,
    "quarta": 4, "quarto": 4, "quinta": 5, "quinto": 5,
}  # fmt: skip
ENCHIMENTO_DA_ESCOLHA = frozenset(
    {"la", "el", "a", "o", "opcion", "opcao", "numero", "es", "e", "esa", "essa", "esta", "seria",
     "por", "favor", "gracias", "obrigado", "obrigada"}
)  # fmt: skip


def _escolha(limpo: str) -> int | None:
    """Posição numa lista só em resposta curta ("2", "la segunda", "opção 3"): "es la primera vez
    que me pasa" não escolhe nada."""
    resto = [p for p in limpo.split() if p not in ENCHIMENTO_DA_ESCOLHA]
    if len(resto) != 1:
        return None
    if re.fullmatch(r"[1-9]", resto[0]):
        return int(resto[0])
    return ORDINAIS.get(resto[0])


# ---- Pistas: valor, data, status, identificador -------------------------------------------------

MESES = {
    "enero": 1, "janeiro": 1, "febrero": 2, "fevereiro": 2, "marzo": 3, "marco": 3, "abril": 4,
    "mayo": 5, "maio": 5, "junio": 6, "junho": 6, "julio": 7, "julho": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "setembro": 9, "octubre": 10, "outubro": 10,
    "noviembre": 11, "novembro": 11, "diciembre": 12, "dezembro": 12,
}  # fmt: skip
DATA_NUMERICA = re.compile(r"(?<![\d.,])(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}|\d{2}))?(?![\d/-])")
DATA_POR_EXTENSO = re.compile(r"(?<!\d)(\d{1,2})\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?(?!\d)")
VALOR = re.compile(r"(?<![\w.,-])(\d{1,3}(?:[.\s]\d{3})+|\d+)(?:[.,](\d{1,2}))?(?![\w-])")
# Identificadores do sistema (prefixos da base e dos protocolos) ou código longo com dígitos.
IDENTIFICADOR = re.compile(
    r"\b(?:trx|cli|prd|suc|pc|at)-[a-z0-9]+\b"
    r"|\b[a-z]{2,4}-(?=[a-z0-9]*\d)[a-z0-9]{3,}\b"
    r"|\b(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{10,}\b",
    re.IGNORECASE,
)


def _data_valida(ano: int, mes: int, dia: int) -> date | None:
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _por_extenso(texto: str) -> re.Match | None:
    return next(
        (m for m in DATA_POR_EXTENSO.finditer(texto) if normalizar(m.group(2)) in MESES), None
    )


def _data(texto: str, referencia: date) -> date | None:
    """dd/mm[/aaaa] ou "10 de marzo [de 2025]". Sem ano: a ocorrência mais recente até a data de
    referência (ninguém contesta compra do futuro)."""
    if achado := DATA_NUMERICA.search(texto):
        dia, mes, ano = achado.groups()
        numero_do_mes = int(mes)
    elif achado := _por_extenso(texto):
        dia, mes, ano = achado.groups()
        numero_do_mes = MESES[normalizar(mes)]
    else:
        return None
    if ano is not None:
        return _data_valida(int(ano) + (2000 if len(ano) == 2 else 0), numero_do_mes, int(dia))
    neste_ano = _data_valida(referencia.year, numero_do_mes, int(dia))
    if neste_ano is not None and neste_ano <= referencia:
        return neste_ano
    return _data_valida(referencia.year - 1, numero_do_mes, int(dia))


def _valor(texto: str) -> Decimal | None:
    """Primeiro número que não é data nem parte de identificador; milhar com ponto ou espaço e
    decimal com vírgula ou ponto ("COP 189.900,55", "45.90", "USD 12")."""
    sem_datas = DATA_NUMERICA.sub(" ", texto)
    sem_datas = DATA_POR_EXTENSO.sub(
        lambda m: " " if normalizar(m.group(2)) in MESES else m.group(0), sem_datas
    )
    achado = VALOR.search(IDENTIFICADOR.sub(" ", sem_datas))
    if achado is None:
        return None
    inteiro, fracao = achado.groups()
    digitos = re.sub(r"[.\s]", "", inteiro)
    return Decimal(f"{digitos}.{(fracao or '0').ljust(2, '0')}")


def _status(limpo: str) -> str | None:
    citados = {status for status, termos in STATUS_CITADO if any(_casa(t, limpo) for t in termos)}
    return citados.pop() if len(citados) == 1 else None


def interpretar(texto: str, idioma_anterior: Idioma, referencia: date) -> Interpretacao:
    limpo = normalizar(texto)
    pistas = {
        "idioma": _idioma(texto, limpo, idioma_anterior),
        "resposta": _resposta(limpo),
        "escolha": _escolha(limpo),
        "valor": _valor(texto),
        "data": _data(texto, referencia),
        "status": _status(limpo),
        "id_digitado": IDENTIFICADOR.search(texto) is not None,
    }
    for intencao, termos in TERMOS:
        casados = tuple(sinal for t in termos if (sinal := _casou(t, limpo)))
        if casados:
            return Interpretacao(intencao=intencao, sinais=casados, **pistas)
    return Interpretacao(intencao="desconhecida", **pistas)


# Palavras de nomes de comércio que também são palavras comuns ("estoy seguro", "en general").
COMUNS = frozenset(
    {"seguro", "general", "central", "centro", "nacional", "servicio", "servicios", "publicos",
     "empresa", "comercial", "express", "premium", "plus", "super", "music", "moda", "tienda",
     "mercado", "restaurante"}
)  # fmt: skip


def comercio_citado(texto: str, comercios: Iterable[str]) -> str | None:
    """Comércio (dentre os das transações do próprio cliente) citado na mensagem: nome inteiro ou
    palavra distintiva dele. Mais de um citado → nenhum (quem escolhe é o cliente)."""
    limpo = normalizar(texto)
    citados = set()
    for nome in comercios:
        nome_limpo = normalizar(nome)
        distintivas = [p for p in nome_limpo.split() if len(p) >= 4 and p not in COMUNS]
        if _casa(nome_limpo, limpo) or any(_casa(p, limpo) for p in distintivas):
            citados.add(nome)
    return citados.pop() if len(citados) == 1 else None
