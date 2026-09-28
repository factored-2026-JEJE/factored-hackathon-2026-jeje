"""Configuração do processo.

Os valores vêm do ambiente montado pelo `compose.yaml` versionado (ENG-003); segredos chegam pelo
`.env`, nunca versionado. Nenhum campo tem default: variável ausente precisa falhar na
inicialização, em vez de o código assumir um valor que diverge do compose.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Prefixo público sob o qual o proxy expõe a API (ex.: "/api"); vazio quando acessada direto.
    api_root_path: str
