// Acesso de teste e área do cliente contra um servidor mínimo na fronteira de rede: as transações
// só saem com o token emitido pelo POST /api/sessoes. A integração real é conferida no E2E.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Transacao } from "./api/cliente";
import { SessaoProvider } from "./app/sessao";
import { Atendimento } from "./Atendimento";

// A sessão é do app inteiro (app/sessao.tsx): o acesso e a área do cliente vivem dentro dela.
const comSessao = () => (
  <SessaoProvider>
    <Atendimento />
  </SessaoProvider>
);

const ANA = {
  customer_id: "CLI-C",
  nome: "Ana Souza",
  cartoes_bloqueaveis: 2,
  transacoes_recusadas: 3,
  pre_casos_recentes: 1,
  contestaveis: 4,
  exemplo: { valor: "1234.5", moeda: "USD", data: "2025-03-07" },
};
const TRANSACOES: Transacao[] = [
  {
    transaction_id: "TRX-C1",
    transaction_date: "2025-03-10T14:09:12",
    amount: "189900.55",
    currency: "COP",
    transaction_status: "Declined",
    response_code: "51",
    transaction_type: "Purchase",
    merchant_name: "Almacenes Éxito",
    channel: "POS",
  },
];

function servidor({ tokenValido = true } = {}) {
  const emitido = "tok-ana";
  let valido = tokenValido;
  const pedidos: { url: string; auth: string | null }[] = [];
  const dispositivos: string[] = [];
  const perguntas: string[] = [];
  let dispositivo = "novo";
  const responder = (status: number, corpo: unknown) =>
    new Response(JSON.stringify(corpo), { status });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const auth = new Headers(init?.headers).get("Authorization");
      pedidos.push({ url, auth });
      if (url === "/api/personas") return responder(200, [ANA]);
      if (url === "/api/sessoes" && init?.method === "POST") {
        const corpo = JSON.parse(String(init.body));
        if (corpo.customer_id !== ANA.customer_id) return responder(404, { detail: "Persona não encontrada" });
        dispositivos.push(corpo.dispositivo);
        dispositivo = corpo.dispositivo ?? "novo";
        return responder(201, { token: emitido, expira_em: "2099-01-01T00:00:00Z", cliente: ANA, dispositivo });
      }
      if (auth !== `Bearer ${emitido}` || !valido) return responder(401, { detail: "Sessão ausente" });
      if (url === "/api/sessao") return responder(200, { ...ANA, dispositivo });
      if (url === "/api/minhas/transacoes") return responder(200, TRANSACOES);
      if (url === "/api/conversas" && init?.method === "POST") {
        const { idioma } = JSON.parse(String(init.body));
        return responder(201, { conversa_id: "C1", idioma, estado: "livre", resposta: "Hola." });
      }
      if (url === "/api/conversas/C1/turnos" && init?.method === "POST") {
        perguntas.push(JSON.parse(String(init.body)).texto);
        return responder(200, {
          conversa_id: "C1", numero: 1, idioma: "es", intencao: "consultar", regra: "POL-CON-03",
          acao: "responder", estado: "livre", resposta: "respondido", transaction_id: "TRX-C1",
          opcoes: [], proposta: null, protocolo: null, atendimento: null, bloqueio: null,
          descricao: null, interpretacao: "regras", efeito: null, fontes: [],
        });
      }
      return responder(404, { detail: "Not Found" });
    }),
  );
  return { pedidos, dispositivos, perguntas, invalidar: () => (valido = false) };
}

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.unstubAllGlobals());

test("entrar como persona abre sessão e mostra só as transações dela", async () => {
  servidor();
  render(comSessao());
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza" }));
  expect(await screen.findByRole("heading", { name: "Olá, Ana Souza" })).toBeInTheDocument();
  const linha = within(await screen.findByRole("row", { name: /Almacenes Éxito/ }));
  expect(linha.getByText("Recusada")).toBeInTheDocument();
  expect(linha.getByText("COP 189.900,55")).toBeInTheDocument();
});

test("cada persona traz quantas contestáveis tem e a frase pronta com uma compra dela", async () => {
  // DEV-073: o exemplo do guia é da própria persona, não uma transação da fixture.
  servidor();
  render(comSessao());
  expect(await screen.findByText(/contestáveis: 4/)).toBeInTheDocument();
  expect(screen.getByText("No reconozco el cobro de 1.234,50 del 07/03")).toBeInTheDocument();
  expect(screen.getByText("Não reconheço a cobrança de 1.234,50 do dia 07/03")).toBeInTheDocument();
});

test("pede as transações com o token emitido e nunca com o id do cliente", async () => {
  const { pedidos } = servidor();
  render(comSessao());
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza" }));
  await screen.findByRole("row", { name: /Almacenes Éxito/ });
  const lista = pedidos.find((p) => p.url === "/api/minhas/transacoes");
  expect(lista?.auth).toBe("Bearer tok-ana");
  expect(pedidos.every((p) => !p.url.includes("CLI-C"))).toBe(true);
});

test("sessão expirada volta para o acesso com aviso", async () => {
  const api = servidor();
  render(comSessao());
  api.invalidar();
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Sua sessão expirou");
  expect(screen.getByRole("heading", { name: "Acesso de teste" })).toBeInTheDocument();
  expect(sessionStorage.getItem("jeje.sessao")).toBeNull();
});

test("sair apaga a sessão guardada", async () => {
  servidor();
  render(comSessao());
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza" }));
  await screen.findByRole("heading", { name: "Olá, Ana Souza" });
  expect(sessionStorage.getItem("jeje.sessao")).toBe("tok-ana");
  await userEvent.click(screen.getByRole("button", { name: "Sair" }));
  expect(await screen.findByRole("heading", { name: "Acesso de teste" })).toBeInTheDocument();
  expect(sessionStorage.getItem("jeje.sessao")).toBeNull();
});

test("recarregar a página com sessão guardada volta direto para o cliente", async () => {
  servidor();
  sessionStorage.setItem("jeje.sessao", "tok-ana");
  render(comSessao());
  expect(await screen.findByRole("heading", { name: "Olá, Ana Souza" })).toBeInTheDocument();
});

test("o dispositivo simulado é escolhido no acesso: sem escolha vai novo, e a sessão mostra o escolhido", async () => {
  const { dispositivos } = servidor();
  render(comSessao());
  const grupo = await screen.findByRole("radiogroup", { name: "Dispositivo (simulação)" });
  expect(within(grupo).getByRole("radio", { name: "Novo" })).toBeChecked();
  await userEvent.click(screen.getByRole("button", { name: "Entrar como Ana Souza" }));
  expect(await screen.findByText("Dispositivo (simulação): novo")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Sair" }));
  await userEvent.click(await screen.findByRole("radio", { name: "Cadastrado" }));
  await userEvent.click(screen.getByRole("button", { name: "Entrar como Ana Souza" }));
  expect(await screen.findByText("Dispositivo (simulação): cadastrado")).toBeInTheDocument();
  expect(dispositivos).toEqual(["novo", "cadastrado"]);
});

test("recarregar a página mostra o dispositivo guardado pelo servidor", async () => {
  servidor();
  render(comSessao());
  await userEvent.click(await screen.findByRole("radio", { name: "Cadastrado" }));
  await userEvent.click(screen.getByRole("button", { name: "Entrar como Ana Souza" }));
  await screen.findByText("Dispositivo (simulação): cadastrado");
  cleanup();
  render(comSessao());
  expect(await screen.findByText("Dispositivo (simulação): cadastrado")).toBeInTheDocument();
});

async function perguntarSobreALinha(abrir: string) {
  const api = servidor();
  render(comSessao());
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza" }));
  const linha = within(await screen.findByRole("row", { name: /Almacenes Éxito/ }));
  // Sem conversa aberta, não há a quem perguntar.
  expect(linha.queryByRole("button", { name: "Perguntar sobre esta" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: abrir }));
  await userEvent.click(await linha.findByRole("button", { name: "Perguntar sobre esta" }));
  expect(await screen.findByText("respondido")).toBeInTheDocument();
  return api.perguntas;
}

test("perguntar sobre esta manda à conversa em espanhol as pistas da linha, nunca o identificador", async () => {
  expect(await perguntarSobreALinha("Conversar em español")).toEqual([
    "¿Qué pasó con la transacción de 189.900,55 del 10/03/2025 en Almacenes Éxito?",
  ]);
});

test("perguntar sobre esta manda à conversa em português as pistas da linha", async () => {
  expect(await perguntarSobreALinha("Conversar em português")).toEqual([
    "O que aconteceu com a transação de 189.900,55 do dia 10/03/2025 na Almacenes Éxito?",
  ]);
});

test("cada persona mostra as dicas para escolher o caminho da demonstração", async () => {
  servidor();
  render(comSessao());
  const item = (await screen.findByRole("button", { name: "Entrar como Ana Souza" })).closest("li");
  expect(item).toHaveTextContent("cartões para bloquear: 2 · recusas: 3 · pré-casos recentes: 1");
});
