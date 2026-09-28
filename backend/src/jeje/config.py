"""Configuração do processo.

Os valores vêm do ambiente montado pelo `compose.yaml` versionado (ENG-003); segredos chegam pelo
`.env`, nunca versionado. Nenhum campo tem default: variável ausente precisa falhar na
inicialização, em vez de o código assumir um valor que diverge do compose.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Prefixo público sob o qual o proxy expõe a API (ex.: "/api"); vazio quando acessada direto.
    api_root_path: str
    # URL SQLAlchemy do PostgreSQL (driver psycopg).
    database_url: str
    # Limite para abrir conexão; evita que readiness e requisições fiquem presas num banco mudo.
    db_connect_timeout_s: int = Field(gt=0)
    # Validade da sessão de teste, em minutos.
    sessao_ttl_minutos: int = Field(gt=0)
    # Liga a abertura de sessão por persona de demonstração (DEV-008); desligado, só 404.
    modo_demo: bool
