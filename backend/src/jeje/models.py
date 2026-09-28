"""Modelos persistidos. Migrations Alembic são a fonte do schema; estes modelos devem coincidir
com elas (verificado por `alembic check` nos testes)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    Numeric,
    Sequence,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class DatasetVersion(Base):
    """Versão do dataset carregado no banco: uma única linha, substituída a cada carga completa."""

    __tablename__ = "dataset_version"
    __table_args__ = (CheckConstraint("id = 1", name="linha_unica"), {"schema": "meta"})

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    # sha256 do manifesto versionado que descreve os arquivos carregados.
    version: Mapped[str] = mapped_column(Text)
    # Origem declarada da carga ("s3" ou "fixture"), para nunca confundir dado de teste com real.
    source: Mapped[str] = mapped_column(Text)
    # sha256 do código do pipeline de dados que produziu raw/curated: mudar contrato recarrega.
    pipeline: Mapped[str] = mapped_column(Text, server_default="")
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Persona(Base):
    """Cliente de demonstração provisionado pelo servidor a partir da base curada (DEV-008).

    Só personas podem abrir sessão de teste; identidade nunca vem do chat nem do navegador."""

    __tablename__ = "personas"
    __table_args__ = ({"schema": "app"},)

    customer_id: Mapped[str] = mapped_column(Text, primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(SmallInteger, unique=True)


class Sessao(Base):
    """Sessão de teste: o token só existe no cliente; aqui fica o sha256 dele."""

    __tablename__ = "sessoes"
    __table_args__ = ({"schema": "app"},)

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, index=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PropostaDePreCaso(Base):
    """Proposta de pré-caso: fatos da transação no momento em que a política permitiu propor."""

    __tablename__ = "propostas_pre_caso"
    __table_args__ = ({"schema": "app"},)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text)
    transaction_id: Mapped[str] = mapped_column(Text)
    fatos: Mapped[dict] = mapped_column(JSONB)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


PROTOCOLO_SEQ = Sequence("protocolo_seq", schema="app", metadata=Base.metadata)


class PreCaso(Base):
    """Pré-caso recebido (DEV-012): um por transação do cliente; nunca move dinheiro."""

    __tablename__ = "pre_casos"
    __table_args__ = (
        UniqueConstraint("proposta_id", name="uq_pre_casos_proposta_id"),
        UniqueConstraint("customer_id", "transaction_id", name="uq_pre_casos_transacao"),
        {"schema": "app"},
    )

    protocolo: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text)
    transaction_id: Mapped[str] = mapped_column(Text)
    proposta_id: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text, server_default="recebido")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Handoff(Base):
    """Encaminhamento para humano (DEV-016): o bastante para seguir sem ler a conversa inteira."""

    __tablename__ = "handoffs"
    __table_args__ = ({"schema": "app"},)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, index=True)
    regra: Mapped[str] = mapped_column(Text)
    idioma: Mapped[str] = mapped_column(Text)
    pedido: Mapped[str] = mapped_column(Text)
    transacao: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    acoes: Mapped[list] = mapped_column(JSONB)
    pendencias: Mapped[list] = mapped_column(JSONB)
    estado: Mapped[str] = mapped_column(Text, server_default="aberto")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def _um_de(coluna: str, valores: tuple[str, ...]) -> str:
    """Expressão do CHECK que limita a coluna a uma lista fechada de valores."""
    return f"{coluna} IN (" + ", ".join(f"'{v}'" for v in valores) + ")"


# Estados da conversa (fonte única: o tipo `conversa.Estado` e o CHECK do banco saem daqui).
# `encerrada`: a recarga dos dados encerrou o atendimento em curso (PRD-002, DEV-020i).
ESTADOS_DA_CONVERSA = (
    "livre", "esclarecendo", "confirmando", "oferecendo_humano", "com_humano", "encerrada",
)  # fmt: skip


class Conversa(Base):
    """Conversa de atendimento (G10): estado entre turnos, sempre de um cliente da sessão."""

    __tablename__ = "conversas"
    __table_args__ = (
        CheckConstraint("idioma IN ('es', 'pt')", name="idioma"),
        CheckConstraint(_um_de("estado", ESTADOS_DA_CONVERSA), name="estado"),
        {"schema": "app"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, index=True)
    idioma: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text, server_default="livre")
    # Só o necessário para o próximo turno: opções listadas, proposta pendente, foco, atendimento.
    contexto: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    turnos: Mapped[int] = mapped_column(Integer, server_default="0")
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Turno(Base):
    """Um turno: a mensagem (limitada), a intenção lida, a regra aplicada e a resposta dada."""

    __tablename__ = "turnos"
    __table_args__ = ({"schema": "app"},)

    conversa_id: Mapped[str] = mapped_column(Text, ForeignKey("app.conversas.id"), primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, primary_key=True)
    mensagem: Mapped[str] = mapped_column(Text)
    idioma: Mapped[str] = mapped_column(Text)
    intencao: Mapped[str] = mapped_column(Text)
    regra: Mapped[str] = mapped_column(Text)
    acao: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text)  # estado da conversa depois do turno
    resposta: Mapped[str] = mapped_column(Text)
    transaction_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    efeito: Mapped[str | None] = mapped_column(Text, nullable=True)  # protocolo, atendimento…
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Tipos de evento (fonte única: o tipo `eventos.Evento.tipo` e o CHECK do banco saem daqui):
# turno da conversa, erro de turno desfeito, ação fora de um turno (rota direta, atendente) e
# recarga dos dados.
TIPOS_DE_EVENTO = ("turno", "erro", "acao", "recarga")


class Evento(Base):
    """Evento de atendimento (G11): o que cada turno fez e quanto levou; nunca token nem texto do
    cliente. Erro de turno desfeito vira evento próprio, gravado fora da transação que falhou."""

    __tablename__ = "eventos"
    __table_args__ = (
        CheckConstraint(_um_de("tipo", TIPOS_DE_EVENTO), name="tipo"),
        CheckConstraint("latencia_ms >= 0", name="latencia"),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    tipo: Mapped[str] = mapped_column(Text)
    conversa_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intencao: Mapped[str | None] = mapped_column(Text, nullable=True)
    regra: Mapped[str | None] = mapped_column(Text, nullable=True)
    acao: Mapped[str | None] = mapped_column(Text, nullable=True)
    efeito: Mapped[str | None] = mapped_column(Text, nullable=True)
    fontes: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)  # classe do erro, sem mensagem
    # Quem leu a mensagem: "regras", "ollama:<modelo>" ou "regras (fallback: <motivo>)".
    interpretacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Chamada ao modelo neste turno (só quando houve): latência e tokens informados pelo servidor.
    modelo_latencia_ms: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    modelo_tokens_entrada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modelo_tokens_saida: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latencia_ms: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    # X-Request-ID da requisição que gerou o evento: liga a resposta, o log e este trace.
    requisicao: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
