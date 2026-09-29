"""Configuração do processo.

Os valores vêm do ambiente montado pelo `compose.yaml` versionado (ENG-003); segredos chegam pelo
`.env`, nunca versionado. Nenhum campo tem default: variável ausente precisa falhar na
inicialização, em vez de o código assumir um valor que diverge do compose.
"""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, Request
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from jeje.politica import Limites


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Prefixo público sob o qual o proxy expõe a API (ex.: "/api"); vazio quando acessada direto.
    api_root_path: str
    # URL SQLAlchemy do PostgreSQL (driver psycopg).
    database_url: str
    # Limite para abrir conexão; evita que readiness e requisições fiquem presas num banco mudo.
    db_connect_timeout_s: int = Field(gt=0)
    # Pool de conexões da API: tamanho, excedente permitido e espera máxima por uma conexão livre
    # (esgotado → 503 com Retry-After, não requisição pendurada).
    db_pool_size: int = Field(gt=0)
    db_pool_max_overflow: int = Field(ge=0)
    db_pool_timeout_s: float = Field(gt=0)
    # Tempo máximo de um comando SQL da API: consulta descontrolada é cancelada (503), não trava
    # conexão. A carga e os scripts não têm esse limite.
    db_statement_timeout_ms: int = Field(gt=0)
    # Validade da sessão de teste, em minutos.
    sessao_ttl_minutos: int = Field(gt=0)
    # Liga a abertura de sessão por persona de demonstração (DEV-008); desligado, só 404.
    modo_demo: bool
    # Limites da política simulada do pré-caso (PRD-001), em USD. Padrão por transação (POL-HUM-02).
    limite_pre_caso_usd: Decimal = Field(gt=0)
    # À noite, em canal digital (celular ou computador): por transação e soma do dia (POL-HUM-04).
    limite_noturno_usd: Decimal = Field(gt=0)
    limite_noturno_dia_usd: Decimal = Field(gt=0)
    # Período noturno [início, fim) em horas locais da transação e canais digitais (vírgulas).
    noturno_inicio_h: int = Field(ge=0, le=23)
    noturno_fim_h: int = Field(ge=0, le=23)
    canais_digitais: str
    # Transferência acima disto vai para análise de segurança (POL-SEG-01).
    limite_seguranca_transferencia_usd: Decimal = Field(gt=0)
    # Validade da proposta de pré-caso até a confirmação do cliente, em minutos.
    proposta_ttl_minutos: int = Field(gt=0)
    # Leitura da mensagem: "regras" (sem modelo), "leitor" (classificador e5 local) ou "ollama"
    # (modelo local); os dois só quando as regras não entendem, e segurança e confirmação continuam
    # das regras.
    interpretador: Literal["regras", "leitor", "ollama"]
    # Leitor e5 (usados só com INTERPRETADOR=leitor): artefato treinado e pesos do e5, gerados no
    # build da imagem (estágio `modelo`), e a confiança mínima para ele decidir (ACH-028).
    leitor_modelo: Path
    leitor_e5: Path
    leitor_limite: float = Field(gt=0, le=1)
    # Servidor Ollama, modelo e tempo máximo por chamada (usados só com INTERPRETADOR=ollama).
    ollama_url: str
    ollama_modelo: str
    ollama_timeout_s: float = Field(gt=0)
    # Quanto tempo o Ollama mantém o modelo carregado depois da última chamada (ex.: 30m).
    ollama_keep_alive: str
    # Tempo máximo para o modelo carregar ao iniciar a API (em segundo plano; não atrasa nada).
    ollama_carga_timeout_s: float = Field(gt=0)
    # Reviews das conversas de teste: quem pode avaliar (logins do GitHub separados por vírgula;
    # vazio: ninguém), o repositório onde cada review vira Issue e a API do GitHub. Sem repositório
    # ou sem token, a review fica só no banco. O token é segredo: vem do ambiente (no Codespace, o
    # dele).
    testadores: str
    reviews_repo: str
    github_api_url: str
    github_token: str
    # Nível dos logs da aplicação (saída padrão, uma linha por acontecimento; ver jeje.logs).
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]

    def limites(self) -> Limites:
        """Os limites da política, na forma que ela usa."""
        return Limites(
            padrao_usd=self.limite_pre_caso_usd,
            noturno_usd=self.limite_noturno_usd,
            noturno_dia_usd=self.limite_noturno_dia_usd,
            noturno_inicio_h=self.noturno_inicio_h,
            noturno_fim_h=self.noturno_fim_h,
            canais_digitais=frozenset(
                c.strip() for c in self.canais_digitais.split(",") if c.strip()
            ),
            seguranca_transferencia_usd=self.limite_seguranca_transferencia_usd,
        )


def config_da_requisicao(request: Request) -> Settings:
    """Dependência FastAPI: a configuração única do processo, criada em `create_app`."""
    return request.app.state.settings


ConfigDep = Annotated[Settings, Depends(config_da_requisicao)]
