"""Os cartões do cliente da sessão (o painel "Cartões" do app, DEV-032): o tipo, os 4 últimos
dígitos, o status da base e o bloqueio ativo feito pelo canal. Não há parâmetro que escolha o
cliente, e o número inteiro do cartão nunca sai da curada."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from jeje import bloqueio
from jeje.db import EngineDep
from jeje.sessao_api import RESPOSTAS_SESSAO, SessaoDep

router = APIRouter(responses=RESPOSTAS_SESSAO)


class BloqueioDoCartao(BaseModel):
    """O bloqueio ativo: completo (o cliente desfaz pela conversa até o prazo) ou preventivo (um
    atendente confirma ou desfaz)."""

    id: str
    tipo: str
    reversivel_ate: datetime


class CartaoDoCliente(BaseModel):
    product_id: str
    produto: str
    ultimos4: str | None
    status: str
    bloqueio: BloqueioDoCartao | None


@router.get("/minhas/cartoes")
def meus_cartoes(ativa: SessaoDep, engine: EngineDep) -> list[CartaoDoCliente]:
    with engine.connect() as conexao:
        cartoes = bloqueio.cartoes_do_cliente(conexao, ativa.customer_id)
        ativos = {
            c.bloqueio: bloqueio.ativo_do_cliente(conexao, ativa.customer_id, c.bloqueio)
            for c in cartoes
            if c.bloqueio
        }
    return [
        CartaoDoCliente(
            product_id=c.product_id,
            produto=c.produto,
            ultimos4=c.ultimos4,
            status=c.status,
            bloqueio=_do_bloqueio(ativos.get(c.bloqueio)),
        )
        for c in cartoes
    ]


def _do_bloqueio(ativo: bloqueio.Bloqueio | None) -> BloqueioDoCartao | None:
    if ativo is None:
        return None
    return BloqueioDoCartao(id=ativo.id, tipo=ativo.tipo, reversivel_ate=ativo.reversivel_ate)
