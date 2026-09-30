"""Interpretação baseline da mensagem do cliente, por regras (ES/PT), sem modelo (G10).

Só classifica: língua, intenção, resposta a uma pergunta (sim/não, opção de uma lista) e pistas
(valor, data, status citado). Não decide nada — a política decide com fatos verificados — e não
carrega identidade de cliente nem ID de transação: identificador digitado no chat só é sinalizado
(POL-ID-02). É o contrato que um interpretador por modelo (G14) também precisa cumprir.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import product
from typing import Literal

from jeje.mensagens import Idioma, Status

Intencao = Literal[
    "fraude",
    "bloquear",
    "desbloquear",
    "humano",
    "fora_de_escopo",
    "contestar",
    "consultar",
    "desconhecida",
]
Resposta = Literal["sim", "nao"]
Cortesia = Literal["saudacao", "agradecimento"]


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
    caso: bool = False  # pergunta pelo pedido de revisão já registrado (POL-CASO-*)
    ultima: bool = False  # "la última", "a mais recente": das que casarem, a mais recente
    cortesia: Cortesia | None = None  # a mensagem inteira é cumprimento ou agradecimento
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
# Cargo de quem atende só é pedido de humano com verbo de pedido perto: "el gerente de la tienda
# dice que…" é consulta (ACH-104).
PEDIDO_DE_CARGO = Perto(
    ("hablar", "falar", "conversar", "comunic*", "comuniq*", "pasame", "passa", "transfer*",
     "quiero", "quero", "necesito", "preciso", "contactar", "contatar"),
    ("gerente", "ejecutivo", "supervisor"),
)  # fmt: skip
# Cobrança repetida é contestação quando o verbo de cobrar (ou de aparecer no extrato) está perto:
# "me cobraron dos veces", "a Streaming Plus me cobrou 2x"; "intenté dos veces y me rechazaron"
# continua consulta.
COBRANCA_REPETIDA = Perto(
    ("cobr*", "carg*", "debit*", "descont*", "sale", "salen", "salio", "aparece*", "aparecio",
     "caiu", "cayo", "vino", "veio"),
    ("dos veces", "2 veces", "duas vezes", "2 vezes", "2x", "doble", "dobro", "duplicad*",
     "repetid*"),
)  # fmt: skip

# Pergunta pelo pedido de revisão já registrado: o pedido (com possessivo ou palavra de andamento
# perto) ou o protocolo. "¿cómo va mi solicitud?", "status do meu pedido de revisão", "cadê o
# protocolo"; "quiero abrir una disputa" e "quero um pedido de revisão" continuam contestação.
PEDIDO_REGISTRADO = Perto(
    ("mi", "mis", "meu", "meus", "minha", "minhas", "como esta", "como va", "como anda",
     "como vai", "como ficou", "como segue", "estado", "status", "situacion", "situacao",
     "andamento", "novedad*", "novidade*", "noticia*", "respuesta", "resposta", "ver",
     "consultar", "que paso con", "o que houve com", "cade", "donde esta"),
    ("pre caso", "precaso", "pre casos", "precasos", "solicitud*", "pedido de revisao",
     "pedidos de revisao", "reclamo", "reclamos", "reclamacao", "reclamacion", "disputa",
     "contestacao"),
)  # fmt: skip
# O protocolo é do próprio cliente e só existe depois do registro; digitado ("PC-00000003"), só
# indica o assunto: a busca continua sendo pelos pré-casos do cliente da sessão (POL-ID-02).
PROTOCOLO = ("protocolo", "protocolos")
PROTOCOLO_DIGITADO = re.compile(r"(?<![a-z0-9])pc \d+")

# Recusar o atendente não é pedir um: "no quiero un agente, solo dime cuál fue". Só a negação
# aplicada ao atendente ("no quiero esperar, quiero un agente" continua pedido).
RECUSA_DE_HUMANO = re.compile(
    r"(?<![a-z0-9])(?:no quiero|nao quero|no necesito|nao preciso|sin|sem)"
    r"(?: (?:hablar|falar)(?: con| com)?)?(?: (?:un|una|um|uma|el|la|o|a|ningun|nenhum))?"
    r" (?:agente|asesor|atendente|humano|operador|persona|pessoa)(?![a-z0-9])"
)

# Pedido de bloqueio ou desbloqueio de cartão (PRD-007): verbo de pedido (infinitivo, imperativo,
# "¿cómo bloqueo…?", "el bloqueo") perto de cartão. "¿Por qué bloquearon mi tarjeta?" e "meu cartão
# foi bloqueado?" não pedem nada; roubo e perda já são relato de fraude, que também bloqueia.
CARTAO = ("tarjeta*", "cartao", "cartoes")
PEDIDO_DE_BLOQUEIO = Perto(
    ("bloquear", "bloquearla", "bloquearlo", "bloquea", "bloquee", "bloqueen", "bloqueela",
     "bloqueala", "bloqueenla", "bloqueia", "bloqueie", "bloqueiem", "como bloqueo",
     "como bloqueio", "el bloqueo", "o bloqueio"),
    CARTAO,
)  # fmt: skip
PEDIDO_DE_DESBLOQUEIO = Perto(
    ("desbloquear", "desbloquearla", "desbloquearlo", "desbloquea", "desbloquee", "desbloqueen",
     "desbloqueela", "desbloqueala", "desbloqueenla", "desbloqueia", "desbloqueie",
     "desbloqueiem", "como desbloqueo", "como desbloqueio", "el desbloqueo", "o desbloqueio"),
    CARTAO,
)  # fmt: skip
# Negação do pedido na mesma oração: "no quiero bloquear mi tarjeta", "não bloqueie meu cartão" e
# "no la bloqueen" não pedem; em "no, bloquéenla" a vírgula separa o "no" do pedido.
NEGACAO = (
    r"(?<![a-z0-9])(?:no|nao|nunca)(?: (?:quiero|quero|necesito|preciso|precisa|precisam"
    r"|hace falta|es necesario|e necessario|vayan a|van a|va a|vao|vai|pueden|podem|puede|pode"
    r"|me|te|la|lo|a|o|mi|meu|minha|el|os|as|las|los))* "
)
NEGACOES = {
    "bloquear": re.compile(NEGACAO + "bloque"),
    "desbloquear": re.compile(NEGACAO + "desbloque"),
}

# Ordem importa: vence a primeira intenção que casar (segurança antes de autosserviço).
TERMOS: tuple[tuple[Intencao, tuple[str | Perto, ...]], ...] = (
    ("fraude", ("fraude", "robaron", "robo de", "un robo", "robada", "robado", "roubaram",
                "roubo", "roubado", "roubada", "clonaron", "clonada", "clonado", "clonaram",
                "hackearon", "hackearam", "invadiram", "asalt*", "assalt*", PERDA_DE_MEIO,
                "usaron mi tarjeta", "usaram meu cartao", "alguien uso mi tarjeta",
                "alguem usou meu cartao",
                "no fui yo", "nao fui eu")),
    ("bloquear", (PEDIDO_DE_BLOQUEIO,)),
    ("desbloquear", (PEDIDO_DE_DESBLOQUEIO,)),
    ("humano", ("agente", "asesor", "atendente", "humano", "operador", PEDIDO_DE_CARGO,
                "persona real",
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
                   "cargo no reconocido", "no hice", "nao fiz", "no autorice", "nao autorizei",
                   COBRANCA_REPETIDA, "revisen", "revisem", "reclamar")),
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


def _so_vocabulario(limpo: str, vocabulario: list[tuple[str, str]]) -> set[str] | None:
    """Tipos das frases do vocabulário que compõem a mensagem inteira (a frase mais longa primeiro);
    None se sobrar alguma palavra fora dele."""
    vocabulario = sorted(vocabulario, key=lambda par: -len(par[0].split()))
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
            return None
    return achados


def _resposta(limpo: str) -> Resposta | None:
    """Sim/não só quando a mensagem inteira é isso (cortesia à parte): "sí, pero no esa" ou
    "¿y si me rechazaron?" não confirmam nada."""
    vocabulario = [(p, "sim") for p in AFIRMATIVAS] + [(p, "nao") for p in NEGATIVAS]
    vocabulario += [(p, "cortesia") for p in CORTESIA]
    achados = _so_vocabulario(limpo, vocabulario)
    if achados is None:
        return None  # palavra fora do vocabulário: não é resposta curta
    achados.discard("cortesia")
    return achados.pop() if len(achados) == 1 else None


# Cumprimento e agradecimento só quando a mensagem inteira é isso: "obrigado, e a outra?" continua
# pedido. É vocabulário fechado: o leitor e5 não tem essa classe e lê "okay, obrigado" como fora do
# escopo (0,81) e "perfeito, obrigada pela ajuda" como explicar_recusa (0,34).
AGRADECIMENTOS = ("gracias", "muchas gracias", "mil gracias", "te agradezco", "le agradezco",
                  "agradezco", "obrigado", "obrigada", "muito obrigado", "muito obrigada",
                  "brigado", "brigada", "brigadao", "valeu", "vlw", "obg", "agradeco", "muy amable",
                  "muito gentil", "muito amavel", "que amable", "adios", "chau", "chao", "tchau",
                  "hasta luego", "hasta pronto", "nos vemos", "ate logo", "ate mais", "ate breve",
                  "era eso", "eso era todo", "eso es todo", "nada mas", "era isso", "e isso",
                  "e so isso", "so isso", "listo", "resolvio", "resolveu", "ya esta", "perfecto",
                  "perfeito", "genial", "otimo", "excelente", "ok", "okay", "okey", "vale",
                  "entendi", "entendido", "beleza", "blz", "show", "joia", "pela ajuda",
                  "por la ayuda", "por tu ayuda", "por su ayuda", "por sua ajuda",
                  "pela informacao", "por la informacion")  # fmt: skip
SAUDACOES = ("hola", "oi", "ola", "opa", "buenas", "buen dia", "buenos dias", "buenas tardes",
             "buenas noches", "bom dia", "boa tarde", "boa noite", "que tal", "e ai", "eai", "hey",
             "alo")  # fmt: skip
ENCHIMENTO_DA_CORTESIA = ("por favor", "pues", "entonces", "entao", "bueno", "bom", "ya", "ja",
                          "senor", "senora", "senhor", "senhora", "muy", "muito", "mucho",
                          "tudo bem", "tudo bom", "todo bien", "como estas", "como vai",
                          "como esta", "si", "sim", "no", "nao", "y", "e", "amigo", "amiga",
                          "cara")  # fmt: skip


def _cortesia(limpo: str) -> Cortesia | None:
    vocabulario = [(p, "agradecimento") for p in AGRADECIMENTOS]
    vocabulario += [(p, "saudacao") for p in SAUDACOES]
    vocabulario += [(p, "enchimento") for p in ENCHIMENTO_DA_CORTESIA]
    achados = _so_vocabulario(limpo, vocabulario) or set()
    if "agradecimento" in achados:
        return "agradecimento"
    return "saudacao" if "saudacao" in achados else None


ORDINAIS = {
    "primera": 1, "primero": 1, "primeira": 1, "primeiro": 1, "segunda": 2, "segundo": 2,
    "tercera": 3, "tercero": 3, "terceira": 3, "terceiro": 3, "cuarta": 4, "cuarto": 4,
    "quarta": 4, "quarto": 4, "quinta": 5, "quinto": 5,
}  # fmt: skip
ENCHIMENTO_DA_ESCOLHA = frozenset(
    {"la", "el", "a", "o", "opcion", "opcao", "numero", "es", "e", "esa", "essa", "esta", "seria",
     "por", "favor", "gracias", "obrigado", "obrigada", "quiero", "quero", "fue", "foi", "era"}
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
# Contagem não é valor: "me aparece 2 veces", "salen 2 cobros".
CONTAGEM = re.compile(
    r"(?<![\w.,])[1-9]\s*(?:veces|vezes|cobros?|cobran[çc]as?|cargos?)(?!\w)", re.IGNORECASE
)
VALOR = re.compile(r"(?<![\w.,-])(\d{1,3}(?:[.\s]\d{3})+|\d+)(?:[.,](\d{1,2}))?(?![\w-])")
# Identificadores do sistema (prefixos da base e dos protocolos) ou código longo com dígitos.
IDENTIFICADOR = re.compile(
    r"\b(?:trx|cli|prd|suc|pc|at)-[a-z0-9]+\b"
    r"|\b[a-z]{2,4}-(?=[a-z0-9]*\d)[a-z0-9]{3,}\b"
    r"|\b(?=[a-z0-9]*\d)(?=[a-z0-9]*[a-z])[a-z0-9]{10,}\b",
    re.IGNORECASE,
)


# "Minha última compra", "la más reciente": critério do cliente entre as que casarem. "La última
# vez que intenté" e "no último mês" falam de tempo, não da transação.
ULTIMA = re.compile(
    r"(?<![a-z0-9])(?:ultim[ao]|mas reciente|mais recente)"
    r"(?! (?:vez|veces|vezes|mes|meses|dia|dias|semana|semanas|ano|anos|hora|horas))(?![a-z0-9])"
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
    """Primeiro número que não é data, contagem nem parte de identificador; milhar com ponto ou
    espaço e decimal com vírgula ou ponto ("COP 189.900,55", "45.90", "USD 12")."""
    sem_datas = DATA_NUMERICA.sub(" ", texto)
    sem_datas = DATA_POR_EXTENSO.sub(
        lambda m: " " if normalizar(m.group(2)) in MESES else m.group(0), sem_datas
    )
    achado = VALOR.search(IDENTIFICADOR.sub(" ", CONTAGEM.sub(" ", sem_datas)))
    if achado is None:
        return None
    inteiro, fracao = achado.groups()
    digitos = re.sub(r"[.\s]", "", inteiro)
    return Decimal(f"{digitos}.{(fracao or '0').ljust(2, '0')}")


def _caso(limpo: str) -> bool:
    return (
        _casou(PEDIDO_REGISTRADO, limpo) is not None
        or any(_casa(p, limpo) for p in PROTOCOLO)
        or PROTOCOLO_DIGITADO.search(limpo) is not None
    )


def _oracoes(texto: str) -> list[str]:
    """A mensagem normalizada, partida na pontuação: a negação só vale na própria oração."""
    return [normalizar(parte) for parte in re.split(r"[,.;:!?¡¿]", texto)]


def _status(limpo: str) -> str | None:
    citados = {status for status, termos in STATUS_CITADO if any(_casa(t, limpo) for t in termos)}
    return citados.pop() if len(citados) == 1 else None


def interpretar(texto: str, idioma_anterior: Idioma, referencia: date) -> Interpretacao:
    limpo = normalizar(texto)
    escolha = _escolha(limpo)
    pistas = {
        "idioma": _idioma(texto, limpo, idioma_anterior),
        "resposta": _resposta(limpo),
        "escolha": escolha,
        # "A 1" é escolha, nunca valor: sem lista pendente, não vira busca de uma transação de 1,00.
        "valor": None if escolha is not None else _valor(texto),
        "data": _data(texto, referencia),
        "status": _status(limpo),
        "id_digitado": IDENTIFICADOR.search(texto) is not None,
        "caso": _caso(limpo),
        "ultima": ULTIMA.search(limpo) is not None,
        "cortesia": _cortesia(limpo),
    }
    oracoes = _oracoes(texto)
    for intencao, termos in TERMOS:
        if intencao == "humano" and RECUSA_DE_HUMANO.search(limpo):
            continue
        if intencao in NEGACOES and "bloque" not in limpo:
            continue  # sem o verbo, nem testa os termos compostos, que são caros (ACH-107)
        if intencao in NEGACOES and any(NEGACOES[intencao].search(o) for o in oracoes):
            continue
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


# O que o cliente diz do comércio sem dizer o nome ("numa ótica", "los pasajes", "loja de roupa"):
# palavra do nome → como o cliente fala dela, em ES e PT. Os nomes da base já dizem o ramo
# ("Óptica Visión", "Viajes El Cóndor", "Boutique Moda"); o e5 sem treino, medido nas conversas da
# QA, trocava "a compra da viagem" e "la ropa" por Uber, então aqui é vocabulário, não modelo.
RAMO: dict[str, tuple[str, ...]] = {
    "optica": ("otica", "oculos", "lentes", "gafas", "anteojos"),
    "farmacia": ("drogaria", "drogueria", "remedio*", "medicamento*"),
    "ferreteria": ("ferragem", "ferragens", "herramienta*", "ferramenta*"),
    "viajes": ("viagem", "viagens", "viaje", "pasaje*", "passage*", "vuelo*", "voo", "voos"),
    "cine": ("cinema", "pelicula*", "filme*"),
    "cafe": ("cafezinho", "cafeteria"),
    "moda": ("roupa*", "ropa", "vestido*"),
    "boutique": ("roupa*", "ropa", "vestido*"),
    "restaurante": ("almuerzo", "almoco", "jantar"),
    "gasolinera": ("gasolina", "combustivel", "combustible"),
    "clinica": ("medico", "doctor"),
    "conciertos": ("concierto", "show", "shows"),
    "streaming": ("assinatura", "suscripcion"),
    "telefonica": ("telefone", "telefono"),
    "mercado": ("supermercado", "mercearia"),
    "super": ("supermercado",),
}


def comercio_citado(texto: str, comercios: Iterable[str]) -> str | None:
    """Comércio (dentre os das transações do próprio cliente) citado na mensagem: nome inteiro,
    palavra distintiva dele ou o ramo que o nome diz (RAMO). Mais de um citado → nenhum (quem
    escolhe é o cliente)."""
    limpo = normalizar(texto)
    citados = set()
    for nome in comercios:
        nome_limpo = normalizar(nome)
        palavras = nome_limpo.split()
        distintivas = [p for p in palavras if len(p) >= 4 and p not in COMUNS]
        ramo = [t for p in palavras for t in RAMO.get(p, ())]
        if _casa(nome_limpo, limpo) or any(_casa(p, limpo) for p in (*distintivas, *ramo)):
            citados.add(nome)
    return citados.pop() if len(citados) == 1 else None


# Cartão citado pelo final ("la terminada en 9241", "o de final 5678") ou pelo tipo ("la de
# débito"). Só exatamente 4 dígitos: o número inteiro do cartão não é final de nada.
FINAL_DE_CARTAO = re.compile(r"(?<!\d)\d{4}(?!\d)")
TIPO_CITADO = {"Tarjeta Crédito": ("credito",), "Tarjeta Débito": ("debito",)}


def cartao_citado(texto: str, cartoes: Sequence[tuple[str, str | None]]) -> int | None:
    """Posição do cartão citado entre os do próprio cliente (tipo e 4 últimos dígitos de cada um):
    pelo final e pelo tipo, os dois conferidos quando citados. Nada citado, nenhum ou mais de um
    casado → None (quem escolhe é o cliente)."""
    limpo = normalizar(texto)
    finais = set(FINAL_DE_CARTAO.findall(texto))
    tipos = {tipo for tipo, termos in TIPO_CITADO.items() if any(_casa(t, limpo) for t in termos)}
    if not finais and not tipos:
        return None
    casados = [
        i
        for i, (tipo, ultimos4) in enumerate(cartoes)
        if (not finais or ultimos4 in finais) and (not tipos or tipo in tipos)
    ]
    return casados[0] if len(casados) == 1 else None


def cita_cartao(texto: str) -> bool:
    """A mensagem aponta um cartão (final de 4 dígitos ou tipo), case ou não com algum do cliente:
    quem cita um cartão nunca tem outro escolhido no lugar (ACH-111)."""
    limpo = normalizar(texto)
    tipos = [t for termos in TIPO_CITADO.values() for t in termos]
    return FINAL_DE_CARTAO.search(texto) is not None or any(_casa(t, limpo) for t in tipos)
