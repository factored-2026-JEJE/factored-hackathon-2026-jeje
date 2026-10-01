"""Encaminhamento estruturado para humano (DEV-016).

O atendente recebe o motivo (regra), a língua, o pedido do cliente (as falas do pedido em curso
que trazem campos, em até 280 caracteres: minimização), os fatos verificados da transação, o que o
sistema tentou e o que ficou pendente — não a conversa inteira nem dados de outros clientes. A
transação só entra se veio de consulta filtrada pelo dono.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field

from sqlalchemy import Connection, text

from jeje.mensagens import Idioma, TransacaoVerificada

LIMITE_PEDIDO = 280


@dataclass(frozen=True)
class Acao:
    acao: str
    resultado: str


@dataclass(frozen=True)
class Encaminhamento:
    customer_id: str
    regra: str
    idioma: Idioma
    pedido: str
    transacao: TransacaoVerificada | None = None
    acoes: tuple[Acao, ...] = ()
    pendencias: tuple[str, ...] = field(default=())


def _transacao_json(t: TransacaoVerificada | None) -> str | None:
    if t is None:
        return None
    return json.dumps(
        {
            "transaction_id": t.transaction_id,
            "data": t.transaction_date.isoformat(),
            "valor": str(t.amount),
            "moeda": t.currency,
            "comercio": t.merchant_name,
            "status": t.transaction_status,
        }
    )


def texto_por_campos(
    falas: Sequence[str],
    campos_de: Callable[[str], frozenset[str]],
    limite: int = LIMITE_PEDIDO,
) -> str:
    """O texto do pedido para o atendente (DEV-036, NOV-11): das falas do cliente no pedido, entra
    primeiro a que cabe e acrescenta mais campos novos (no empate, a mais curta), até nenhuma
    acrescentar; as escolhidas vão na ordem em que foram ditas. Sem campo em nenhuma, vai a
    primeira, como antes. Só falas do próprio cliente: nada de fora da conversa."""
    falas = [" ".join(f.split()) for f in falas]
    campos = [campos_de(f) for f in falas]
    escolhidas: list[int] = []
    cobertos: set[str] = set()
    usado = -1  # cada fala escolhida ocupa o tamanho dela e um espaço antes
    while True:
        candidatas = [
            i
            for i, fala in enumerate(falas)
            if i not in escolhidas and usado + 1 + len(fala) <= limite and campos[i] - cobertos
        ]
        if not candidatas:
            break
        melhor = max(candidatas, key=lambda i: (len(campos[i] - cobertos), -len(falas[i])))
        escolhidas.append(melhor)
        cobertos |= campos[melhor]
        usado += 1 + len(falas[melhor])
    if not escolhidas:
        return falas[0]
    return " ".join(falas[i] for i in sorted(escolhidas))


def registrar(conexao: Connection, e: Encaminhamento) -> str:
    """Grava o encaminhamento aberto e devolve o identificador lido de volta (AT-########)."""
    pedido = e.pedido if len(e.pedido) <= LIMITE_PEDIDO else e.pedido[: LIMITE_PEDIDO - 1] + "…"
    return conexao.execute(
        text(
            "INSERT INTO app.handoffs (id, customer_id, regra, idioma, pedido, transacao, acoes,"
            " pendencias) VALUES ('AT-' || lpad(nextval('app.handoff_seq')::text, 8, '0'),"
            " :cliente, :regra, :idioma, :pedido, CAST(:transacao AS jsonb),"
            " CAST(:acoes AS jsonb), CAST(:pendencias AS jsonb)) RETURNING id"
        ),
        {
            "cliente": e.customer_id,
            "regra": e.regra,
            "idioma": e.idioma,
            "pedido": pedido,
            "transacao": _transacao_json(e.transacao),
            "acoes": json.dumps([asdict(a) for a in e.acoes]),
            "pendencias": json.dumps(list(e.pendencias)),
        },
    ).scalar_one()


def anotar(conexao: Connection, handoff_id: str, acoes: Sequence[Acao]) -> None:
    """Acrescenta ao encaminhamento o que a conversa fez depois de encaminhar (o bloqueio do
    cartão escolhido no relato de fraude, PRD-009). Sem o encaminhamento, nada é anotado e o turno
    é desfeito por quem chama."""
    anotado = conexao.execute(
        text("UPDATE app.handoffs SET acoes = acoes || CAST(:acoes AS jsonb) WHERE id = :id"),
        {"id": handoff_id, "acoes": json.dumps([asdict(a) for a in acoes])},
    ).rowcount
    if anotado != 1:
        raise RuntimeError("encaminhamento não encontrado; nada foi anotado")


class NaoEncontrado(Exception):
    """Encaminhamento inexistente."""


class JaAssumido(Exception):
    """Outro atendente já assumiu este encaminhamento."""


COLUNAS = "id, customer_id, regra, idioma, pedido, transacao, acoes, pendencias, estado, criado_em"


def assumir(conexao: Connection, handoff_id: str) -> dict:
    """Um atendente assume o encaminhamento aberto: sai da fila; ninguém assume duas vezes."""
    linha = (
        conexao.execute(
            text(
                "UPDATE app.handoffs SET estado = 'em_atendimento'"
                f" WHERE id = :id AND estado = 'aberto' RETURNING {COLUNAS}"
            ),
            {"id": handoff_id},
        )
        .mappings()
        .first()
    )
    if linha is not None:
        return dict(linha)
    existe = conexao.execute(
        text("SELECT 1 FROM app.handoffs WHERE id = :id"), {"id": handoff_id}
    ).first()
    raise JaAssumido(handoff_id) if existe else NaoEncontrado(handoff_id)


def fila(conexao: Connection, limite: int) -> list[dict]:
    """Encaminhamentos abertos, mais antigos primeiro (ordem de atendimento)."""
    linhas = conexao.execute(
        text(
            f"SELECT {COLUNAS} FROM app.handoffs WHERE estado = 'aberto'"
            " ORDER BY criado_em, id LIMIT :limite"
        ),
        {"limite": limite},
    ).mappings()
    return [dict(linha) for linha in linhas]
