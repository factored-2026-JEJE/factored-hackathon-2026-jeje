"""Configuração do processo.

Os valores vêm do ambiente montado pelo `compose.yaml` versionado (ENG-003); segredos chegam pelo
`.env`, nunca versionado. Nenhum campo tem default: variável ausente precisa falhar na
inicialização, em vez de o código assumir um valor que diverge do compose.
"""

from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, Request
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from jeje.politica import Limites

# Senha dos jurados: longa o bastante para não ser adivinhada sem limite de tentativas.
MINIMO_DA_SENHA = 16


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
    # Janela da contestação em dias, contados do último dia dos dados (POL-HUM-05), e reincidência:
    # N pré-casos do cliente nos últimos N dias do relógio mandam o próximo ao humano (POL-HUM-06).
    janela_contestacao_dias: int = Field(gt=0)
    reincidencia_pre_casos: int = Field(gt=0)
    reincidencia_dias: int = Field(gt=0)
    # Bloqueio simulado de cartão (PRD-007): por quantos dias o bloqueio fica reversível.
    janela_desbloqueio_dias: int = Field(gt=0)
    # Validade da proposta de pré-caso até a confirmação do cliente, em minutos.
    proposta_ttl_minutos: int = Field(gt=0)
    # Leitura da mensagem: "regras" (sem modelo), "leitor" (classificador e5 local), "leitor_modelo"
    # (o leitor e, no que ele não decide, o LLM local com exemplos, DEV-042) ou "ollama" (modelo
    # local); todos só quando as regras não entendem, e segurança e confirmação continuam das
    # regras.
    interpretador: Literal["regras", "leitor", "leitor_modelo", "ollama"]
    # Leitor e5 (usados só com INTERPRETADOR=leitor): artefato treinado e pesos do e5, gerados no
    # build da imagem (estágio `modelo`), e a confiança mínima para ele decidir (ACH-028).
    leitor_modelo: Path
    leitor_e5: Path
    # Portão de intenção de Enzo (TF-IDF, jeje.intencao): artefato do build, lido na primeira
    # chamada das rotas /intencao; sem ele, as rotas respondem 503.
    intencao_modelo: Path
    leitor_limite: float = Field(gt=0, le=1)
    # LLM do "não entendi" (usados só com INTERPRETADOR=leitor_modelo): o modelo no Ollama (mesmos
    # servidor e tempos do modo ollama) e os exemplos gerados no build ao lado do leitor.
    nao_entendi_modelo: str
    leitor_vizinhos: Path
    # Garantia de encaminhamento da fraude (DEV-046, só com INTERPRETADOR=leitor_modelo): ligada ou
    # não, e o detector gerado no build ao lado do leitor.
    garantia_de_fraude: bool
    leitor_garantia: Path
    # "Qual transação" (DEV-037): ranking com conjunto conformal, calibrado no arquivo versionado
    # do pacote, ou o filtro exato de antes.
    resolvedor_de_transacao: Literal["ranking", "filtro"]
    qual_transacao_calibracao: Path
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
    # ou sem token, a review fica só no banco. O token é segredo: vem do ambiente de quem sobe a
    # stack (make exportar-reviews).
    testadores: str
    reviews_repo: str
    github_api_url: str
    github_token: str
    # Nível dos logs da aplicação (saída padrão, uma linha por acontecimento; ver jeje.logs).
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    # Acesso dos jurados (PRD-009, ver jeje.acesso): com senha, toda rota fora a saúde e o próprio
    # acesso exige o cookie de acesso; vazia, o portão fica desligado. A senha é segredo (o compose
    # da publicação a tira do .env). A publicação marca o acesso como obrigatório: sem senha, a API
    # não sobe. O cookie vale as horas configuradas e é `Secure` atrás do HTTPS da publicação.
    acesso_senha: SecretStr
    acesso_obrigatorio: bool
    acesso_validade_horas: int = Field(gt=0)
    acesso_cookie_seguro: bool

    @model_validator(mode="after")
    def _acesso_com_senha_forte(self) -> "Settings":
        senha = self.acesso_senha.get_secret_value()
        if self.acesso_obrigatorio and not senha:
            raise ValueError("ACESSO_OBRIGATORIO exige ACESSO_SENHA")
        if senha and len(senha) < MINIMO_DA_SENHA:
            raise ValueError(f"ACESSO_SENHA precisa de pelo menos {MINIMO_DA_SENHA} caracteres")
        return self

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
            janela_contestacao_dias=self.janela_contestacao_dias,
            reincidencia_pre_casos=self.reincidencia_pre_casos,
            reincidencia_dias=self.reincidencia_dias,
        )


def config_da_requisicao(request: Request) -> Settings:
    """Dependência FastAPI: a configuração única do processo, criada em `create_app`."""
    return request.app.state.settings


ConfigDep = Annotated[Settings, Depends(config_da_requisicao)]
