"""Contratos da camada curada: fonte única de tipos, obrigatoriedade, domínios e referências.

Política por regra (códigos estáveis, usados na quarentena e no relatório):

- `Q-TIPO:<col>`     valor não conversível para o tipo do contrato → quarentena;
- `Q-OBRIG:<col>`    campo obrigatório vazio → quarentena;
- `Q-DOMINIO:<col>`  valor fora do domínio declarado → quarentena;
- `Q-REF:<col>`      referência essencial inexistente → quarentena;
- `Q-PROP:<col>`     referência essencial a registro de outro cliente → quarentena;
- `A-REF:<col>`      referência acessória inexistente → campo anulado e contabilizado;
- `A-PROP:<col>`     referência acessória a registro de outro cliente → anulado (ACH-016, R08);
- `Q-PK-CONFLITO`    mesma chave com conteúdos diferentes sem data que os ordene → quarentena;
- `R-REVISAO-SUBSTITUIDA` mesma chave republicada num `process_date` posterior: a versão antiga
  sai da curada e fica auditável na quarentena (revisão / chegada tardia, DEV-004).

Domínios são os valores observados na entrega real (inventário de 28/09/2026); valor novo
precisa de decisão explícita, não entra em silêncio. Referências acessórias com quebra massiva
conhecida (ACH-017) não derrubam o registro inteiro.
"""

from dataclasses import dataclass, field

from jeje.dados.raw import COLUNAS

TIPOS = (
    "text", "integer", "numeric(18,2)", "double precision", "date", "timestamp", "time", "boolean",
)  # fmt: skip


@dataclass(frozen=True)
class Referencia:
    coluna: str
    tabela: str  # tabela curada referenciada (pela chave dela)
    essencial: bool  # quebrada: True → quarentena; False → anulada e contabilizada
    mesmo_cliente: bool = False  # o registro referenciado precisa ser do mesmo customer_id


@dataclass(frozen=True)
class Contrato:
    tabela: str
    chave: tuple[str, ...]
    tipos: dict[str, str] = field(default_factory=dict)  # colunas não listadas: text
    obrigatorias: tuple[str, ...] = ()
    dominios: dict[str, tuple[str, ...]] = field(default_factory=dict)
    referencias: tuple[Referencia, ...] = ()

    def tipo(self, coluna: str) -> str:
        return self.tipos.get(coluna, "text")

    def obrigatoria(self, coluna: str) -> bool:
        return coluna in self.chave or coluna in self.obrigatorias


MOEDAS = ("ARS", "COP", "USD")

# Ordem de dependência: cada tabela só referencia tabelas anteriores.
CONTRATOS: tuple[Contrato, ...] = (
    Contrato(
        tabela="branches",
        chave=("branch_id",),
        tipos={
            "opening_time": "time", "closing_time": "time", "has_atms": "boolean",
            "atm_count": "integer", "has_teller_windows": "boolean",
            "teller_window_count": "integer", "latitude": "double precision",
            "longitude": "double precision", "branch_opening_date": "date",
        },
    ),
    Contrato(
        tabela="daily_exchange_rates",
        chave=("date", "source_currency", "target_currency"),
        tipos={
            "date": "date", "exchange_rate": "double precision",
            "buy_rate": "double precision", "sell_rate": "double precision",
        },
        obrigatorias=("exchange_rate",),
    ),
    Contrato(
        tabela="customers",
        chave=("customer_id",),
        tipos={
            "date_of_birth": "date", "credit_score": "double precision",
            "estimated_monthly_income": "numeric(18,2)", "registration_date": "timestamp",
            "last_updated": "timestamp", "accepts_marketing": "boolean",
        },
        dominios={
            "customer_status": ("Active", "Closed", "Inactive", "Suspended"),
            "document_type": ("CC", "CE", "DNI", "Pasaporte"),
        },
        referencias=(Referencia("registration_branch_id", "branches", essencial=False),),
    ),
    Contrato(
        tabela="products",
        chave=("product_id",),
        tipos={
            "current_balance": "numeric(18,2)", "credit_limit": "numeric(18,2)",
            "interest_rate": "double precision", "opening_date": "date",
            "expiration_date": "date", "has_linked_app": "boolean",
            "days_past_due": "double precision", "last_transaction_date": "timestamp",
            "last_updated": "timestamp",
        },
        obrigatorias=("customer_id", "product_type", "currency", "product_status"),
        dominios={
            "currency": MOEDAS,
            "product_status": ("Active", "Blocked", "Closed", "Suspended"),
        },
        referencias=(
            Referencia("customer_id", "customers", essencial=True),
            Referencia("opening_branch_id", "branches", essencial=False),
        ),
    ),
    Contrato(
        tabela="transactions",
        chave=("transaction_id",),
        tipos={
            "transaction_date": "timestamp", "process_date": "date",
            "amount": "numeric(18,2)", "amount_usd": "numeric(18,2)",
            "is_fraud": "boolean", "fraud_score": "double precision",
            "latitude": "double precision", "longitude": "double precision",
        },
        obrigatorias=(
            "transaction_date", "customer_id", "product_id", "amount", "currency",
            "transaction_status",
        ),
        dominios={
            "currency": MOEDAS,
            "transaction_status": ("Approved", "Declined", "Pending", "Reversed"),
        },
        referencias=(
            Referencia("customer_id", "customers", essencial=True),
            Referencia("product_id", "products", essencial=True, mesmo_cliente=True),
            Referencia("branch_id", "branches", essencial=False),
        ),
    ),
    Contrato(
        tabela="complaints",
        chave=("complaint_id",),
        tipos={
            "creation_date": "timestamp", "process_date": "date",
            "claimed_amount": "numeric(18,2)", "assignment_date": "timestamp",
            "first_response_date": "timestamp", "resolution_date": "timestamp",
            "closing_date": "timestamp", "sla_breached": "boolean",
            "resolution_days": "double precision", "compensation_granted": "numeric(18,2)",
            "resolution_satisfaction": "double precision", "is_repeat_complainer": "boolean",
        },
        obrigatorias=("creation_date", "customer_id", "case_type", "status"),
        dominios={
            "case_type": ("Claim", "Complaint", "Request", "Suggestion"),
            "status": ("Closed", "Escalated", "In Process", "Open", "Rejected", "Resolved"),
        },
        referencias=(
            Referencia("customer_id", "customers", essencial=True),
            Referencia("affected_product_id", "products", essencial=False, mesmo_cliente=True),
            Referencia("related_branch_id", "branches", essencial=False),
        ),
    ),
)  # fmt: skip

POR_TABELA: dict[str, Contrato] = {contrato.tabela: contrato for contrato in CONTRATOS}


def colunas(contrato: Contrato) -> tuple[str, ...]:
    """Colunas da tabela curada: as mesmas da raw, na mesma ordem."""
    return COLUNAS[contrato.tabela]
