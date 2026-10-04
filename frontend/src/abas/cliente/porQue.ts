// As linhas do "Por que esta resposta?" do app (DEV-032b), as do design (ui.rc), lidas do turno da API
// e na língua da interface: o X-Request-ID, a língua, quem leu, a intenção, como a transação foi achada,
// a regra e o que ela quer dizer, a ação, o efeito, o protocolo, o arquivo e a linha do recibo e a
// versão dos dados. No turno reaberto pelo histórico, a API guarda só a regra e a ação.
import type { TurnoComRequisicao } from "../../api/cliente";
import type { Lingua, Textos } from "../../app/conteudo";
import { transacaoDoTurno } from "../../porQueDoTurno";
import { CONTEUDO } from "../../site/conteudo";

export interface Motivo {
  readonly regra: string;
  readonly acao: string;
  readonly turno?: TurnoComRequisicao;
}

// Os rótulos do design para os códigos da API; um código sem rótulo aparece como veio.
const INTENCAO: Readonly<Record<string, keyof Textos["int"]>> = {
  fraude: "fraud",
  bloquear: "block",
  desbloquear: "unblock",
  humano: "agent",
  fora_de_escopo: "scope",
  contestar: "dispute",
  consultar: "consult",
  desconhecida: "unknown",
};
const ACAO: Readonly<Record<string, keyof Textos["act"]>> = {
  responder: "read",
  esclarecer: "clarify",
  propor_pre_caso: "propose",
  registrar_pre_caso: "record",
  humano: "handoff",
  oferecer_humano: "offer",
  recusar: "none",
  bloquear_cartao: "block",
  propor_desbloqueio: "askYes",
  desbloquear_cartao: "unblock",
  encerrada: "none",
};
const EFEITO: Readonly<Record<string, keyof Textos["eff"]>> = {
  registrar_pre_caso: "recorded",
  humano: "queued",
  bloquear_cartao: "blocked",
  desbloquear_cartao: "unblocked",
  propor_pre_caso: "wait",
  propor_desbloqueio: "wait",
};

const rotulo = <K extends string>(mapa: Readonly<Record<string, K>>, textos: Readonly<Record<K, string>>, codigo: string) => {
  const chave = mapa[codigo];
  return chave ? textos[chave] : codigo;
};

/** Quem leu a mensagem: as regras, as regras com o leitor abaixo do limite, ou o modelo que leu. */
export function quemLeu(interpretacao: string, t: Textos): string {
  if (interpretacao === "regras") return t.rd.rules;
  if (interpretacao.includes("abaixo do limite")) return `${t.rd.rules} (${t.rd.below})`;
  return interpretacao;
}

/** O que a regra quer dizer, na língua da interface (a lista do site); sem ela, a descrição da API. */
export function significado(regra: string, lingua: Lingua, descricao?: string | null): string {
  const chave = regra.startsWith("POL-CASO") ? "POL-CASO-01–03" : regra;
  const achada = CONTEUDO.rules.list.find(([id]) => id === chave);
  return achada ? achada[2][lingua] : (descricao ?? "—");
}

// A garantia da escolha pelo ranking (DEV-037a, PRD-012): a probabilidade, quantas podiam ser e a
// versão da calibração (backend/src/jeje/qual_transacao.json), como o app mostrava antes do design.
const RANKING: Readonly<Record<Lingua, { readonly p: string; readonly possiveis: string; readonly calibracao: string; readonly decimal: string }>> = {
  en: { p: "probability", possiveis: "candidates", calibracao: "calibration", decimal: "." },
  es: { p: "probabilidad", possiveis: "posibles", calibracao: "calibración", decimal: "," },
  pt: { p: "probabilidade", possiveis: "possíveis", calibracao: "calibração", decimal: "," },
};

function detalheDoRanking(tr: TurnoComRequisicao, lingua: Lingua): string {
  const r = tr.resolucao;
  if (!r || r.resolvedor !== "ranking") return "";
  const L = RANKING[lingua];
  const p = r.probabilidade === null ? "" : ` · ${L.p} ${r.probabilidade.toFixed(2).replace(".", L.decimal)}`;
  return `${p} · ${r.possiveis ?? "?"} ${L.possiveis} · ${L.calibracao} ${r.calibracao ?? "?"}`;
}

export function linhasDoPorQue(
  motivo: Motivo,
  t: Textos,
  lingua: Lingua,
  versaoCarregada: string | null = null,
): (readonly [string, string])[] {
  const tr = motivo.turno;
  if (!tr) {
    return [
      [t.rc.rule, motivo.regra],
      [t.rc.meaning, significado(motivo.regra, lingua)],
      [t.rc.action, rotulo(ACAO, t.act, motivo.acao)],
    ];
  }
  const linhas: (readonly [string, string])[] = [
    [t.rc.rid, tr.requestId ?? "—"],
    [t.rc.lang, tr.idioma],
    [t.rc.reader, quemLeu(tr.interpretacao, t)],
    [t.rc.intent, rotulo(INTENCAO, t.int, tr.intencao)],
  ];
  const transacao = transacaoDoTurno(tr, lingua);
  if (transacao) linhas.push([t.rc.txn, transacao + detalheDoRanking(tr, lingua)]);
  const efeito = t.eff[EFEITO[tr.acao] ?? "none"] + (tr.efeito ? ` · ${tr.efeito}` : "");
  linhas.push(
    [t.rc.rule, tr.regra],
    [t.rc.meaning, significado(tr.regra, lingua, tr.descricao)],
    [t.rc.action, rotulo(ACAO, t.act, tr.acao)],
    [t.rc.effect, efeito],
  );
  if (tr.protocolo) linhas.push([t.rc.protocol, tr.protocolo]);
  if (tr.recibo) linhas.push([t.rc.file, tr.recibo.arquivo], [t.rc.line, String(tr.recibo.linha)]);
  // A versão do fato quando há recibo; sem ele (uma pergunta, um encaminhamento), a do conjunto carregado
  // na API (/health/ready), como o design mostra em toda resposta.
  linhas.push([t.rc.version, (tr.recibo?.versao_dos_dados ?? versaoCarregada)?.slice(0, 12) ?? "—"]);
  return linhas;
}
