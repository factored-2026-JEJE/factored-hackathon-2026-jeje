// Textos das abas Atendente, Operação e How to test (DEV-032b, 2.10) que o design não tem, no tom e
// nas três línguas dele. Os do design ficam em app/conteudo.ts, só para leitura.
import { E, type Lingua, type Textos, type Traducao } from "../app/conteudo";

export const traduzir = (texto: Traducao, lingua: Lingua): string => texto[lingua] ?? texto.en;

/** O tipo de caso do design para cada regra que encaminha (os rótulos de t.cases). */
export type TipoDeCaso = keyof Textos["cases"];
export const TIPO_DA_REGRA: Readonly<Record<string, TipoDeCaso>> = {
  "POL-HUM-01": "fraud",
  "POL-HUM-03": "agent",
  "POL-ESC-01": "scope",
  "POL-HUM-06": "tooMany",
  "POL-BLQ-05": "unblock",
  "POL-BLQ-01": "prev",
  RESUMO: "help",
  "RESUMO-PEDIDO": "help",
};

/** As regras que encaminham e que o design não desenhou: o pedido e a pendência no mesmo tom. */
export const CASOS_FORA_DO_DESIGN: Readonly<Record<string, { readonly req: Traducao; readonly pend: Traducao }>> = {
  "POL-HUM-02": {
    req: E("Dispute above the simulated limit", "Impugnación por encima del límite simulado", "Contestação acima do limite simulado"),
    pend: E("Review the dispute by hand", "Revisar la impugnación a mano", "Revisar a contestação manualmente"),
  },
  "POL-HUM-04": {
    req: E("Night or high-value purchase", "Compra de noche o de valor alto", "Compra à noite ou de valor alto"),
    pend: E("Review the dispute by hand", "Revisar la impugnación a mano", "Revisar a contestação manualmente"),
  },
  "POL-SEG-01": {
    req: E("Large transfer to verify", "Transferencia grande para verificar", "Transferência alta para verificar"),
    pend: E("Verify the transfer with the customer", "Verificar la transferencia con el cliente", "Verificar a transferência com o cliente"),
  },
  "POL-DISP-02": {
    req: E("Dispute of a declined purchase", "Impugnación de una compra rechazada", "Contestação de uma compra recusada"),
    pend: E("Explain the decline and review it", "Explicar el rechazo y revisarlo", "Explicar a recusa e revisá-la"),
  },
  "POL-CON-04": {
    req: E("Decline without a recorded reason", "Rechazo sin motivo registrado", "Recusa sem motivo registrado"),
    pend: E("Find out why it was declined", "Averiguar por qué se rechazó", "Descobrir por que foi recusada"),
  },
};

/** As ações tentadas que o caso traz, com o rótulo do design quando ele tem um. */
export type ChaveDeAcao = keyof Textos["act"];
export const ACAO_DO_CASO: Readonly<Record<string, ChaveDeAcao>> = {
  bloquear_cartao: "block",
  desbloquear_cartao: "unblock",
  humano: "handoff",
  encaminhar: "handoff",
  esclarecer: "clarify",
  registrar_pre_caso: "record",
  propor_pre_caso: "propose",
};
export const ACOES_FORA_DO_DESIGN: Readonly<Record<string, Traducao>> = {
  interpretar: E("read the message", "leer el mensaje", "ler a mensagem"),
  identificar_transacao: E("find the transaction", "identificar la transacción", "identificar a transação"),
  avaliar_contestacao: E("evaluate the dispute", "evaluar la impugnación", "avaliar a contestação"),
  avaliar_bloqueio: E("evaluate the block", "evaluar el bloqueo", "avaliar o bloqueio"),
  avaliar_desbloqueio: E("evaluate the unblock", "evaluar el desbloqueo", "avaliar o desbloqueio"),
  consultar_situacao: E("check the transaction", "consultar la transacción", "consultar a transação"),
};

/** O desbloqueio anotado no caso (bloqueio.desfazer) diz qual bloqueio saiu e quem o desfez: o
 * atendente vê que o cliente já desfez o bloqueio do relato. */
export const DESFEITO = /^(BL-\d+): desfeito pelo (cliente|atendente)$/;
export const DESFEITO_POR: Readonly<Record<string, Traducao>> = {
  cliente: E("undone by the customer", "deshecho por el cliente", "desfeito pelo cliente"),
  atendente: E("undone by the agent", "deshecho por el agente", "desfeito pelo atendente"),
};

/** A ação de cada turno, nos rótulos do design (os últimos eventos da Operação). */
const ACAO_DO_TURNO: Readonly<Record<string, ChaveDeAcao>> = {
  responder: "read",
  esclarecer: "clarify",
  recusar: "none",
  humano: "handoff",
  oferecer_humano: "offer",
  propor_pre_caso: "propose",
  registrar_pre_caso: "record",
  bloquear_cartao: "block",
  desbloquear_cartao: "unblock",
  aguardar_humano: "handoff",
  encerrada: "none",
};
/** O bloqueio da POL-BLQ-01 é o preventivo; sem rótulo no design, a ação fica como veio. */
export function acaoDoTurno(acao: string | null | undefined, regra: string | null | undefined): ChaveDeAcao | undefined {
  if (acao === "bloquear_cartao" && regra === "POL-BLQ-01") return "blockPrev";
  return acao ? ACAO_DO_TURNO[acao] : undefined;
}

/** O efeito de um turno pelo id que ele criou (pré-caso, caso, bloqueio ou proposta); o desbloqueio
 * traz o id do bloqueio que desfez. */
export type ChaveDeEfeito = keyof Textos["eff"];
export function efeitoDoTurno(acao: string | null | undefined, efeito: string | null | undefined): ChaveDeEfeito {
  if (!efeito) return "none";
  if (acao === "desbloquear_cartao") return "unblocked";
  if (efeito.startsWith("PC-")) return "recorded";
  if (efeito.startsWith("AT-")) return "queued";
  if (efeito.startsWith("BL-")) return "blocked";
  return "wait";
}

export const CONSOLE = {
  carregando: E("Loading…", "Cargando…", "Carregando…"),
  indisponivel: E("Unavailable.", "No disponible.", "Indisponível."),
  naoAssumido: E("Could not take this case.", "No se pudo asumir el caso.", "Não foi possível assumir o caso."),
  naoDesbloqueado: E("Could not unblock this card.", "No se pudo desbloquear la tarjeta.", "Não foi possível desbloquear o cartão."),
};

export const OPERACAO = {
  // O banco fora do "ready" (o "ok" usa o t.ops.ok do design).
  banco: {
    unreachable: E("unreachable", "inaccesible", "inacessível"),
    not_migrated: E("not migrated", "sin migraciones", "sem migrations"),
    reloading: E("reloading", "recargando", "recarregando"),
  } as Readonly<Record<string, Traducao>>,
  // O título da qualidade diz a origem real dos dados: o design fala da fixture sintética, mas a
  // publicação roda com a base do desafio.
  qualidadeDaBase: E("Data quality · challenge dataset", "Calidad de datos · base del desafío", "Qualidade dos dados · base do desafio"),
  naoFecha: E("raw ≠ curated + quarantine + copies in", "raw ≠ curados + cuarentena + copias en", "raw ≠ curados + quarentena + cópias em"),
  semCarga: E("No load recorded yet.", "Aún no hay carga registrada.", "Nenhuma carga registrada ainda."),
  semDados: E("no data loaded", "sin datos cargados", "nenhum dado carregado"),
  // A versão recusada na recarga, com o motivo, e a que segue no ar.
  segue: E("still serving", "sigue la", "segue a"),
  eda: E("Why this flow · from the data", "Por qué este flujo · en los datos", "Por que este fluxo · nos dados"),
  edaNota: E(
    "Numbers from the loaded dataset, each with the query that produced it. They describe the data, not the effect of the system.",
    "Números de la base cargada, cada uno con la consulta que lo produjo. Describen los datos, no el efecto del sistema.",
    "Números da base carregada, cada um com a consulta que o produziu. Eles descrevem os dados, não o efeito do sistema.",
  ),
  edaCalculando: E("Computing the indicators…", "Calculando los indicadores…", "Calculando os indicadores…"),
  edaGrupo: E("group", "grupo", "grupo"),
  edaRegistros: E("records", "registros", "registros"),
  edaParticipacao: E("share", "participación", "participação"),
  edaParticipacaoEm: E("share of", "participación en", "participação em"),
  edaResolvidos: E("solved", "resueltos", "resolvidos"),
  edaTaxa: E("rate", "tasa", "taxa"),
  edaDe: E("of", "de", "de"),
  consulta: E("The query", "La consulta", "A consulta"),
};
