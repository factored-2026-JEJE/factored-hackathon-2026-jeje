"""Rotas da conversa sem modelo (G10): abrir, enviar mensagem (turno) e reabrir o histórico."""

import logging
import time
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from jeje import conversa, eventos, politica
from jeje.config import ConfigDep
from jeje.db import EngineDep
from jeje.interpretacao_modelo import Leitura
from jeje.pre_caso_api import ID_PROPOSTA, Proposta
from jeje.sessao_api import CORPO_ILEGIVEL, RESPOSTAS_SESSAO, SessaoDep

router = APIRouter(responses=RESPOSTAS_SESSAO)
log = logging.getLogger("jeje.conversa")

NAO_ENCONTRADA = "Conversa não encontrada"
ConversaId = Annotated[str, Path(pattern=ID_PROPOSTA)]


class NovaConversa(BaseModel):
    idioma: Literal["es", "pt"]


class ConversaAberta(BaseModel):
    conversa_id: str
    idioma: Literal["es", "pt"]
    estado: str
    resposta: str


# Sem caractere de controle (fora tab e quebra de linha): o NUL nem cabe no banco (ACH-153).
SEM_CONTROLE = r"^[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]*$"


class Mensagem(BaseModel):
    texto: str = Field(min_length=1, max_length=conversa.LIMITE_MENSAGEM, pattern=SEM_CONTROLE)


class Opcao(BaseModel):
    numero: int
    transaction_id: str
    descricao: str


class ResultadoDoTurno(BaseModel):
    """O que o turno fez: regra aplicada, efeito verificado e a resposta ao cliente."""

    conversa_id: str
    numero: int
    idioma: Literal["es", "pt"]
    intencao: str
    regra: str
    acao: str
    estado: str
    resposta: str
    transaction_id: str | None
    opcoes: list[Opcao]
    proposta: Proposta | None
    protocolo: str | None
    atendimento: str | None
    bloqueio: str | None
    # "Por que esta resposta?" (DEV-031): o que a regra quer dizer, quem leu a mensagem, o efeito
    # criado neste turno e de onde vieram os fatos.
    descricao: str | None
    interpretacao: str
    efeito: str | None
    fontes: list[str]


class TurnoRegistrado(BaseModel):
    numero: int
    mensagem: str
    resposta: str
    regra: str
    acao: str
    estado: str
    criado_em: datetime


class Historico(BaseModel):
    conversa_id: str
    idioma: Literal["es", "pt"]
    estado: str
    atendimento: str | None = Field(
        description="Caso que está com o atendente (AT-…), se a conversa já foi encaminhada"
    )
    turnos: list[TurnoRegistrado]


@router.post("/conversas", status_code=201, responses=CORPO_ILEGIVEL)
def abrir_conversa(pedido: NovaConversa, ativa: SessaoDep, engine: EngineDep) -> ConversaAberta:
    with engine.begin() as conexao:
        conversa_id, saudacao = conversa.abrir(conexao, ativa.customer_id, pedido.idioma)
    return ConversaAberta(
        conversa_id=conversa_id, idioma=pedido.idioma, estado="livre", resposta=saudacao
    )


@router.post(
    "/conversas/{conversa_id}/turnos",
    responses={
        **CORPO_ILEGIVEL,
        404: {"description": NAO_ENCONTRADA},
        503: {"description": "Turno não registrado; nada foi criado"},
    },
)
def enviar_mensagem(
    conversa_id: ConversaId,
    mensagem: Mensagem,
    ativa: SessaoDep,
    engine: EngineDep,
    config: ConfigDep,
    request: Request,
) -> ResultadoDoTurno:
    """Um turno: a política decide com fatos verificados; efeito só com confirmação explícita."""
    inicio, leitura = time.perf_counter(), None
    try:
        with engine.connect() as conexao:
            preparo = conversa.preparar(conexao, ativa.customer_id, conversa_id)
        # Fora de qualquer conexão: esperar o modelo não prende trava, transação nem pool.
        leitura = conversa.ler(preparo, mensagem.texto, request.app.state.interpretador)
        with engine.begin() as conexao:
            resultado = conversa.turno(
                conexao,
                ativa.customer_id,
                conversa_id,
                mensagem.texto,
                leitura,
                config.limites(),
                config.proposta_ttl_minutos,
                inicio,
                ativa.dispositivo,
                config.janela_desbloqueio_dias,
                request.app.state.calibracao,
            )
    except conversa.ConversaNaoEncontrada:
        raise HTTPException(status_code=404, detail=NAO_ENCONTRADA) from None
    except (SQLAlchemyError, RuntimeError) as erro:
        # Sem sucesso falso: o turno inteiro foi desfeito, inclusive o efeito que não se confirmou
        # na releitura; reenviar a mesma mensagem é seguro.
        _registrar_erro(engine, conversa_id, erro, inicio, leitura)
        raise HTTPException(
            status_code=503, detail="Turno não registrado; nada foi criado. Tente de novo."
        ) from None
    saida = resultado.saida
    # Depois do commit: o log só afirma o que ficou gravado (nunca o texto do cliente).
    log.info(
        "turno conversa=%s numero=%d intencao=%s regra=%s acao=%s estado=%s efeito=%s",
        conversa_id,
        resultado.numero,
        resultado.intencao,
        saida.regra,
        saida.acao,
        saida.estado,
        resultado.efeito,
    )
    return ResultadoDoTurno(
        conversa_id=resultado.conversa_id,
        numero=resultado.numero,
        idioma=resultado.idioma,
        intencao=resultado.intencao,
        regra=saida.regra,
        acao=saida.acao,
        estado=saida.estado,
        resposta=resultado.resposta,
        transaction_id=saida.transaction_id,
        opcoes=[Opcao(**o.__dict__) for o in saida.opcoes],
        proposta=None if saida.proposta is None else Proposta(**saida.proposta.__dict__),
        protocolo=saida.protocolo,
        atendimento=saida.atendimento,
        bloqueio=saida.bloqueio,
        descricao=politica.DESCRICOES.get(saida.regra),
        interpretacao=leitura.fonte,
        efeito=resultado.efeito,
        fontes=list(resultado.fontes),
    )


def _registrar_erro(
    engine, conversa_id: str, erro: Exception, inicio: float, leitura: Leitura | None
) -> None:
    """O turno foi desfeito; o erro fica registrado à parte (só a classe, sem texto nem dados),
    com a leitura já feita (a chamada ao modelo custou mesmo sem turno). Se nem isso grava
    (banco fora), o cliente continua recebendo o 503."""
    log.warning("turno desfeito conversa=%s erro=%s", conversa_id, type(erro).__name__)
    evento = eventos.Evento(
        tipo="erro",
        latencia_ms=eventos.desde(inicio),
        conversa_id=conversa_id,
        erro=type(erro).__name__,
        **conversa.rastro_da_leitura(leitura),
    )
    try:
        with engine.begin() as conexao:
            eventos.registrar(conexao, evento)
    except SQLAlchemyError as outro:
        log.warning(
            "evento de erro nao gravado conversa=%s erro=%s", conversa_id, type(outro).__name__
        )


@router.get("/conversas/{conversa_id}", responses={404: {"description": NAO_ENCONTRADA}})
def historico(conversa_id: ConversaId, ativa: SessaoDep, engine: EngineDep) -> Historico:
    """Reabre a conversa (ex.: depois de recarregar a página), só para o dono."""
    with engine.connect() as conexao:
        try:
            dados, turnos = conversa.historico(conexao, ativa.customer_id, conversa_id)
        except conversa.ConversaNaoEncontrada:
            raise HTTPException(status_code=404, detail=NAO_ENCONTRADA) from None
    return Historico(
        conversa_id=dados["id"],
        idioma=dados["idioma"],
        estado=dados["estado"],
        atendimento=dados["atendimento"],
        turnos=[TurnoRegistrado(**t) for t in turnos],
    )
