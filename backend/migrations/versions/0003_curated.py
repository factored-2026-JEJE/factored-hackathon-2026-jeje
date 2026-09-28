"""Camada curada (tipada, com chaves e referências) e schema de qualidade.

Revision ID: 0003
Revises: 0002

DDL congelada a partir de `jeje.dados.curado` nesta revisão.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CRIAR = [
    """
CREATE TABLE curated.branches (
	branch_id TEXT NOT NULL,
	branch_code TEXT,
	branch_name TEXT,
	branch_type TEXT,
	address TEXT,
	city TEXT,
	state TEXT,
	country TEXT,
	postal_code TEXT,
	geographic_zone TEXT,
	phone TEXT,
	email TEXT,
	opening_time TIME WITHOUT TIME ZONE,
	closing_time TIME WITHOUT TIME ZONE,
	has_atms BOOLEAN,
	atm_count INTEGER,
	has_teller_windows BOOLEAN,
	teller_window_count INTEGER,
	latitude DOUBLE PRECISION,
	longitude DOUBLE PRECISION,
	branch_opening_date DATE,
	branch_status TEXT,
	_arquivo TEXT NOT NULL,
	_linha INTEGER NOT NULL,
	CONSTRAINT pk_branches PRIMARY KEY (branch_id)
)
""",
    """
CREATE TABLE curated.daily_exchange_rates (
	date DATE NOT NULL,
	source_currency TEXT NOT NULL,
	target_currency TEXT NOT NULL,
	exchange_rate DOUBLE PRECISION NOT NULL,
	buy_rate DOUBLE PRECISION,
	sell_rate DOUBLE PRECISION,
	source TEXT,
	_arquivo TEXT NOT NULL,
	_linha INTEGER NOT NULL,
	CONSTRAINT pk_daily_exchange_rates PRIMARY KEY (date, source_currency, target_currency)
)
""",
    """
CREATE TABLE curated.customers (
	customer_id TEXT NOT NULL,
	document_number TEXT,
	document_type TEXT,
	first_name TEXT,
	last_name TEXT,
	date_of_birth DATE,
	gender TEXT,
	email TEXT,
	mobile_phone TEXT,
	landline_phone TEXT,
	address TEXT,
	city TEXT,
	state TEXT,
	country TEXT,
	postal_code TEXT,
	detected_accent TEXT,
	segment TEXT,
	credit_score DOUBLE PRECISION,
	estimated_monthly_income NUMERIC(18, 2),
	occupation TEXT,
	marital_status TEXT,
	education_level TEXT,
	registration_date TIMESTAMP WITHOUT TIME ZONE,
	registration_branch_id TEXT,
	customer_status TEXT,
	last_updated TIMESTAMP WITHOUT TIME ZONE,
	accepts_marketing BOOLEAN,
	_arquivo TEXT NOT NULL,
	_linha INTEGER NOT NULL,
	CONSTRAINT pk_customers PRIMARY KEY (customer_id),
	CONSTRAINT fk_customers_registration_branch_id FOREIGN KEY(registration_branch_id) REFERENCES curated.branches (branch_id)
)
""",
    """
CREATE TABLE curated.products (
	product_id TEXT NOT NULL,
	customer_id TEXT NOT NULL,
	product_type TEXT NOT NULL,
	product_number TEXT,
	currency TEXT NOT NULL,
	current_balance NUMERIC(18, 2),
	credit_limit NUMERIC(18, 2),
	interest_rate DOUBLE PRECISION,
	opening_date DATE,
	expiration_date DATE,
	opening_branch_id TEXT,
	product_status TEXT NOT NULL,
	opening_channel TEXT,
	has_linked_app BOOLEAN,
	days_past_due DOUBLE PRECISION,
	last_transaction_date TIMESTAMP WITHOUT TIME ZONE,
	last_updated TIMESTAMP WITHOUT TIME ZONE,
	_arquivo TEXT NOT NULL,
	_linha INTEGER NOT NULL,
	CONSTRAINT pk_products PRIMARY KEY (product_id),
	CONSTRAINT uq_products_dono UNIQUE (product_id, customer_id),
	CONSTRAINT fk_products_customer_id FOREIGN KEY(customer_id) REFERENCES curated.customers (customer_id),
	CONSTRAINT fk_products_opening_branch_id FOREIGN KEY(opening_branch_id) REFERENCES curated.branches (branch_id)
)
""",
    """
CREATE TABLE curated.transactions (
	transaction_id TEXT NOT NULL,
	transaction_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	process_date DATE,
	product_id TEXT NOT NULL,
	customer_id TEXT NOT NULL,
	transaction_type TEXT,
	transaction_category TEXT,
	amount NUMERIC(18, 2) NOT NULL,
	currency TEXT NOT NULL,
	amount_usd NUMERIC(18, 2),
	channel TEXT,
	branch_id TEXT,
	merchant_name TEXT,
	merchant_category TEXT,
	transaction_country TEXT,
	transaction_city TEXT,
	transaction_status TEXT NOT NULL,
	response_code TEXT,
	is_fraud BOOLEAN,
	fraud_score DOUBLE PRECISION,
	latitude DOUBLE PRECISION,
	longitude DOUBLE PRECISION,
	_arquivo TEXT NOT NULL,
	_linha INTEGER NOT NULL,
	CONSTRAINT pk_transactions PRIMARY KEY (transaction_id),
	CONSTRAINT fk_transactions_customer_id FOREIGN KEY(customer_id) REFERENCES curated.customers (customer_id),
	CONSTRAINT fk_transactions_product_id_dono FOREIGN KEY(product_id, customer_id) REFERENCES curated.products (product_id, customer_id),
	CONSTRAINT fk_transactions_branch_id FOREIGN KEY(branch_id) REFERENCES curated.branches (branch_id)
)
""",
    """
CREATE TABLE curated.complaints (
	complaint_id TEXT NOT NULL,
	creation_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	process_date DATE,
	customer_id TEXT NOT NULL,
	case_type TEXT NOT NULL,
	category TEXT,
	subcategory TEXT,
	reception_channel TEXT,
	affected_product_id TEXT,
	related_branch_id TEXT,
	origin_interaction_id TEXT,
	description TEXT,
	claimed_amount NUMERIC(18, 2),
	currency TEXT,
	priority TEXT,
	status TEXT NOT NULL,
	assigned_agent_id TEXT,
	assignment_date TIMESTAMP WITHOUT TIME ZONE,
	first_response_date TIMESTAMP WITHOUT TIME ZONE,
	resolution_date TIMESTAMP WITHOUT TIME ZONE,
	closing_date TIMESTAMP WITHOUT TIME ZONE,
	sla_breached BOOLEAN,
	resolution_days DOUBLE PRECISION,
	resolution TEXT,
	compensation_granted NUMERIC(18, 2),
	resolution_satisfaction DOUBLE PRECISION,
	is_repeat_complainer BOOLEAN,
	_arquivo TEXT NOT NULL,
	_linha INTEGER NOT NULL,
	CONSTRAINT pk_complaints PRIMARY KEY (complaint_id),
	CONSTRAINT fk_complaints_customer_id FOREIGN KEY(customer_id) REFERENCES curated.customers (customer_id),
	CONSTRAINT fk_complaints_affected_product_id_dono FOREIGN KEY(affected_product_id, customer_id) REFERENCES curated.products (product_id, customer_id),
	CONSTRAINT fk_complaints_related_branch_id FOREIGN KEY(related_branch_id) REFERENCES curated.branches (branch_id)
)
""",
    """
CREATE TABLE quality.quarentena (
	id BIGSERIAL NOT NULL,
	tabela TEXT NOT NULL,
	_arquivo TEXT NOT NULL,
	_linha INTEGER NOT NULL,
	motivos TEXT[] NOT NULL,
	registro JSONB NOT NULL,
	CONSTRAINT pk_quarentena PRIMARY KEY (id)
)
""",
    """
CREATE TABLE quality.relatorio (
	tabela TEXT NOT NULL,
	raw BIGINT NOT NULL,
	curado BIGINT NOT NULL,
	quarentena BIGINT NOT NULL,
	copias_descartadas BIGINT NOT NULL,
	motivos JSONB NOT NULL,
	anulacoes JSONB NOT NULL,
	normalizacoes JSONB NOT NULL,
	CONSTRAINT pk_relatorio PRIMARY KEY (tabela)
)
""",
]

# Ordem inversa às dependências.
REMOVER = [
    "quality.relatorio",
    "quality.quarentena",
    "curated.complaints",
    "curated.transactions",
    "curated.products",
    "curated.customers",
    "curated.daily_exchange_rates",
    "curated.branches",
]


def upgrade() -> None:
    op.execute("CREATE SCHEMA curated")
    op.execute("CREATE SCHEMA quality")
    for ddl in CRIAR:
        op.execute(ddl)


def downgrade() -> None:
    for tabela in REMOVER:
        op.execute(f"DROP TABLE {tabela}")
    op.execute("DROP SCHEMA quality")
    op.execute("DROP SCHEMA curated")
