"""Interpretação baseline da mensagem do cliente, por regras (ES/PT), sem modelo (G10).

Só classifica: língua, intenção, resposta a uma pergunta (sim/não, opção de uma lista) e pistas
(valor, data, status citado). Não decide nada — a política decide com fatos verificados — e não
carrega identidade de cliente nem ID de transação: identificador digitado no chat só é sinalizado
(POL-ID-02). É o contrato que um interpretador por modelo (G14) também precisa cumprir.
"""

import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from itertools import product
from pathlib import Path
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
    # A mensagem inteira aceita a oferta do atendente, com o aceite largo do dia a dia ("sí,
    # pásame", "pode passar", "beleza"). Vale só para a oferta: confirmar ação pede `resposta`.
    aceita_oferta: bool = False
    # A resposta recusa a transação proposta, não o pedido ("no, esa no", "não é essa", ACH-145).
    outra: bool = False
    escolha: int | None = None  # posição (1..9) numa lista de opções apresentada antes
    valor: Decimal | None = None
    # O valor veio com moeda, símbolo ou centavos ("45,90", "46 dólares"): o número solto pode ser
    # o dia ou o final do cartão, e não basta para a proposta direta pelo ranking (ACH-143).
    valor_marcado: bool = False
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


@lru_cache(maxsize=4096)
def _regex(padrao: str) -> re.Pattern[str]:
    """Cada expressão é compilada uma vez por processo. Uma mensagem passa por mais termos do que o
    cache do `re` guarda (512), e recompilar tudo custava ~100 ms por mensagem (ACH-107). O limite
    cobre os termos fixos com folga; os nomes de comércio, que variam, giram no fim da fila."""
    return re.compile(padrao)


def _casa(termo: str, limpo: str) -> bool:
    return _regex(_padrao(termo)).search(limpo) is not None


PALAVRAS_ENTRE = 3


@dataclass(frozen=True)
class Perto:
    """Termo composto: um termo de cada grupo, em qualquer ordem, separados por no máximo `entre`
    palavras, nenhuma delas de `fora` (o que mostra que o objeto é outro). Com o termo do segundo
    grupo antes do primeiro, também as `antes` palavras anteriores não podem ser de `fora_antes`: em
    "la compra con mi tarjeta no aparece", o que não aparece é a compra."""

    um: tuple[str, ...]
    outro: tuple[str, ...]
    entre: int = PALAVRAS_ENTRE
    fora: tuple[str, ...] = ()
    antes: int = 0
    fora_antes: tuple[str, ...] = ()
    negavel: bool = False  # negado logo antes ("no me cobraron de más"), não casa
    so_nessa_ordem: bool = False  # só o termo do primeiro grupo e depois o do segundo
    # Nas `depois` palavras depois do par, um termo de `fora_depois` mostra que o objeto está
    # seguro ou é outro: "olvidé mi tarjeta en casa", "la tarjeta no aparece en la app".
    depois: int = 0
    fora_depois: tuple[str, ...] = ()


def _casou(termo: str | Perto, limpo: str) -> str | None:
    """O termo que casou na mensagem (no composto, o primeiro par na ordem dos grupos, unido por
    `+`) ou None. Só se testam os pares com os dois termos na mensagem: testar todos custava uma
    busca por par, centenas no relato de golpe (ACH-142)."""
    if isinstance(termo, str):
        return termo if _casa(termo, limpo) else None
    entre = rf"((?: [a-z0-9]+){{0,{termo.entre}}}) "
    um = [a for a in termo.um if _casa(a, limpo)]
    outro = [b for b in termo.outro if _casa(b, limpo)]
    for a, b in product(um, outro):
        x, y = _padrao(a), _padrao(b)
        padrao = f"{x}{entre}{y}" if termo.so_nessa_ordem else f"{x}{entre}{y}|{y}{entre}{x}"
        for achado in _regex(padrao).finditer(limpo):
            grupos = achado.groups()
            meio = next((g for g in grupos if g), "")
            if any(_casa(f, meio) for f in termo.fora):
                continue
            # O segundo grupo só participa quando o termo do segundo grupo veio antes.
            invertido = len(grupos) == 2 and grupos[1] is not None
            antes = " ".join(limpo[: achado.start()].split()[-termo.antes :] if termo.antes else ())
            if invertido and any(_casa(f, antes) for f in termo.fora_antes):
                continue
            if termo.negavel and _negado(limpo[: achado.start()]):
                continue
            seguinte = " ".join(limpo[achado.end() :].split()[: termo.depois])
            if any(_casa(f, seguinte) for f in termo.fora_depois):
                continue
            return f"{a}+{b}"
    return None


def _negado(antes: str) -> bool:
    """A palavra logo antes do termo, pulando um pronome ("no me cobraron", "não me roubaram"), é
    uma negação."""
    palavras = antes.split()
    if palavras and palavras[-1] in PRONOMES_DA_VITIMA:
        palavras = palavras[:-1]
    return bool(palavras) and palavras[-1] in NEGA_A_VITIMA


# Perda ou extravio só é relato de fraude com cartão, carteira ou celular perto: "perdí la
# conexión" e "no encuentro la compra en mi tarjeta" continuam consulta (ACH-101).
# "Plástico" é o cartão na gíria (ACH-182), mas só com determinante: "congelen mi plástico" é o
# cartão; "la bolsa de plástico" não.
PLASTICO = ("mi plastico", "meu plastico", "el plastico", "o plastico", "su plastico",
            "seu plastico", "mis plasticos", "meus plasticos")  # fmt: skip
PERDA_DE_MEIO = Perto(
    ("perdi*", "extravi*", "no encuentro", "nao encontro", "sumiu", "desapareci*",
     # DEV-079 (ACH-157, PERDA-01): as outras formas de perder ou ter o cartão levado.
     "quitaron", "hurt*", "no hallo", "no puedo encontrar", "ya no tengo", "olvid*",
     "no aparece", "furt*", "levaram", "nao acho", "nao consigo achar", "nao tenho mais",
     "desaparec*", "esqueci*",
     # O cartão antes do verbo, com "se me cayó" ou o tipo do cartão no meio (PERDA-01, EV-199).
     "se me cayo"),
    ("tarjeta*", "cartao", "cartoes", *PLASTICO, "cartera", "carteira", "billetera", "celular",
     "tarjeta de credito", "tarjeta de debito", "cartao de credito", "cartao de debito"),
    # Entre o verbo e o cartão, o objeto é outro: "esqueci a senha do cartão", "la compra no
    # aparece en la tarjeta", "não tenho mais limite no cartão" não são perda.
    fora=("compra*", "cargo*", "cobr*", "pago*", "pagamento*", "transac*", "senha", "clave",
          "contrasena", "pin", "saldo", "limite", "prazo", "plazo", "en", "em", "no", "na",
          # A fatura, o extrato ou a opção do cartão (auditoria do dev, 02/10).
          "fatura", "factura", "extrato", "extracto", "resumen", "opcion", "opcao", "boleto",
          "comprovante", "comprobante"),
    # Com o cartão antes do verbo, o que vem logo antes dele também conta: "la compra con mi
    # tarjeta no aparece" e "el cargo de mi tarjeta no aparece" falam da compra (ACH-190).
    antes=3,
    fora_antes=("compra*", "cargo*", "cobr*", "pago*", "pagamento*", "transac*", "moviment*",
                "debito*", "saldo", "limite"),
    # Logo depois do par: o cartão em casa ou a tela do app não são perda (auditoria do dev,
    # 02/10). Só 3 palavras: mais longe, já é outra oração ("perdi meu cartão e não aparece no
    # aplicativo a opção de bloquear" é perda).
    depois=3,
    fora_depois=("en casa", "em casa", "en mi casa", "na minha casa", "en la app", "en el app",
                 "na app", "no app", "en la aplicacion", "no aplicativo", "na aplicacao",
                 "en la lista", "de la lista", "na lista", "da lista", "en la pantalla", "na tela"),
)  # fmt: skip
# A pessoa ou o cargo de quem atende só é pedido de humano com verbo de pedido perto: "el gerente
# de la tienda dice que…" (ACH-104) e "una persona me cobró de más" (ACH-159) não são pedido.
PEDIDO_DE_PESSOA = Perto(
    ("hablar", "falar", "conversar", "comunic*", "comuniq*", "pasame", "pase", "pasas", "pasa",
     "pasenme", "pasen", "passem",
     "passa", "transfer*", "quiero", "quero", "necesito", "preciso", "contactar", "contatar",
     "contacto", "contato", "conect*", "chama", "chame", "chamar", "coloca", "coloque", "colocar",
     "atienda", "atenda", "dame", "deme", "llamame", "llame", "liga", "ligue", "poe", "ponme"),
    ("agente", "asesor", "atendente", "humano", "operador", "persona", "pessoa", "alguien",
     "alguem", "gerente", "ejecutivo", "supervisor"),
)  # fmt: skip
# A mensagem que é só a pessoa ("Agente", "un humano por favor", "asesor pfv") continua sendo
# pedido, também com o "por favor" abreviado.
POR_FAVOR = r"(?:por favor|porfavor|porfa|pfv|pfvr|pf|pls|plis|plz|please)"
SO_A_PESSOA = re.compile(
    rf"^(?:(?:un|una|um|uma|el|la|o|a|{POR_FAVOR}|ya|ahora|agora|ja) )*"
    r"(?:agente|asesor|atendente|humano|operador|persona|pessoa|gerente|supervisor)"
    rf"(?: (?:{POR_FAVOR}|ya|ahora|agora|ja))*$"
)
# Cobrança repetida é contestação quando o verbo de cobrar (ou de aparecer no extrato) está perto:
# "me cobraron dos veces", "a Streaming Plus me cobrou 2x"; "intenté dos veces y me rechazaron"
# continua consulta.
COBRANCA_REPETIDA = Perto(
    ("cobr*", "carg*", "debit*", "descont*", "sale", "salen", "salio", "aparece*", "aparecio",
     "caiu", "cayo", "vino", "veio"),
    ("dos veces", "2 veces", "duas vezes", "2 vezes", "2x", "doble", "dobro", "duplicad*",
     "repetid*"),
)  # fmt: skip
# Cobrança a mais é contestação: "me cobraron de más", "a loja me cobrou a mais" (ACH-159). Só com
# o verbo de cobrar: "a cobrança mais recente" e "el cobro más reciente" continuam consulta. Negada
# ("no me cobraron de más, solo quería saber el saldo") não é contestação.
COBRANCA_A_MAIS = Perto(
    ("cobraron", "cobro", "cobran", "cobra", "cobrou", "cobraram", "cobram", "cobrado", "cobrada"),
    ("de mas", "demas", "a mais", "de mais", "mas caro", "mais caro"),
    entre=2,
    negavel=True,
)  # fmt: skip
# Pedido de contestação com substantivo perto da transação ("una contestación a esta compra", "abrir
# un reclamo por la compra", "uma reclamação da cobrança"): sobrava só "compra", e a conversa
# respondia como consulta (ACH-120). Sem a transação perto, "hacer una disputa" (segurança da
# conta) e "una reclamación para un análisis" não decidem nada.
PEDIDO_DE_CONTESTACAO = Perto(
    ("contestacion", "contestacao", "reclamo", "reclamacion", "reclamacao", "disputa", "objecion",
     "objecao", "impugnacion", "impugnacao"),
    ("compra", "cobro", "cobranca", "cargo", "transaccion", "transacao"),
)  # fmt: skip
# A transação negada como do cliente ("hay un cobro que no es mío", "essa compra não é minha") é não
# reconhecer (ACH-120 ampliado, EV-147). A janela é maior porque o valor costuma vir no meio ("un
# cobro de 30 dólares que no es mío"); sem a transação perto, "ese error no es mío" não decide nada.
TRANSACAO_NEGADA = Perto(
    ("no es mio", "no es mia", "no son mios", "no son mias", "nao e minha", "nao e meu",
     "nao sao minhas", "nao sao meus"),
    ("compra", "compras", "cobro", "cobros", "cobranca", "cobrancas", "cargo", "cargos",
     "transaccion", "transacao"),
    entre=5,
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
CARTAO = ("tarjeta*", "cartao", "cartoes", *PLASTICO)
# Congelar e travar também pedem bloqueio (ACH-140), nas formas de pedido: "mi tarjeta está
# congelada" e "o cartão travou na maquininha" contam o estado, não pedem nada.
PEDIDO_DE_BLOQUEIO = Perto(
    ("bloquear", "bloquearla", "bloquearlo", "bloquea", "bloquee", "bloqueen", "bloqueela",
     "bloqueala", "bloqueenla", "bloqueia", "bloqueie", "bloqueiem", "como bloqueo",
     "como bloqueio", "el bloqueo", "o bloqueio", "congelar", "congele", "congelen",
     "congelem", "congelarla", "congelala", "travar", "trave", "travem",
     # "Trava" e "congela" também descrevem o cartão ("meu cartão trava na maquininha", "o
     # aplicativo trava quando abro o cartão", "a trava do cartão"): só são pedido seguidos do
     # cartão de quem pede (auditoria do dev, 02/10).
     "trava meu", "trava minha", "trava o", "trava a", "trava esse", "trava este",
     "congela mi", "congela la", "congela el", "congela esta", "congela esa"),
    CARTAO,
)  # fmt: skip
# Reativar, achar o cartão e liberar de novo também pedem desbloqueio (ACH-140); ativar um cartão
# novo, não.
PEDIDO_DE_DESBLOQUEIO = Perto(
    ("desbloquear", "desbloquearla", "desbloquearlo", "desbloquea", "desbloquee", "desbloqueen",
     "desbloqueela", "desbloqueala", "desbloqueenla", "desbloqueia", "desbloqueie",
     "desbloqueiem", "como desbloqueo", "como desbloqueio", "el desbloqueo", "o desbloqueio",
     "reactivar", "reactiva", "reactive", "reactiven", "reativar", "reativa", "reative",
     "reativem"),
    CARTAO,
)  # fmt: skip
# O cartão achado ("ya apareció mi tarjeta", "achei meu cartão"): o cartão logo depois do verbo.
# "Encontré un pago con tarjeta no autorizado" é outra coisa.
CARTAO_ACHADO = Perto(
    ("ya aparecio", "ja apareceu", "achei", "encontrei", "encontre"), CARTAO, entre=1
)
# Dinheiro sendo tirado da conta é relato de fraude (ACH-140); "¿por qué me estás robando con
# las comisiones?" sem o dinheiro ou a conta perto, não. A conta esvaziada ("me vaciaron la
# cuenta", "esvaziaram minha conta") também é (REG-21).
DINHEIRO_TIRADO = Perto(
    ("robando", "roubando", "tirando", "vaciaron", "esvaziaram", "limparam"),
    ("plata", "dinero", "dinheiro", "cuenta", "conta"),
)
# Golpe de engenharia social (ACH-142): alguém se passou pelo banco, por um funcionário ou por um
# parente; o cliente entregou a senha, o código ou os dados; o site ou o link era falso; a conta, o
# número ou o WhatsApp foram tomados; o dinheiro foi para um golpista.
QUEM_ELE_DISSE_SER = (
    "banco", "bancaria", "agencia", "oficina", "funcionario*", "empleado*", "suporte", "soporte",
    "central", "gerente", "primo", "prima", "tio", "tia", "sobrinho", "sobrinha", "sobrino",
    "sobrina", "hermano", "hermana", "irmao", "irma", "cunhado", "cunhada", "cunado", "familiar",
    "filho", "filha", "hijo", "hija", "mae", "madre", "amigo", "amiga",
    "atendente", "operador", "asesor", "parente", "pariente", "agente", "representante", "primos",
    "sobrinos", "sobrinhos", "parentes", "parientes", "ustedes", "voces",
)  # fmt: skip
SE_PASSOU_POR = Perto(
    ("dijo ser", "dijeron ser", "dice ser", "diciendo ser", "decia ser", "se decia", "dizendo ser",
     "dizia ser", "disse ser", "alegando ser", "alegando serem", "se hizo pasar por",
     "se fez passar por", "se passou por", "fingiu ser", "fingindo ser", "fingiendo ser",
     # Golpe contado como história (ACH-171, REG-12 no 1c11b16).
     "se passava por", "se fazia passar por", "fingia ser", "se hacia pasar por",
     "haciendose pasar por",
     # Apresentou-se como outro ("se presentó como empleado del banco", "me aseguró ser mi primo").
     "se presento como", "se presentaron como",
     "afirma ser", "afirmo ser", "afirmando ser", "aseguro ser", "asegurando ser",
     "se fazendo passar por", "fazendo se passar por", "se passando por", "se passava como",
     "disfrazado de", "disfrazada de", "disfarcado de", "disfarcada de", "decia trabajar",
     "dijo trabajar", "dizia trabalhar", "disse trabalhar"),
    QUEM_ELE_DISSE_SER,
    entre=2,
    # Só o verbo e depois o papel: "o atendente falou que era só esperar" é o atendente de
    # verdade (ACH-173, REG-18).
    so_nessa_ordem=True,
)  # fmt: skip
# "Disse que era" é comum fora do golpe ("o vendedor disse que era problema do banco"): só com
# quem ele disse ser logo depois.
DISSE_QUE_ERA = Perto(
    ("dijo que era", "dijo era", "dijeron que era", "diciendo que era", "diciendo que eran",
     "disse que era", "disseram que era", "dizendo que era", "dizendo que e", "acreditei que era",
     "crei que era", "crei yo era", "achei que era", "pense que era", "falando que era",
     "falou que era", "se dizia do", "que se dizia", "alegando que era", "alegando que e",
     "decia era", "decia que era", "hicieron creer que era", "hizo creer que era",
     "fizeram acreditar que era", "fez acreditar que era", "creyendo que era", "achando que era",
     "pensando que era"),
    QUEM_ELE_DISSE_SER,
    entre=1,
    so_nessa_ordem=True,  # como o SE_PASSOU_POR (ACH-173)
)  # fmt: skip
FALSO_ATENDENTE = Perto(
    ("supuesto", "supuesta", "suposto", "suposta", "falso", "falsa"),
    ("vendedor", "corretor", "funcionario", "operador", "empleado", "ligacao", "llamada",
     "central", "atendente", "asesor", "gerente", "agente"),
    entre=1,
)  # fmt: skip
SENHA_ENTREGUE = Perto(
    ("passei", "dei", "deu", "di", "le di", "les di", "pase", "forneci", "fornecendo", "contei",
     "diera", "facilite", "facilitei"),
    ("senha", "codigo", "clave", "contrasena", "datos", "dados", "pin", "token", "credenciales"),
    entre=2,
)  # fmt: skip
# A senha, o código ou os dados do cliente obtidos ou roubados por outra pessoa ("conseguiu minha
# senha", "robaron mi clave", ACH-171): só com o possessivo e sem negação. Pedida não basta: o
# caixa, o app e o caixa eletrônico também pedem ("o caixa pediu a senha", "el cajero me pidió mi
# pin", REG-17); e o meio de uso legítimo desfaz ("o sistema conseguiu recuperar minha senha").
SENHA_OBTIDA = Perto(
    ("conseguiu", "consiguio", "consiguieron", "conseguiram", "roubou", "robo", "roubaram",
     "robaron"),
    ("minha senha", "mi clave", "mi contrasena", "meu codigo", "mi codigo", "meus dados",
     "mis datos", "meu pin", "mi pin", "meu token", "mi token"),
    entre=1,
    fora=("recuperar", "trocar", "mudar", "alterar", "cambiar", "validar", "confirmar",
          "redefinir", "restablecer", "cadastrar", "registrar", "desbloquear"),
    negavel=True,
)  # fmt: skip
SITE_FALSO = Perto(
    ("sitio", "sitios", "site", "sites", "pagina", "paginas", "enlace", "enlaces", "link",
     "links", "web", "correo", "email"),
    ("falso", "falsos", "falsa", "falsas", "malicioso", "maliciosa", "fraudulento",
     "fraudulenta", "sospechoso", "suspeito", "falsificad*"),
)  # fmt: skip
TRANSFERENCIA_NAO_FEITA = Perto(
    ("transferencia", "transferencias", "movimientos", "movimiento", "movimentacoes",
     "movimentacao", "pix"),
    ("que no hice", "que nao fiz", "que no realice", "no autorice", "nao autorizei",
     "sin autorizar", "sem autorizacao", "sem minha autorizacao", "sin mi autorizacion",
     "no le pedi"),
    entre=5,
)  # fmt: skip
# O cliente não sabe quem fez ("não faço ideia de quem poderia ter feito isso").
AUTOR_DESCONHECIDO = Perto(
    ("nao sei quem", "no se quien", "nao faco ideia de quem", "no tengo idea de quien",
     "sem saber quem", "sin saber quien"),
    ("fez", "hizo", "feito", "hecho", "realizo", "realizou"),
)  # fmt: skip
PEDIDO_DE_DINHEIRO = Perto(
    ("pidiendo", "pedindo", "pidio", "pediu"), ("dinero", "dinheiro", "plata"), entre=1
)
# Outra pessoa usou, roubou, sacou ou pediu dinheiro: "alguien utilizó mi tarjeta sin mi permiso",
# "alguien está usando mi número", "uma pessoa fez compras no meu cartão". Até o #57, "alguien" e
# "una persona" soltos levavam essas mensagens ao atendente como pedido de humano; o relato é de
# fraude (regressão do #57 no REG-12). Só o verbo no passado ou em curso: "si alguien usa mi
# tarjeta" é pergunta.
TERCEIRO_USOU = Perto(
    ("alguien", "alguem", "una persona", "uma pessoa", "otra persona", "outra pessoa",
     "un desconocido", "um desconhecido", "un extrano", "um estranho"),
    # Usar e gastar só com o que é do cliente ("usando mi tarjeta", "gastando com o meu
    # plástico"): "uma pessoa está usando o caixa" não é relato. Transferir fica fora: "alguém
    # transferiu dinheiro para mim" é dinheiro recebido.
    ("uso mi", "usaba mi", "usaron mi", "usando mi", "usando mis", "utilizo mi", "utilizando mi",
     "gastando con mi", "gastando en mi", "gastaron", "robo", "hizo pagos", "hizo compras",
     "hizo un pago", "hizo una compra", "hizo un retiro", "compro", "saco", "retiro",
     "se hizo pasar", "accedio", "entro a mi cuenta", "clono",
     "usou meu", "usou minha", "usava meu", "usaram meu", "usaram minha", "usando meu",
     "usando minha", "usando meus", "utilizou meu", "utilizou minha", "gastando com o meu",
     "gastando com meu", "gastando com a minha", "gastando com minha", "gastou", "roubou",
     "fez pagamentos", "fez compras", "fez um pagamento", "fez uma compra", "fez um saque",
     "comprou", "sacou", "tirou", "se passou", "acessou", "entrou na minha conta", "clonou",
     # Contado de outros jeitos ("alguien la utilizó sin autorización", "alguien obtuvo los datos
     # de mi tarjeta", "alguém está usando a minha conta"), sempre com o que é do cliente (o resto
     # do ACH-171, REG-12 no 4c62c69).
     "la utilizo", "la uso", "la usaron", "la utilizaron", "la esta usando", "la esta utilizando",
     "la ha utilizado", "la ha usado", "usado mi", "usado meu", "usado minha", "uso la misma",
     "usando a minha", "usando o meu", "usou a minha", "usou o meu", "usou um cartao meu",
     "usou o mesmo cartao", "sido utilizada por", "sido usada por", "fue utilizada por",
     "fue usada por", "foi usado por", "foi usada por", "foi utilizado por", "foi utilizada por",
     "ha accedido a mi cuenta", "accedieron a mi cuenta", "acessaram minha conta",
     "tenido acceso a mi", "entrando en mi cuenta", "entrando a mi cuenta",
     "entrando na minha conta", "haciendo pagos con mi", "haciendo compras con mi",
     "fazendo compras com meu", "fazendo compras no meu", "fazendo pagamentos com meu",
     "obtuvo los datos", "obtuvo los detalles", "obteve os dados", "obteve os detalhes",
     "consiguio los datos", "conseguiu os dados", "conseguido la informacion",
     "conseguido as informacoes", "conseguiu obter os dados", "conseguiu obter meus dados",
     "abrio una cuenta a mi nombre", "abriu uma conta no meu nome", "abriu uma conta em meu nome",
     "intento realizar una compra", "intento realizar una transaccion",
     "tentou realizar uma compra", "tentou realizar uma operacao", "tentou realizar uma transacao",
     "intento cobrar con mi", "tentou cobrar com meu", "se ha hecho pasar", "pegou meu cartao",
     "pegou meus cartoes", "pegou minha carteira", "forjou o meu", "forjou meu", "rouba o meu",
     "rouba meu"),
)  # fmt: skip
# O cartão que "se robó" ("mi tarjeta se robó anoche", REG-12).
CARTAO_SE_ROUBOU = Perto(
    ("se robo", "se roubou"), ("tarjeta*", "cartao", "cartoes", "cartera", "carteira", "billetera")
)
# Não querer falar com o robô é pedir uma pessoa (ACH-140). "Robô" sem acento é "robo", que em
# espanhol é roubo: o relato de fraude vem antes e só casa "un robo" e "robo de".
SEM_ROBO = Perto(("no quiero", "nao quero"), ("robot", "robo", "bot", "maquina"))
# Os radicais dos verbos acima: sem nenhum deles, os pedidos de bloqueio e desbloqueio não casam.
RADICAIS_DE_BLOQUEIO = (
    "bloque", "congel", "trav", "reactiv", "reativ", "aparec", "achei", "encontr", "liber",
)  # fmt: skip
LIBERAR_DE_NOVO = Perto(
    ("liberar", "libera", "libere", "liberem", "liberen"),
    ("de novo", "novamente", "de nuevo", "otra vez"),
)
# O pedido de volta do cartão bloqueado (ACH-141), em qualquer ponto da mensagem: o verbo de
# desbloqueio com o cartão ou o bloqueio que o cliente fez ("bloqueé mi tarjeta por error, ¿me la
# pueden desbloquear?"); reativar, liberar e usar de novo com o bloqueio ("meu cartão está
# bloqueado, quero liberar"). "Desbloquear mi PIN", "mi PIN está bloqueado" e "o cartão se
# encerrou, como reativo?" não citam o cartão e o bloqueio do cliente: não casam.
NA_MENSAGEM = 60
BLOQUEIO_DO_CLIENTE = ("bloquee", "bloqueei", "acabo de bloquear", "acabei de bloquear")
DESBLOQUEIO_DE_LONGE = Perto(("desbloque*",), CARTAO + BLOQUEIO_DO_CLIENTE, entre=NA_MENSAGEM)
VOLTA_DO_BLOQUEADO = Perto(
    ("reactiv*", "reativ*", "liberar", "libera", "libere", "liberen", "liberem", "liberarla",
     "liberarlo", "liberala", "liberalo", "libero", "de nuevo", "de novo", "nuevamente",
     "novamente", "otra vez", "outra vez"),
    ("bloqueada", "bloqueado", "bloqueo", "bloqueio", *BLOQUEIO_DO_CLIENTE),
    entre=NA_MENSAGEM,
)  # fmt: skip
# Negação do pedido na mesma oração: "no quiero bloquear mi tarjeta", "não bloqueie meu cartão" e
# "no la bloqueen" não pedem; em "no, bloquéenla" a vírgula separa o "no" do pedido.
NEGACAO = (
    r"(?<![a-z0-9])(?:no|nao|nunca)(?: (?:quiero|quero|necesito|preciso|precisa|precisam"
    r"|hace falta|es necesario|e necessario|vayan a|van a|va a|vao|vai|pueden|podem|puede|pode"
    r"|me|te|la|lo|a|o|mi|meu|minha|el|os|as|las|los))* "
)
# O bloqueio que o cliente já fez ("ya bloqueé mi tarjeta", "la bloquee por error") conta o que
# aconteceu e não pede outro (ACH-141). Só o texto com acento separa o passado "bloqueé" do pedido
# "bloquee mi tarjeta"; sem acento, a partícula antes diz que é passado, menos depois de "que" ("que
# me la bloquee" pede).
BLOQUEIO_CONTADO = re.compile(r"\bbloqueé\b|(?<!que )(?<!que me )\b(?:ya|yo|la|lo|me|le) bloquee\b")
NEGACOES = {
    "bloquear": re.compile(NEGACAO + "(?:bloque|congel|trav)"),
    "desbloquear": re.compile(NEGACAO + "(?:desbloque|reactiv|reativ|liber)"),
}

# Ordem importa: vence a primeira intenção que casar (segurança antes de autosserviço).
TERMOS: tuple[tuple[Intencao, tuple[str | Perto, ...]], ...] = (
    ("fraude", ("fraude", "robaron", "robo de", "un robo", "robada", "robado", "roubaram",
                "roubo", "roubado", "roubada", "clonaron", "clonada", "clonado", "clonaram",
                "hackearon", "hackearam", "invadiram", "asalt*", "assalt*", PERDA_DE_MEIO,
                "usaron mi tarjeta", "usaram meu cartao", "alguien uso mi tarjeta",
                "alguem usou meu cartao",
                "no fui yo", "nao fui eu", "no la hice yo", "no lo hice yo",
                # "Esta compra es fraudulenta" (ACH-121). Sem o verbo ("un cargo fraudulento"),
                # a leitura continua a de hoje.
                "es fraudulent*", "e fraudulent*", "son fraudulent*", "sao fraudulent*",
                "fue fraudulent*", "foi fraudulent*", "fraudulentamente", "de manera fraudulenta",
                "de forma fraudulenta",
                # Golpe e dinheiro tirado da conta (ACH-140).
                "golpe", "estafa", "estafaron", "pix que nao fiz", DINHEIRO_TIRADO,
                # Golpe de engenharia social (ACH-142).
                SE_PASSOU_POR, DISSE_QUE_ERA, FALSO_ATENDENTE, SENHA_ENTREGUE, SENHA_OBTIDA,
                SITE_FALSO,
                PEDIDO_DE_DINHEIRO, TRANSFERENCIA_NAO_FEITA, AUTOR_DESCONHECIDO,
                TERCEIRO_USOU, CARTAO_SE_ROUBOU,
                "phishing", "estafador*", "golpista*", "timo", "trapaca", "hackead*", "hackeou",
                "hackeo", "clonou", "usurpacion", "enganado", "enganada", "enganaram",
                "me enganaron", "robados", "robadas", "roubados", "roubadas", "site errado",
                "sitio equivocado", "pagina errada", "pagina equivocada", "link errado")),
    # O desbloqueio vem antes do bloqueio: o pedido de volta vence o bloqueio contado na mesma
    # frase ("ya bloqueé mi tarjeta, ahora quiero desbloquearla", ACH-141); negado, não pede nada.
    ("desbloquear", (PEDIDO_DE_DESBLOQUEIO, CARTAO_ACHADO, LIBERAR_DE_NOVO, DESBLOQUEIO_DE_LONGE,
                     VOLTA_DO_BLOQUEADO)),
    ("bloquear", (PEDIDO_DE_BLOQUEIO,)),
    ("humano", (PEDIDO_DE_PESSOA, "persona real", "pessoa de verdade", SEM_ROBO)),
    # "Tarjeta de crédito" é comum numa contestação: crédito sozinho não é fora de escopo.
    ("fora_de_escopo", ("prestamo", "emprestimo", "linea de credito", "limite de credito",
                        "inversion", "invertir", "investimento", "investir", "contrasena", "senha",
                        "clave", "tasa de interes", "taxa de juros", "abrir cuenta", "abrir conta",
                        "seguro de vida", "cripto*")),
    ("contestar", ("no reconozco", "no la reconozco", "no lo reconozco", "nao reconheco",
                   "nao a reconheco", "nao o reconheco", "desconozco", "desconheco", "contestar",
                   "contesto", "disputar", "impugnar", "cobro indebido", "cobranca indevida",
                   "cargo no reconocido", "no hice", "nao fiz", "no autorice", "nao autorizei",
                   COBRANCA_REPETIDA, COBRANCA_A_MAIS, "revisen", "revisem", "reclamar",
                   PEDIDO_DE_CONTESTACAO, TRANSACAO_NEGADA)),
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
# "Esa no", "não é essa", "la otra": a transação apontada não é a certa (ACH-145).
OUTRA = ("esa no", "essa nao", "no es esa", "nao e essa", "esa no es", "essa nao e", "no era esa",
         "nao era essa", "no esa", "nao essa", "otra", "outra", "la otra", "a outra", "es otra",
         "e outra")  # fmt: skip
CORTESIA = ("por favor", "gracias", "muchas gracias", "obrigado", "obrigada", "muito obrigado",
            "pues", "entonces", "entao", "bueno", "bom", "ya", "ja", "senor", "senhor")  # fmt: skip


def _so_vocabulario(limpo: str, vocabulario: list[tuple[str, str]]) -> list[str] | None:
    """Tipos das frases do vocabulário que compõem a mensagem inteira, na ordem em que aparecem (a
    frase mais longa primeiro); None se sobrar alguma palavra fora dele."""
    vocabulario = sorted(vocabulario, key=lambda par: -len(par[0].split()))
    palavras, achados = limpo.split(), []
    i = 0
    while i < len(palavras):
        for frase, tipo in vocabulario:
            partes = frase.split()
            if palavras[i : i + len(partes)] == partes:
                achados.append(tipo)
                i += len(partes)
                break
        else:
            return None
    return achados


# Aceites do dia a dia que só valem para a oferta do atendente (sem efeito financeiro, ACH-123): a
# confirmação de pré-caso ou de desbloqueio continua pedindo o sim estrito de AFIRMATIVAS.
ACEITES_DA_OFERTA = ("pasame", "comunicame", "adelante", "pode passar", "pode ser", "com certeza",
                     "isso mesmo", "beleza", "uhum", "por favor", "obvio", "afirmativo", "sip",
                     "va", "bueno", "quero", "simm")  # fmt: skip


def _aceita_oferta(limpo: str) -> bool:
    """A mensagem inteira aceita (um sim, estrito ou largo, e cortesia): qualquer outra palavra,
    como uma negação ou uma pergunta, deixa a oferta sem aceite."""
    vocabulario = [(p, "sim") for p in (*AFIRMATIVAS, *ACEITES_DA_OFERTA)]
    vocabulario += [(p, "cortesia") for p in CORTESIA if p not in ACEITES_DA_OFERTA]
    achados = _so_vocabulario(limpo, vocabulario)
    return achados is not None and set(achados) - {"cortesia"} == {"sim"}


def _outra(limpo: str) -> bool:
    """A mensagem inteira recusa a transação apontada, com ou sem o "não" e a cortesia."""
    vocabulario = [(p, "outra") for p in OUTRA] + [(p, "nao") for p in NEGATIVAS]
    vocabulario += [(p, "cortesia") for p in CORTESIA]
    achados = _so_vocabulario(limpo, vocabulario)
    return achados is not None and "outra" in achados


def _resposta(limpo: str) -> Resposta | None:
    """Sim/não só quando a mensagem inteira é isso (cortesia à parte): "sí, pero no esa" ou
    "¿y si me rechazaron?" não confirmam nada."""
    vocabulario = [(p, "sim") for p in AFIRMATIVAS] + [(p, "nao") for p in NEGATIVAS]
    vocabulario += [(p, "cortesia") for p in CORTESIA]
    achados = _so_vocabulario(limpo, vocabulario)
    if achados is None:
        return None  # palavra fora do vocabulário: não é resposta curta
    tipos = set(achados) - {"cortesia"}
    return tipos.pop() if len(tipos) == 1 else None


# Cumprimento e agradecimento só quando a mensagem inteira é isso: "obrigado, e a outra?" continua
# pedido. É vocabulário fechado: o leitor e5 não tem essa classe e lê "okay, obrigado" como fora do
# escopo (0,81) e "perfeito, obrigada pela ajuda" como explicar_recusa (0,34).
AGRADECIMENTOS = ("gracias", "muchas gracias", "mil gracias", "te agradezco", "le agradezco",
                  "agradezco", "obrigado", "obrigada", "muito obrigado", "muito obrigada",
                  "brigado", "brigada", "brigadao", "valeu", "vlw", "obg", "agradeco", "muy amable",
                  "muito gentil", "muito amavel", "que amable", "adios", "chau", "chao", "tchau",
                  "hasta luego", "hasta pronto", "nos vemos", "ate logo", "ate mais", "ate breve",
                  "beleza", "blz", "show", "joia", "pela ajuda", "por la ayuda", "por tu ayuda",
                  "por su ayuda", "por sua ajuda", "pela informacao",
                  "por la informacion")  # fmt: skip
# Palavras de fechamento: encerram como o agradecimento, mas com uma negação antes ("no resolvió",
# "não era isso", ACH-128) dizem o contrário e não são cortesia.
FECHAMENTO = ("era eso", "eso era todo", "eso es todo", "nada mas", "era isso", "e isso",
              "e so isso", "so isso", "listo", "resolvio", "resolveu", "ya esta", "perfecto",
              "perfeito", "genial", "otimo", "excelente", "ok", "okay", "okey", "vale", "entendi",
              "entendido")  # fmt: skip
NEGACOES_DA_CORTESIA = ("no", "nao", "nunca", "todavia no", "ainda nao")
SAUDACOES = ("hola", "oi", "ola", "opa", "buenas", "buen dia", "buenos dias", "buenas tardes",
             "buenas noches", "bom dia", "boa tarde", "boa noite", "que tal", "e ai", "eai", "hey",
             "alo")  # fmt: skip
ENCHIMENTO_DA_CORTESIA = ("por favor", "pues", "entonces", "entao", "bueno", "bom", "ya", "ja",
                          "senor", "senora", "senhor", "senhora", "muy", "muito", "mucho",
                          "tudo bem", "tudo bom", "todo bien", "como estas", "como vai",
                          "como esta", "si", "sim", "y", "e", "amigo", "amiga",
                          "cara")  # fmt: skip


def _cortesia(limpo: str) -> Cortesia | None:
    vocabulario = [(p, "agradecimento") for p in AGRADECIMENTOS]
    vocabulario += [(p, "fechamento") for p in FECHAMENTO]
    vocabulario += [(p, "negacao") for p in NEGACOES_DA_CORTESIA]
    vocabulario += [(p, "saudacao") for p in SAUDACOES]
    vocabulario += [(p, "enchimento") for p in ENCHIMENTO_DA_CORTESIA]
    achados = _so_vocabulario(limpo, vocabulario) or []
    if any(t == "fechamento" and "negacao" in achados[:i] for i, t in enumerate(achados)):
        return None  # "no resolvió", "não era isso": insatisfação, não agradecimento
    if "agradecimento" in achados or "fechamento" in achados:
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
    # Abreviados ("15 de mar", "3 de fev"), só depois do dia: "mar" sozinho é outra coisa.
    "ene": 1, "jan": 1, "feb": 2, "fev": 2, "mar": 3, "abr": 4, "may": 5, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "out": 10, "nov": 11, "dic": 12, "dez": 12,
}  # fmt: skip
DATA_NUMERICA = re.compile(r"(?<![\d.,])(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}|\d{2}))?(?![\d/-])")
DATA_POR_EXTENSO = re.compile(r"(?<!\d)(\d{1,2})\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?(?!\d)")
# Contagem não é valor: "me aparece 2 veces", "salen 2 cobros".
CONTAGEM = re.compile(
    r"(?<![\w.,])[1-9]\s*(?:veces|vezes|cobros?|cobran[çc]as?|cargos?)(?!\w)", re.IGNORECASE
)
# Números que não são dinheiro (ACH-129 e ACH-127): tempo ("hace 3 días", "faz 2 semanas",
# "10:30", "15h", "a las 3", "3 de la tarde"), final do cartão, dia do mês, conta ou telefone,
# número com zero à esquerda e parcelas. Saem antes de procurar o valor, como a contagem.
NAO_E_DINHEIRO = re.compile(
    r"(?<![\w.,])\d+\s*(?:d[ií]as?|semanas?|mes(?:es)?|m[eê]s|horas?|minutos?|a[nñ]os?"
    r"|cuotas?|parcelas?)(?!\w)"
    r"|(?<![\w.,])\d{1,2}(?::\d{2}|\s*h(?:s|rs)?)(?!\w)"
    r"|(?:a\s+las|a\s+la|às)\s+\d{1,2}(?::\d{2})?(?![\d.,])"
    r"|(?<![\w.,])\d{1,2}\s+(?:de\s+la|da|de)\s+(?:tarde|ma[ñn]ana|noche|manh[ãa]|noite|madrugada)"
    r"(?!\w)"
    r"|(?:terminad[ao]|termina|final|finalizad[ao])\s+(?:en\s+|em\s+)?\d{4}(?!\d)"
    r"|d[ií]a\s+\d{1,2}(?![\d.,/-])"
    r"|(?:cuenta|conta|tel[eé]fono|telefone|celular)\s*(?:n[uú]mero|n[ºo°]\.?|#)?\s*\d{3,}"
    # O grupo de milhar depois do espaço ("1 000") não é código com zero à esquerda (ACH-155).
    r"|(?<![\w.,])(?<!\d\s)0\d{2,}",
    re.IGNORECASE,
)
# Marca de dinheiro junto do número: com várias, vale o valor marcado ("45 dólares", "USD 12").
MOEDA = r"(?:us\$|r\$|\$|usd|mxn|cop|ars|brl|eur|d[oó]lar(?:es)?|pesos?|reais|real)"
MARCADO = re.compile(rf"{MOEDA}\s*$|^\s*{MOEDA}(?![a-z])", re.IGNORECASE)
# "30 mil pesos" é 30.000.
MIL = re.compile(r"(?<![\w.,])(\d{1,3})\s+mil(?!\w)", re.IGNORECASE)
# O dia do mês sem o mês ("el día 15", "no dia 1"): o mais recente até a referência.
DIA_DO_MES = re.compile(r"(?<!\w)d[ií]a\s+(\d{1,2})(?![\d.,/-])", re.IGNORECASE)
# Milhar com ponto, espaço ou vírgula seguida de exatamente 3 dígitos ("189.900,55", "6,050.00",
# o formato do México e dos EUA); decimal com vírgula ou ponto e 1 ou 2 dígitos ("13,45", "1,5").
VALOR = re.compile(r"(?<![\w.,-])(\d{1,3}(?:[.,\s]\d{3})+|\d+)(?:[.,](\d{1,2}))?(?![\w-])")
# Código da moeda colado ao número ("USD13,45"): separado antes de procurar o valor (DEV-043).
MOEDA_COLADA = re.compile(r"(?<![a-z])(usd|mxn|cop|ars|brl|eur)(?=\d)", re.IGNORECASE)
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
    """dd/mm[/aaaa], "10 de marzo [de 2025]" ou "15 de mar". Sem ano: a ocorrência mais recente até
    a data de referência (ninguém contesta compra do futuro). Só o dia ("el día 15"): o dia mais
    recente com esse número até a referência."""
    if achado := DATA_NUMERICA.search(texto):
        dia, mes, ano = achado.groups()
        numero_do_mes = int(mes)
    elif achado := _por_extenso(texto):
        dia, mes, ano = achado.groups()
        numero_do_mes = MESES[normalizar(mes)]
    elif achado := DIA_DO_MES.search(texto):
        return _dia_mais_recente(int(achado.group(1)), referencia)
    else:
        return None
    if ano is not None:
        return _data_valida(int(ano) + (2000 if len(ano) == 2 else 0), numero_do_mes, int(dia))
    neste_ano = _data_valida(referencia.year, numero_do_mes, int(dia))
    if neste_ano is not None and neste_ano <= referencia:
        return neste_ano
    return _data_valida(referencia.year - 1, numero_do_mes, int(dia))


def _dia_mais_recente(dia: int, referencia: date) -> date | None:
    """O dia `dia` mais recente até a referência (no mês dela ou num dos anteriores)."""
    ano, mes = referencia.year, referencia.month
    for _ in range(12):
        candidata = _data_valida(ano, mes, dia)
        if candidata is not None and candidata <= referencia:
            return candidata
        ano, mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    return None


def _valor(texto: str) -> tuple[Decimal | None, bool]:
    """O número com cara de dinheiro: fora data, contagem, identificador, tempo, final de cartão,
    dia, conta e parcelas (ACH-129), o marcado com moeda ou, sem marca, o primeiro; milhar com
    ponto, espaço ou vírgula e decimal com vírgula ou ponto ("COP 189.900,55", "6,050.00",
    "45.90", "USD13,45"); "30 mil" vale 30.000. Junto, se ele veio marcado: com moeda, símbolo ou
    centavos (ACH-143)."""
    sem_datas = DATA_NUMERICA.sub(" ", MOEDA_COLADA.sub(r"\1 ", MIL.sub(r"\g<1>000", texto)))
    sem_datas = DATA_POR_EXTENSO.sub(
        lambda m: " " if normalizar(m.group(2)) in MESES else m.group(0), sem_datas
    )
    limpo = NAO_E_DINHEIRO.sub(" ", IDENTIFICADOR.sub(" ", CONTAGEM.sub(" ", sem_datas)))
    achados = list(VALOR.finditer(limpo))
    if not achados:
        return None, False
    marcados = [
        a
        for a in achados
        if MARCADO.search(limpo[max(0, a.start() - 12) : a.start()])
        or MARCADO.search(limpo[a.end() : a.end() + 12])
    ]
    inteiro, fracao = (marcados or achados)[0].groups()
    digitos = re.sub(r"[.,\s]", "", inteiro)
    return Decimal(f"{digitos}.{(fracao or '0').ljust(2, '0')}"), bool(marcados) or bool(fracao)


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


# ---- Erro de digitação nas palavras de intenção (DEV-060) ---------------------------------------
# O corretor do NOV-24 da validação: a palavra desconhecida com 6 letras ou mais que está a uma
# edição (Damerau-Levenshtein) de uma única palavra dos termos de contestar, fraude, bloquear,
# desbloquear ou humano conta como essa palavra. Palavra com 2 ou mais ocorrências no vocabulário
# (o BANKING77 de treino ES/PT, `python -m jeje.palavras`) nunca é trocada, e a que aparece
# nele ao menos uma vez não vira termo de fraude ("probado" não vira "robado").
VOCABULARIO_DO_ARQUIVO = Path(__file__).with_name("palavras_conhecidas.txt")
VOCABULARIO: dict[str, int] = {
    palavra: int(n)
    for palavra, n in (
        linha.split("\t")
        for linha in VOCABULARIO_DO_ARQUIVO.read_text(encoding="utf-8").split("\n")
        if linha
    )
}
INTENCOES_CORRIGIDAS = frozenset({"contestar", "fraude", "bloquear", "desbloquear", "humano"})
MINIMO_PARA_CORRIGIR = 6


def _palavras_do_termo(termo: str | Perto) -> Iterator[str]:
    if isinstance(termo, Perto):
        for parte in (*termo.um, *termo.outro):
            yield from _palavras_do_termo(parte)
    elif not termo.endswith("*"):
        yield from normalizar(termo).split()


def _lexico() -> dict[str, frozenset[str]]:
    """Cada palavra (4 letras ou mais) dos termos das intenções corrigidas, e as intenções dela."""
    intencoes: dict[str, set[str]] = {}
    for intencao, termos in TERMOS:
        if intencao in INTENCOES_CORRIGIDAS:
            for termo in termos:
                for palavra in _palavras_do_termo(termo):
                    if len(palavra) >= 4:
                        intencoes.setdefault(palavra, set()).add(intencao)
    return {palavra: frozenset(i) for palavra, i in intencoes.items()}


LEXICO_DE_INTENCAO = _lexico()


def _uma_edicao(a: str, b: str) -> bool:
    """A uma edição: uma letra trocada, uma a mais ou a menos, ou duas vizinhas invertidas. O termo
    com uma letra a mais no fim é outra palavra, não erro: "golpes" não vira "golpe" (REG-14), nem
    "pessoal" vira "pessoa" (ACH-172)."""
    if a == b or a[:-1] == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        dif = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
        vizinhas = len(dif) == 2 and dif[1] == dif[0] + 1
        return len(dif) == 1 or (vizinhas and a[dif[0]] == b[dif[1]] and a[dif[1]] == b[dif[0]])
    curta, longa = (a, b) if len(a) < len(b) else (b, a)
    i = next((k for k, (x, y) in enumerate(zip(curta, longa, strict=False)) if x != y), len(curta))
    return curta[i:] == longa[i + 1 :]


def corrigir(texto: str) -> tuple[str, tuple[str, ...]]:
    """O texto com as palavras de intenção corrigidas, e as trocas feitas ("robron→robaron")."""
    trocas, pedacos = [], re.split(r"(\w+)", texto)
    for k, pedaco in enumerate(pedacos):
        palavra = normalizar(pedaco) if pedaco.isalpha() else ""
        if (
            len(palavra) < MINIMO_PARA_CORRIGIR
            or palavra in LEXICO_DE_INTENCAO
            or VOCABULARIO.get(palavra, 0) >= 2
        ):
            continue
        candidatas = [termo for termo in LEXICO_DE_INTENCAO if _uma_edicao(palavra, termo)]
        if len(candidatas) != 1:
            continue
        if "fraude" in LEXICO_DE_INTENCAO[candidatas[0]] and palavra in VOCABULARIO:
            continue
        pedacos[k] = candidatas[0]
        trocas.append(f"{palavra}→{candidatas[0]}")
    return "".join(pedacos), tuple(trocas)


def interpretar(texto: str, idioma_anterior: Idioma, referencia: date) -> Interpretacao:
    texto, corrigidas = corrigir(texto)
    limpo = normalizar(texto)
    escolha = _escolha(limpo)
    # "A 1" é escolha, nunca valor: sem lista pendente, não vira busca de uma transação de 1,00.
    valor, valor_marcado = (None, False) if escolha is not None else _valor(texto)
    pistas = {
        "idioma": _idioma(texto, limpo, idioma_anterior),
        "resposta": _resposta(limpo),
        "aceita_oferta": _aceita_oferta(limpo),
        "outra": _outra(limpo),
        "escolha": escolha,
        "valor": valor,
        "valor_marcado": valor_marcado,
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
        if intencao in NEGACOES and not any(r in limpo for r in RADICAIS_DE_BLOQUEIO):
            continue  # sem o verbo, os pares não casam: pular poupa ~20% da leitura (ACH-107)
        if intencao in NEGACOES and any(NEGACOES[intencao].search(o) for o in oracoes):
            continue
        if intencao == "bloquear" and BLOQUEIO_CONTADO.search(texto.casefold()):
            continue
        casados = tuple(sinal for t in termos if (sinal := _casou(t, limpo)))
        if intencao == "humano" and SO_A_PESSOA.match(limpo):
            casados = (*casados, "so_a_pessoa")
        if casados:
            sinais = (*casados, *(f"digitacao:{t}" for t in corrigidas))
            return Interpretacao(intencao=intencao, sinais=sinais, **pistas)
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
    "mercado": ("supermercado", "mercearia"),
    "super": ("supermercado",),
}


# Palavras de nome de comércio que são também palavras comuns (ACH-150, a regra medida pela
# validação no QT-03): sozinhas, não citam o comércio ("por internet", "Buen día", "soy José",
# "cuenta de ahorro", "llamada telefónica", "por mi salud"). O nome inteiro sempre cita.
PALAVRAS_COMUNS_DO_NOME = frozenset({"internet", "buen", "jose", "ahorro", "telefonica", "salud"})


def comercio_citado_e_como(
    texto: str, comercios: Iterable[str]
) -> tuple[str | None, Literal["nome", "palavra"] | None]:
    """Comércio (dentre os das transações do próprio cliente) citado na mensagem, e como: pelo
    nome inteiro, ou por uma palavra distintiva dele ou pelo ramo que o nome diz (RAMO). Mais de um
    citado → nenhum (quem escolhe é o cliente)."""
    limpo = normalizar(texto)
    citados: dict[str, Literal["nome", "palavra"]] = {}
    for nome in comercios:
        nome_limpo = normalizar(nome)
        if _casa(nome_limpo, limpo):
            citados[nome] = "nome"
            continue
        palavras = nome_limpo.split()
        comuns = COMUNS | PALAVRAS_COMUNS_DO_NOME
        distintivas = [p for p in palavras if len(p) >= 4 and p not in comuns]
        ramo = [t for p in palavras for t in RAMO.get(p, ())]
        if any(_casa(p, limpo) for p in (*distintivas, *ramo)):
            citados[nome] = "palavra"
    if len(citados) != 1:
        return None, None
    return next(iter(citados.items()))


def comercio_citado(texto: str, comercios: Iterable[str]) -> str | None:
    return comercio_citado_e_como(texto, comercios)[0]


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


# ---- Prevenção não é relato (ACH-144) -----------------------------------------------------------
# Listas e regra medidas pela validação no NOV-35 (EV-174): a pergunta de prevenção ou a suspeita
# sem perda, sem termo de vítima não negado, não é relato de quem perdeu o cartão ou o dinheiro.
PREVENCAO = (
    "evitar", "no caer", "nao cair", "como me protejo", "como me proteger", "dicas", "consejos",
    "medo de", "miedo de", "prevenir", "proteger", "es golpe", "e golpe", "era golpe",
    "sera golpe", "es una estafa", "e uma fraude", "protegerme", "me proteger", "protegerse",
    "cuidados", "recomendaciones", "recomendacoes", "como identificar", "como reconocer",
    "como reconhecer", "como saber si", "como saber se", "como detectar", "seria golpe",
    "seria una estafa", "era una estafa", "sera una estafa", "es fraude", "e fraude", "era fraude",
    "es un fraude", "e um golpe", "era um golpe", "sera um golpe", "es legitimo", "es legitima",
    "e legitimo", "e legitima", "es real", "e real", "es verdadero", "es verdadera",
    "e verdadeiro", "e verdadeira",
    # A pergunta condicional ("¿qué hago si alguien usó mi tarjeta?"): sem vítima, é pergunta.
    "que hago si", "que debo hacer si", "que hacer si", "o que fazer se", "o que faco se",
    "o que devo fazer se", "como se si", "como sei se",
    # As flexões de "evitar" e "cuidar" ("¿cómo evito caer en una estafa?"), medidas no REG-16.
    "evito", "evita", "evitas", "evite", "evitamos", "evitarlo", "evitarla", "evitalo", "evitala",
    "como no caer", "para no caer", "para nao cair", "como nao cair", "cuidarme", "cuidarse",
    "como me cuido", "me cuidar", "me previno", "como me previno", "prevengo",
    # A hipótese de perda ("en caso de perder la tarjeta, ¿cómo la bloqueo?"), do REG-20.
    "en caso de", "em caso de", "caso eu", "si la pierdo", "si lo pierdo", "si pierdo",
    "se eu perder", "se eu perdesse", "que pasa si", "o que acontece se"
)  # fmt: skip
SUSPEITA_SEM_PERDA = (
    "no di", "no le di", "no les di", "nao dei", "nao passei", "no pase", "no entregue",
    "nao forneci", "no clique", "no hice clic", "no di clic", "nao cliquei", "no abri", "nao abri",
    "no respondi", "nao respondi", "no cai", "nao cai", "no perdi", "nao perdi", "sin perder",
    "sem perder", "no paso nada", "nao aconteceu nada", "por las dudas", "por via das duvidas",
    "solo para confirmar", "so para confirmar", "quiero confirmar", "quero confirmar",
    "queria confirmar",
    # O objeto antes do verbo ("no se la di") e o nada entregue ("não passei nada"), do REG-21.
    "no se la di", "no se lo di", "no se las di", "no se los di", "no la di", "no lo di",
    "nunca se la di", "nunca se lo di", "no se la pase", "no se lo pase", "nao passei nada",
    "nao informei", "nao forneci nada"
)  # fmt: skip
VITIMA = (
    "cai", "me aplicaron", "sofri", "sufri", "me estafaron", "estafaron", "fui vitima",
    "fui victima", "foi vitima", "perdi", "me robaron", "roubaram", "me roubaram", "transferi",
    "transfiri", "hice una transferencia", "fiz um pix", "fiz uma transferencia", "me sacaron",
    "tiraram", "me quitaron", "apareceram", "aparecieron", "me clonaron", "clonaron", "clonaram",
    "hackearon", "hackearam", "invadiram", "invadieron", "le di", "les di", "di mis", "passei",
    "pase mis", "dei meus", "entregue", "forneci", "pague", "paguei", "deposite", "depositei",
    "envie", "mandei", "me cobraron", "cobraram", "descontaron", "debitaron", "sumiu",
    "desaparecio", "desapareceu", "se llevaron", "levaram", "no reconozco", "nao reconheco",
    "que no hice", "que nao fiz", "sin autorizar", "sem autorizacao", "no autorice",
    "nao autorizei", "me enganaron", "me enganaram", "fui enganado", "fui enganada", "usaron",
    "usaram",
    # A conta esvaziada ("no se la di, pero vaciaron mi cuenta"), do REG-21.
    "vaciaron", "esvaziaram", "limparam"
)  # fmt: skip
NEGA_A_VITIMA = (
    "no", "nao", "nunca", "ni", "nem", "jamas", "jamais"
)  # fmt: skip
PRONOMES_DA_VITIMA = (
    "me", "le", "les", "lhe", "te", "se", "o", "a", "la", "lo"
)  # fmt: skip


def _vitima(limpo: str) -> bool:
    """Algum termo de vítima sem negação logo antes (ou antes do pronome que o precede)."""
    for termo in VITIMA:
        for achado in _regex(_padrao(termo)).finditer(limpo):
            if not _negado(limpo[: achado.start()]):
                return True
    return False


def prevencao(texto: str) -> bool:
    """Pergunta de prevenção ou suspeita sem perda, sem vítima: a fraude lida assim vai ao
    atendente sem bloquear o cartão (P3 do NOV-35)."""
    limpo = normalizar(texto)
    sinal = any(_casa(t, limpo) for t in (*PREVENCAO, *SUSPEITA_SEM_PERDA))
    return sinal and not _vitima(limpo)
