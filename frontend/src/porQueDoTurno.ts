// Como a transação do turno foi achada (o rastro do resolvedor, DEV-071 e DEV-037), nos três idiomas:
// o "Por que esta resposta?" do site e o do app mostram o mesmo rastro, lido do turno da API.
import type { ResultadoDoTurno } from "./api/cliente";

type Lingua = "pt" | "es" | "en";
type Texto = Readonly<Record<Lingua, string>>;

export const COMO_ACHOU: Readonly<Record<"possiveis" | "filtro" | "ranking" | "semGarantia" | "escolha" | "foco", Texto>> = {
  possiveis: { pt: "possíveis · pergunta qual", es: "posibles · pregunta cuál", en: "candidates · asks which" },
  filtro: { pt: "filtro exato", es: "filtro exacto", en: "exact filter" },
  ranking: { pt: "ranking com garantia (α = 5%)", es: "ranking con garantía (α = 5%)", en: "ranking with a guarantee (α = 5%)" },
  semGarantia: {
    pt: "ranking sem garantia: mostra as possíveis",
    es: "ranking sin garantía: muestra las posibles",
    en: "ranking without a guarantee: shows candidates",
  },
  escolha: { pt: "escolhida pelo cliente", es: "elegida por el cliente", en: "chosen by the customer" },
  foco: { pt: "a da proposta", es: "la de la propuesta", en: "the proposed one" },
};

/** O rastro da transação do turno: as possíveis (a API perguntou qual), o resolvedor que achou, ou o id. */
export function transacaoDoTurno(
  turno: Pick<ResultadoDoTurno, "opcoes" | "resolucao" | "transaction_id">,
  lingua: Lingua,
): string | null {
  const res = turno.resolucao;
  if (turno.opcoes.length > 0) return turno.opcoes.length + " " + COMO_ACHOU.possiveis[lingua];
  if (res) {
    if (res.resolvedor === "ranking") return (turno.transaction_id ? COMO_ACHOU.ranking : COMO_ACHOU.semGarantia)[lingua];
    return COMO_ACHOU[res.resolvedor][lingua];
  }
  return turno.transaction_id ?? null;
}
