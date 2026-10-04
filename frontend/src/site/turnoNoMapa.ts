// O caminho de um turno da conversa no mapa (DEV-032a), "o mapa que acende" do design: quem leu a
// mensagem, se houve uma transação a achar, se a política agiu e se o caso passou para uma pessoa.
// No exemplo roteirizado do design, as rotas vêm das jornadas (nosDaRota); aqui, do turno de verdade.
import type { ResultadoDoTurno } from "../api/cliente";
import { IDS_DOS_NOS, MENSAGEM, nosDaRota, type IdDoNo, type TipoDeRota } from "./mapa";

/** Quem leu a mensagem: as regras, o leitor e5 (decidindo ou abaixo do limite) ou o LLM. */
export type Leitura = "regras" | "leitor" | "llm";

export interface CaminhoDoTurno {
  readonly nos: readonly IdDoNo[];
  readonly humano: boolean;
  readonly leitura: Leitura;
}

// Ações que chegam ao componente Ação do mapa (consulta, pré-caso, bloqueio, atendente). Perguntar,
// oferecer o atendente, recusar e pedir o "sim" do desbloqueio não agem, como nas rotas do design.
const AGEM = new Set(["responder", "consultar", "propor_pre_caso", "registrar_pre_caso", "humano", "bloquear_cartao", "desbloquear_cartao"]);

/** O campo `interpretacao` do turno: "regras", "leitor:e5@…", "regras (leitor abaixo do limite)" ou "ollama:<modelo>". */
export function leituraDe(interpretacao: string): Leitura {
  if (interpretacao.startsWith("ollama:")) return "llm";
  return interpretacao.includes("leitor") ? "leitor" : "regras";
}

type Turno = Pick<ResultadoDoTurno, "acao" | "interpretacao" | "transaction_id" | "resolucao" | "opcoes" | "atendimento" | "estado">;

export function caminhoDoTurno(t: Turno): CaminhoDoTurno {
  const leitura = leituraDe(t.interpretacao);
  const achouTransacao = t.transaction_id != null || t.resolucao != null || t.opcoes.length > 0;
  const agiu = AGEM.has(t.acao);
  const nos: IdDoNo[] = MENSAGEM.filter((id) => (id !== "qual" || achouTransacao) && (id !== "acoes" || agiu));
  if (leitura !== "regras") nos.push("leitor");
  if (leitura === "llm") nos.push("llm");
  return { nos, humano: t.acao === "humano" || t.atendimento != null || t.estado === "com_humano", leitura };
}

/** O caminho de uma jornada roteirizada do design (as rotas full, ask, act… de cada exemplo). */
export function caminhoDaJornada(rota: TipoDeRota, id: string, humano: boolean): CaminhoDoTurno {
  const nos = nosDaRota(rota, id);
  return { nos, humano, leitura: nos.includes("leitor") ? "leitor" : "regras" };
}

const ROTAS_DO_DESIGN: readonly TipoDeRota[] = ["full", "read", "ask", "act", "noact", "reader"];

/**
 * O caminho que chega pelo jeje-turn do app aberto na janela do site: a lista dos nós de verdade do turno
 * (o que o app manda) ou um tipo de rota do design. Qualquer outra coisa (nó que não existe, rota
 * desconhecida, lista vazia) é ignorada: o nosDaRota não tem reserva.
 */
export function caminhoRecebido(rota: unknown, humano: boolean, leitura: unknown): CaminhoDoTurno | null {
  if (Array.isArray(rota)) {
    const nos = rota.filter((id): id is IdDoNo => typeof id === "string" && (IDS_DOS_NOS as readonly string[]).includes(id));
    if (nos.length === 0 || nos.length !== rota.length) return null;
    return { nos, humano, leitura: leitura === "llm" || leitura === "leitor" ? leitura : "regras" };
  }
  if (typeof rota === "string" && (ROTAS_DO_DESIGN as readonly string[]).includes(rota)) {
    return caminhoDaJornada(rota as TipoDeRota, "", humano);
  }
  return null;
}
