"""Restrições da camada curada garantidas pelo próprio PostgreSQL (defesa em profundidade)."""

import pytest
from conftest import conexao
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

CLIENTE = "insert into curated.customers (customer_id, _arquivo, _linha) values (:id, 'f', 1)"
PRODUTO = (
    "insert into curated.products (product_id, customer_id, product_type, currency, "
    "product_status, _arquivo, _linha) "
    "values (:id, :dono, 'Cuenta Ahorro', 'USD', 'Active', 'f', 1)"
)
TRANSACAO = (
    "insert into curated.transactions (transaction_id, transaction_date, customer_id, product_id, "
    "amount, currency, transaction_status, _arquivo, _linha) values "
    "(:id, '2025-03-10 10:00', :cliente, :produto, 10, 'USD', 'Approved', 'f', 1)"
)


@pytest.fixture
def dois_clientes(banco_migrado):
    with conexao(banco_migrado) as con:
        for cliente in ("CLI-A", "CLI-B"):
            con.execute(text(CLIENTE), {"id": cliente})
        con.execute(text(PRODUTO), {"id": "PRD-A", "dono": "CLI-A"})
    return banco_migrado


def test_transacao_com_produto_do_proprio_cliente_e_aceita(dois_clientes):
    with conexao(dois_clientes) as con:
        con.execute(text(TRANSACAO), {"id": "TRX-1", "cliente": "CLI-A", "produto": "PRD-A"})


def test_banco_recusa_transacao_com_produto_de_outro_cliente(dois_clientes):
    with (
        pytest.raises(IntegrityError, match="fk_transactions_product_id_dono"),
        conexao(dois_clientes) as con,
    ):
        con.execute(text(TRANSACAO), {"id": "TRX-2", "cliente": "CLI-B", "produto": "PRD-A"})


def test_banco_recusa_reclamacao_ligada_a_produto_de_outro_cliente(dois_clientes):
    reclamacao = (
        "insert into curated.complaints (complaint_id, creation_date, customer_id, case_type, "
        "status, affected_product_id, _arquivo, _linha) values "
        "('CMP-1', '2025-03-10 10:00', 'CLI-B', 'Claim', 'Open', :produto, 'f', 1)"
    )
    with conexao(dois_clientes) as con:
        con.execute(text(reclamacao), {"produto": None})
    with (
        pytest.raises(IntegrityError, match="fk_complaints_affected_product_id_dono"),
        conexao(dois_clientes) as con,
    ):
        con.execute(text(reclamacao.replace("CMP-1", "CMP-2")), {"produto": "PRD-A"})
