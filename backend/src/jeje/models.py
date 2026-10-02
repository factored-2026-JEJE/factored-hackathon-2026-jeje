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
    Index,
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
    # A última versão que a carga recusou com esta valendo (ACH-112); a próxima carga boa apaga.
    recusada_versao: Mapped[str | None] = mapped_column(Text)
    recusada_motivo: Mapped[str | None] = mapped_column(Text)
    recusada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Persona(Base):
    """Cliente de demonstração provisionado pelo servidor a partir da base curada (DEV-008).

    Só personas podem abrir sessão de teste; identidade nunca vem do chat nem do navegador."""

    __tablename__ = "personas"
    __table_args__ = ({"schema": "app"},)

    customer_id: Mapped[str] = mapped_column(Text, primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(SmallInteger, unique=True)


def _um_de(coluna: str, valores: tuple[str, ...]) -> str:
    """Expressão do CHECK que limita a coluna a uma lista fechada de valores."""
    return f"{coluna} IN (" + ", ".join(f"'{v}'" for v in valores) + ")"


# Dispositivo da sessão de teste, escolhido no acesso da demo (PRD-007, simulação): a base não diz
# se o dispositivo é cadastrado, e sem escolha vale o lado conservador ("novo", como na PRD-001).
DISPOSITIVOS = ("cadastrado", "novo")


class Sessao(Base):
    """Sessão de teste: o token só existe no cliente; aqui fica o sha256 dele."""

    __tablename__ = "sessoes"
    __table_args__ = (
        CheckConstraint(_um_de("dispositivo", DISPOSITIVOS), name="dispositivo"),
        {"schema": "app"},
    )

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, index=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispositivo: Mapped[str] = mapped_column(Text, server_default="novo")


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


# Estados da conversa (fonte única: o tipo `conversa.Estado` e o CHECK do banco saem daqui).
# `encerrada`: a recarga dos dados encerrou o atendimento em curso (PRD-002, DEV-020i).
ESTADOS_DA_CONVERSA = (
    "livre", "esclarecendo", "confirmando", "oferecendo_humano", "com_humano", "encerrada",
    "escolhendo_cartao", "confirmando_desbloqueio",
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
# Como a transação do turno foi achada (DEV-071): o filtro exato, o ranking (DEV-037), a escolha do
# cliente numa lista ou a transação já em curso na conversa.
RESOLVEDORES = ("filtro", "ranking", "escolha", "foco")


class Evento(Base):
    """Evento de atendimento (G11): o que cada turno fez e quanto levou; nunca token nem texto do
    cliente. Erro de turno desfeito vira evento próprio, gravado fora da transação que falhou."""

    __tablename__ = "eventos"
    __table_args__ = (
        CheckConstraint(_um_de("tipo", TIPOS_DE_EVENTO), name="tipo"),
        CheckConstraint("latencia_ms >= 0", name="latencia"),
        CheckConstraint(_um_de("resolvedor", RESOLVEDORES), name="resolvedor"),
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
    # Como a transação do turno foi achada (DEV-071): pelo ranking, também a versão da calibração,
    # a probabilidade da primeira e quantas podiam ser.
    resolvedor: Mapped[str | None] = mapped_column(Text, nullable=True)
    calibracao: Mapped[str | None] = mapped_column(Text, nullable=True)
    probabilidade: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    possiveis: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A versão dos dados em vigor quando o evento aconteceu (DEV-044): sobrevive à recarga.
    versao_dos_dados: Mapped[str | None] = mapped_column(Text, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


RESOLVEU = ("sim", "parcial", "nao")


class Review(Base):
    """Avaliação de uma conversa de teste por alguém do time: nota, se resolveu e o que deu errado.
    A conversa (e os turnos) já estão no banco; a Issue do GitHub, quando criada, fica anotada."""

    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("nota BETWEEN 1 AND 5", name="nota"),
        CheckConstraint(_um_de("resolveu", RESOLVEU), name="resolveu"),
        {"schema": "app"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    conversa_id: Mapped[str] = mapped_column(Text, ForeignKey("app.conversas.id"), index=True)
    avaliador: Mapped[str] = mapped_column(Text)
    nota: Mapped[int] = mapped_column(SmallInteger)
    resolveu: Mapped[str] = mapped_column(Text)
    comentario: Mapped[str] = mapped_column(Text)
    issue_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# Bloqueio simulado de cartão (PRD-007): o tipo vem do dispositivo da sessão, o motivo diz quem pode
# desfazer (o que veio de roubo ou perda, só o atendente) e quem desfez fica registrado.
TIPOS_DE_BLOQUEIO = ("preventivo", "completo")
MOTIVOS_DE_BLOQUEIO = ("pedido", "roubo_perda")
QUEM_DESFAZ = ("cliente", "atendente")
BLOQUEIO_SEQ = Sequence("bloqueio_seq", schema="app", metadata=Base.metadata)


class Bloqueio(Base):
    """Bloqueio simulado de um cartão do cliente (PRD-007). A curada não muda (é dado do desafio): o
    bloqueio fica aqui, com a fotografia do cartão (tipo e 4 últimos dígitos, nunca o número)."""

    __tablename__ = "bloqueios"
    __table_args__ = (
        CheckConstraint(_um_de("tipo", TIPOS_DE_BLOQUEIO), name="tipo"),
        CheckConstraint(_um_de("motivo", MOTIVOS_DE_BLOQUEIO), name="motivo"),
        CheckConstraint(_um_de("dispositivo", DISPOSITIVOS), name="dispositivo"),
        CheckConstraint(_um_de("desfeito_por", QUEM_DESFAZ), name="desfeito_por"),
        CheckConstraint("(desfeito_em IS NULL) = (desfeito_por IS NULL)", name="desfeito"),
        # Um bloqueio ativo por cartão do cliente: bloquear de novo não duplica (idempotência).
        Index(
            "uq_bloqueios_ativo",
            "customer_id",
            "product_id",
            unique=True,
            postgresql_where=text("desfeito_em IS NULL"),
        ),
        {"schema": "app"},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text)
    product_id: Mapped[str] = mapped_column(Text)
    produto: Mapped[str] = mapped_column(Text)
    ultimos4: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[str] = mapped_column(Text)
    motivo: Mapped[str] = mapped_column(Text)
    dispositivo: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reversivel_ate: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    desfeito_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    desfeito_por: Mapped[str | None] = mapped_column(Text, nullable=True)
    # O caso do atendente a que o bloqueio pertence (PRD-009): todo desbloqueio é anotado nele.
    atendimento: Mapped[str | None] = mapped_column(
        Text, ForeignKey("app.handoffs.id"), nullable=True
    )
