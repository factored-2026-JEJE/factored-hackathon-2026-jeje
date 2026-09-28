"""Modelos persistidos. Migrations Alembic são a fonte do schema; estes modelos devem coincidir
com elas (verificado por `alembic check` nos testes)."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, MetaData, SmallInteger, Text, func
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
