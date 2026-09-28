"""Configuração do pipeline de dados. Valores do compose versionado; chaves do S3 só no `.env`."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from jeje.dados.raw import COLUNAS


class ConfigDados(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Onde ficam os CSV baixados e o manifesto versionado (montados pelo compose).
    dataset_raw_dir: Path
    dataset_manifest_dir: Path
    # Tabelas carregadas na camada raw, separadas por vírgula.
    dataset_tables: Annotated[list[str], NoDecode]
    # "s3": baixa do bucket dos organizadores; "fixture": usa arquivos já presentes (testes/CI).
    dataset_source: Literal["s3", "fixture"]
    # Segredo (vem do .env): s3://bucket/prefixo/. Vazio só é aceito com source=fixture.
    dataset_s3_uri: str = Field(default="", repr=False)
    # Endpoint S3 alternativo (servidor de testes); vazio = AWS.
    dataset_s3_endpoint: str
    dataset_download_workers: int = Field(gt=0)

    @field_validator("dataset_tables", mode="before")
    @classmethod
    def separar_tabelas(cls, valor: object) -> object:
        if isinstance(valor, str):
            return [tabela.strip() for tabela in valor.split(",") if tabela.strip()]
        return valor

    @field_validator("dataset_tables")
    @classmethod
    def tabelas_conhecidas(cls, tabelas: list[str]) -> list[str]:
        desconhecidas = sorted(set(tabelas) - set(COLUNAS))
        if desconhecidas:
            raise ValueError(f"tabelas fora da camada raw: {', '.join(desconhecidas)}")
        if not tabelas:
            raise ValueError("DATASET_TABLES vazio")
        return tabelas

    @model_validator(mode="after")
    def uri_quando_s3(self) -> "ConfigDados":
        if self.dataset_source == "s3" and not self.dataset_s3_uri:
            raise ValueError("DATASET_S3_URI ausente: copie .env.example para .env e preencha")
        return self
