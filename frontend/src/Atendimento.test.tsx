// Acesso de teste e área do cliente contra um servidor mínimo na fronteira de rede: as transações
// só saem com o token emitido pelo POST /api/sessoes. A integração real é conferida no E2E.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Transacao } from "./api/cliente";
import { Atendimento } from "./Atendimento";

const ANA = { customer_id: "CLI-C", nome: "Ana Souza" };
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
      return responder(404, { detail: "Not Found" });
    }),
  );
  return { pedidos, dispositivos, invalidar: () => (valido = false) };
}

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.unstubAllGlobals());

test("entrar como persona abre sessão e mostra só as transações dela", async () => {
  servidor();
  render(<Atendimento />);
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza" }));
  expect(await screen.findByRole("heading", { name: "Olá, Ana Souza" })).toBeInTheDocument();
  const linha = within(await screen.findByRole("row", { name: /Almacenes Éxito/ }));
  expect(linha.getByText("Recusada")).toBeInTheDocument();
  expect(linha.getByText("COP 189.900,55")).toBeInTheDocument();
});

test("pede as transações com o token emitido e nunca com o id do cliente", async () => {
  const { pedidos } = servidor();
  render(<Atendimento />);
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza" }));
  await screen.findByRole("row", { name: /Almacenes Éxito/ });
  const lista = pedidos.find((p) => p.url === "/api/minhas/transacoes");
  expect(lista?.auth).toBe("Bearer tok-ana");
  expect(pedidos.every((p) => !p.url.includes("CLI-C"))).toBe(true);
});

test("sessão expirada volta para o acesso com aviso", async () => {
  const api = servidor();
  render(<Atendimento />);
  api.invalidar();
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Sua sessão expirou");
  expect(screen.getByRole("heading", { name: "Acesso de teste" })).toBeInTheDocument();
  expect(sessionStorage.getItem("jeje.sessao")).toBeNull();
});

test("sair apaga a sessão guardada", async () => {
  servidor();
  render(<Atendimento />);
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
  render(<Atendimento />);
  expect(await screen.findByRole("heading", { name: "Olá, Ana Souza" })).toBeInTheDocument();
});

test("o dispositivo simulado é escolhido no acesso: sem escolha vai novo, e a sessão mostra o escolhido", async () => {
  const { dispositivos } = servidor();
  render(<Atendimento />);
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
  render(<Atendimento />);
  await userEvent.click(await screen.findByRole("radio", { name: "Cadastrado" }));
  await userEvent.click(screen.getByRole("button", { name: "Entrar como Ana Souza" }));
  await screen.findByText("Dispositivo (simulação): cadastrado");
  cleanup();
  render(<Atendimento />);
  expect(await screen.findByText("Dispositivo (simulação): cadastrado")).toBeInTheDocument();
});
