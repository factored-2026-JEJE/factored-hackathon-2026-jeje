// Ajudantes das jornadas E2E: sessão pela API real e escolha de transações sem disputa entre os
// testes que rodam em paralelo contra o mesmo banco.
import { expect, type APIRequestContext, type TestInfo } from "@playwright/test";

export type Persona = { customer_id: string; nome: string };
export type Transacao = {
  transaction_id: string;
  transaction_date: string;
  amount: string;
  currency: string;
  merchant_name: string | null;
  transaction_status: string;
  response_code: string | null;
};

export const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

export async function personas(request: APIRequestContext): Promise<Persona[]> {
  const resposta = await request.get("/api/personas");
  expect(resposta.status()).toBe(200);
  return resposta.json();
}

export async function sessao(request: APIRequestContext, customerId: string): Promise<string> {
  const resposta = await request.post("/api/sessoes", { data: { customer_id: customerId } });
  expect(resposta.status()).toBe(201);
  return (await resposta.json()).token;
}

export async function transacoes(request: APIRequestContext, token: string, limite = 100): Promise<Transacao[]> {
  const resposta = await request.get(`/api/minhas/transacoes?limite=${limite}`, { headers: auth(token) });
  expect(resposta.status()).toBe(200);
  return resposta.json();
}

// Quem registra pré-caso nos E2E; cada um × cada navegador contesta só transações da sua parte.
const CONSUMIDORES = ["pre_caso", "conversa-es", "conversa-pt"] as const;

/**
 * Transação que a política deixa contestar agora (POL-DISP-01), numa partição estável por
 * consumidor e navegador. Já contestadas (POL-DISP-03) seguem contando na partição, para que quem
 * confirmar primeiro não desloque a escolha dos outros. `aceita` filtra dentro da própria parte.
 */
export async function elegivel(
  request: APIRequestContext,
  consumidor: (typeof CONSUMIDORES)[number],
  info: TestInfo,
  aceita: (t: Transacao, doCliente: Transacao[]) => boolean = () => true,
) {
  const projetos = info.config.projects.map((p) => p.name);
  const partes = projetos.length * CONSUMIDORES.length;
  const parte = CONSUMIDORES.indexOf(consumidor) * projetos.length + projetos.indexOf(info.project.name);
  let posicao = 0;
  for (const persona of await personas(request)) {
    const token = await sessao(request, persona.customer_id);
    const doCliente = await transacoes(request, token);
    for (const t of doCliente.slice(0, 20)) {
      const url = `/api/minhas/transacoes/${t.transaction_id}/contestacao`;
      const { regra } = await (await request.get(url, { headers: auth(token) })).json();
      if (regra !== "POL-DISP-01" && regra !== "POL-DISP-03") continue;
      if (posicao++ % partes === parte && regra === "POL-DISP-01" && aceita(t, doCliente)) {
        return { persona, transacao: t, token };
      }
    }
  }
  throw new Error(`nenhuma transação elegível para ${consumidor} em ${info.project.name}`);
}

/** Valor como nas respostas do atendimento: milhar com ponto, sempre duas casas com vírgula. */
export function valorTexto(amount: string): string {
  const [inteiro = "0", centavos = "00"] = Number(amount).toFixed(2).split(".");
  return `${inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${centavos}`;
}

/** dd/mm/aaaa da data da transação (sem fuso: a base guarda o horário local da transação). */
export function dataTexto(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

/** Descrição da transação como o atendimento a mostra (fatos da API, na língua da conversa). */
export function descricao(t: Transacao, idioma: "es" | "pt"): string {
  const onde = t.merchant_name ? `${idioma === "es" ? "en" : "em"} ${t.merchant_name}` : t.transaction_id;
  return `${onde} de ${t.currency} ${valorTexto(t.amount)} (${dataTexto(t.transaction_date)})`;
}
