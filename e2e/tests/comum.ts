// Ajudantes das jornadas E2E: sessão pela API real e escolha de transações sem disputa entre os
// testes que rodam em paralelo contra o mesmo banco.
import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

export type Persona = { customer_id: string; nome: string };
export type Transacao = {
  transaction_id: string;
  transaction_date: string;
  amount: string;
  currency: string;
  merchant_name: string | null;
  transaction_status: string;
  response_code: string | null;
  transaction_type: string | null;
  channel: string | null;
};

// Limites do compose (PRD-001 e PRD-008), reescritos aqui como oráculo independente do código da
// política. A reincidência vale 3 no compose.yaml; nas stacks da fixture (compose.ci.yaml) ela sobe
// para 10, e o oráculo só aceita POL-HUM-06 quando a persona tem pré-casos recentes suficientes.
export const LIMITES = {
  padrao: 5000, noturno: 1000, seguranca: 50000, canais: ["App", "Web"], inicio: 20, fim: 6,
  janelaDias: 120, reincidencia: 3, reincidenciaDias: 30,
};

/** Dias entre duas datas ISO (só a parte da data). */
export function diasEntre(de: string, ate: string): number {
  return Math.round((Date.parse(ate.slice(0, 10)) - Date.parse(de.slice(0, 10))) / 86_400_000);
}

/** Feita à noite (20h–6h, horário local da transação) por celular ou computador. */
export function noturnaDigital(t: Transacao): boolean {
  const hora = Number(t.transaction_date.slice(11, 13));
  return LIMITES.canais.includes(t.channel ?? "") && (hora >= LIMITES.inicio || hora < LIMITES.fim);
}

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
 * confirmar primeiro não desloque a escolha dos outros. Noturnas digitais ficam de fora: o limite
 * do dia (POL-HUM-04) pode tirá-las da lista no meio da execução, quando outro teste registra um
 * pré-caso do mesmo cliente. `aceita` filtra dentro da própria parte.
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
      if (noturnaDigital(t)) continue;
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

// A aba do cliente do design de 03/10 (DEV-032b). As jornadas abrem o app na língua da conversa
// (?lang=es ou pt): os rótulos do design ficam previsíveis. Os textos estão aqui como oráculo.
export const UI = {
  es: {
    entrar: (nome: string) => `Entrar como ${nome} →`,
    caixa: "Escribe como cliente, en español o portugués",
    enviar: "Enviar",
    opcoes: "Opciones",
    atalhos: "Atajos",
    conversa: "Conversación",
    humano: "Pasado a una persona",
    recebido: "pre-caso recibido",
    pedidos: "Mis solicitudes",
    transacoes: "Mis transacciones",
    cadastrado: "Dispositivo registrado",
    novo: "Dispositivo nuevo",
    agente: "Agente",
    cliente: "Cliente",
    nova: "Nueva conversación",
    reenviar: "Reenviar",
    perguntar: "Preguntar por esta →",
    paineis: ["Chat", "Transacciones", "Solicitudes · tarjetas"],
  },
  pt: {
    entrar: (nome: string) => `Entrar como ${nome} →`,
    caixa: "Escreva como cliente, em espanhol ou português",
    enviar: "Enviar",
    opcoes: "Opções",
    atalhos: "Atalhos",
    conversa: "Conversa",
    humano: "Passado para uma pessoa",
    recebido: "pré-caso recebido",
    pedidos: "Meus pedidos",
    transacoes: "Minhas transações",
    cadastrado: "Dispositivo cadastrado",
    novo: "Dispositivo novo",
    agente: "Atendente",
    cliente: "Cliente",
    nova: "Nova conversa",
    reenviar: "Reenviar",
    perguntar: "Perguntar sobre esta →",
    paineis: ["Conversa", "Transações", "Pedidos · cartões"],
  },
} as const;

/** Entra pela tela de acesso do design: o cartão da persona, o dispositivo e o "Entrar como". */
export async function entrarPeloAcesso(page: Page, nome: string, idioma: "es" | "pt", dispositivo: "cadastrado" | "novo" = "cadastrado") {
  const u = UI[idioma];
  await page.goto(`/?lang=${idioma}#cliente`);
  await page.locator(".acc-persona").filter({ hasText: nome }).first().click();
  await page.getByRole("button", { name: dispositivo === "cadastrado" ? u.cadastrado : u.novo }).click();
  await page.getByRole("button", { name: u.entrar(nome), exact: true }).click();
  await expect(page.getByRole("region", { name: u.transacoes })).toBeAttached();
}

/** As falas da conversa (as do cliente e as do assistente), sem o "lendo…" de passagem. */
export const falasDaConversa = (page: Page) => page.getByRole("log").locator(".conv-falas > li:not(.conv-lendo)");

/** Escreve e envia como o cliente; devolve a resposta do assistente, depois que ela chega. */
export async function dizerNaConversa(page: Page, texto: string, idioma: "es" | "pt") {
  const u = UI[idioma];
  const falas = falasDaConversa(page);
  const antes = await falas.count();
  await page.getByLabel(u.caixa).fill(texto);
  await page.getByRole("button", { name: u.enviar, exact: true }).click();
  await expect(falas).toHaveCount(antes + 2);
  return falas.last();
}
