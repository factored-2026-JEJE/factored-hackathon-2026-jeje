"""Pré-caso de contestação (DEV-012): proposta → confirmação → gravação idempotente → releitura.

A proposta só nasce quando a política permite (POL-DISP-01) e guarda os fatos daquele momento. A
confirmação, na mesma transação: trava a proposta, devolve o protocolo se ela já foi confirmada,
recusa proposta vencida, **reavalia a política com os fatos atuais** e grava sem duplicar (um
pré-caso por transação do cliente). O protocolo só é devolvido depois de relido do banco. Pré-caso
recebido não é estorno nem resolução: nenhum dinheiro é movido.
"""

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Connection, text

from jeje import consultas, politica


class NaoEncontrada(Exception):
    """Transação ou proposta inexistente para o cliente da sessão (ou de outro cliente)."""


class Conflito(Exception):
    """A proposta não pode mais ser confirmada (vencida ou situação da transação mudou)."""


@dataclass(frozen=True)
class Proposta:
    id: str
    transaction_id: str
    expira_em: datetime


@dataclass(frozen=True)
class PreCaso:
    protocolo: str
    transaction_id: str
    estado: str
    criado_em: datetime


def pre_caso_da_transacao(conexao: Connection, customer_id: str, transaction_id: str):
    linha = conexao.execute(
        text(
            "SELECT protocolo, transaction_id, estado, criado_em FROM app.pre_casos"
            " WHERE customer_id = :cliente AND transaction_id = :transacao"
        ),
        {"cliente": customer_id, "transacao": transaction_id},
    ).first()
    return None if linha is None else PreCaso(**linha._mapping)


def noturno_digital_hoje(
    conexao: Connection, customer_id: str, limites: politica.Limites
) -> Decimal:
    """Quanto o assistente já registrou hoje, em USD, de transações noturnas em canal digital do
    cliente: é a base do limite do dia de POL-HUM-04."""
    return sum(
        (
            f.amount_usd
            for f in consultas.fatos_dos_pre_casos_de_hoje(conexao, customer_id)
            if f.amount_usd is not None and politica.noturna_digital(f, limites)
        ),
        Decimal("0"),
    )


def _do_cliente(conexao: Connection, customer_id: str, limites: politica.Limites) -> dict:
    """O que a política precisa saber do cliente, além da transação: o total noturno digital de
    hoje (POL-HUM-04), o "hoje" dos dados (POL-HUM-05) e os pré-casos recentes (POL-HUM-06)."""
    return {
        "noturno_no_dia_usd": noturno_digital_hoje(conexao, customer_id, limites),
        "hoje": consultas.hoje_dos_dados(conexao),
        "pre_casos_recentes": consultas.pre_casos_recentes(
            conexao, customer_id, limites.reincidencia_dias
        ),
    }


def avaliar(
    conexao: Connection, customer_id: str, transaction_id: str, limites: politica.Limites
) -> tuple[politica.Fatos, politica.Decisao]:
    """Decisão da política para contestar a transação agora, com o pré-caso existente e o total
    noturno digital do dia. Transação inexistente ou de outro cliente: NaoEncontrada."""
    fatos = consultas.fatos_da_transacao(conexao, customer_id, transaction_id)
    if fatos is None:
        raise NaoEncontrada(transaction_id)
    existente = pre_caso_da_transacao(conexao, customer_id, transaction_id)
    decisao = politica.decidir_contestacao(
        fatos,
        limites,
        existente.protocolo if existente else None,
        **_do_cliente(conexao, customer_id, limites),
    )
    return fatos, decisao


def propor(
    conexao: Connection,
    customer_id: str,
    transaction_id: str,
    limites: politica.Limites,
    ttl_minutos: int,
) -> tuple[politica.Decisao, Proposta | None]:
    fatos, decisao = avaliar(conexao, customer_id, transaction_id, limites)
    if decisao.acao != "propor_pre_caso":
        return decisao, None
    proposta_id = secrets.token_urlsafe(16)
    expira_em = conexao.execute(
        text(
            "INSERT INTO app.propostas_pre_caso (id, customer_id, transaction_id, fatos, expira_em)"
            " VALUES (:id, :cliente, :transacao, CAST(:fatos AS jsonb),"
            "         now() + make_interval(mins => :ttl)) RETURNING expira_em"
        ),
        {
            "id": proposta_id,
            "cliente": customer_id,
            "transacao": transaction_id,
            "fatos": _fatos_json(fatos),
            "ttl": ttl_minutos,
        },
    ).scalar_one()
    return decisao, Proposta(id=proposta_id, transaction_id=transaction_id, expira_em=expira_em)


def _fatos_json(fatos: politica.Fatos) -> str:
    return json.dumps(
        {
            "status": fatos.status,
            "response_code": fatos.response_code,
            "amount_usd": None if fatos.amount_usd is None else str(fatos.amount_usd),
        }
    )


def confirmar(
    conexao: Connection, customer_id: str, proposta_id: str, limites: politica.Limites
) -> tuple[PreCaso, bool]:
    """Devolve (pré-caso relido, criado_agora). Idempotente por proposta e por transação."""
    # Uma confirmação por cliente de cada vez: o limite do dia (POL-HUM-04) soma o que já foi
    # registrado, e duas confirmações simultâneas não podem ver o mesmo total.
    conexao.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:cliente))"), {"cliente": customer_id}
    )
    proposta = conexao.execute(
        text(
            "SELECT transaction_id, expira_em > now() AS valida FROM app.propostas_pre_caso"
            " WHERE id = :id AND customer_id = :cliente FOR UPDATE"
        ),
        {"id": proposta_id, "cliente": customer_id},
    ).first()
    if proposta is None:
        raise NaoEncontrada(proposta_id)
    ja_registrado = pre_caso_da_transacao(conexao, customer_id, proposta.transaction_id)
    if ja_registrado is not None:
        return ja_registrado, False
    if not proposta.valida:
        raise Conflito("proposta vencida; peça uma nova avaliação")
    fatos = consultas.fatos_da_transacao(conexao, customer_id, proposta.transaction_id)
    if fatos is None:
        raise Conflito("a transação não está mais disponível")
    decisao = politica.decidir_contestacao(
        fatos,
        limites,
        protocolo_existente=None,
        **_do_cliente(conexao, customer_id, limites),
    )
    if decisao.acao != "propor_pre_caso":
        raise Conflito(f"situação da transação mudou ({decisao.regra})")
    inserido = conexao.execute(
        text(
            "INSERT INTO app.pre_casos (protocolo, customer_id, transaction_id, proposta_id)"
            " VALUES ('PC-' || lpad(nextval('app.protocolo_seq')::text, 8, '0'),"
            "         :cliente, :transacao, :proposta)"
            " ON CONFLICT DO NOTHING"
        ),
        {"cliente": customer_id, "transacao": proposta.transaction_id, "proposta": proposta_id},
    ).rowcount
    registrado = pre_caso_da_transacao(conexao, customer_id, proposta.transaction_id)
    if registrado is None:
        raise RuntimeError("pré-caso não encontrado na releitura; nada foi confirmado")
    return registrado, inserido == 1


def pre_casos_do_cliente(conexao: Connection, customer_id: str) -> list[PreCaso]:
    linhas = conexao.execute(
        text(
            "SELECT protocolo, transaction_id, estado, criado_em FROM app.pre_casos"
            " WHERE customer_id = :cliente ORDER BY criado_em DESC, protocolo DESC"
        ),
        {"cliente": customer_id},
    )
    return [PreCaso(**linha._mapping) for linha in linhas]
