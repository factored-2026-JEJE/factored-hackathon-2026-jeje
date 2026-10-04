// O acesso de teste e a aba do cliente do design (DEV-032b) contra um servidor mínimo na fronteira de
// rede: as transações só saem com o token emitido pelo POST /api/sessoes. A integração real é
// conferida no E2E.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CartaoDoCliente, Transacao } from "./api/cliente";
import { LinguaDoAppProvider } from "./app/LinguaDoApp";
import { SessaoProvider } from "./app/sessao";
import { Topo } from "./app/Topo";
import { Atendimento } from "./Atendimento";

// A sessão é do app inteiro (app/sessao.tsx): a barra do topo (o Leave) e a aba do cliente vivem nela.
const comSessao = () => (
  <LinguaDoAppProvider>
    <SessaoProvider>
      <Topo aba="cliente" versao={0} aoEscolher={() => {}} />
      <Atendimento />
    </SessaoProvider>
  </LinguaDoAppProvider>
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
const BIA = { ...ANA, customer_id: "CLI-D", nome: "Bia Lima", exemplo: null };
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
  {
    transaction_id: "TRX-C2",
    transaction_date: "2025-03-08T10:00:00",
    amount: "45.9",
    currency: "USD",
    transaction_status: "Approved",
    response_code: null,
    transaction_type: "Purchase",
    merchant_name: "Mercado Sol",
    channel: "App",
  },
];

function servidor({ tokenValido = true } = {}) {
  const emitido = "tok-ana";
  let valido = tokenValido;
  const pedidos: { url: string; auth: string | null }[] = [];
  const dispositivos: string[] = [];
  const perguntas: string[] = [];
  const idiomas: string[] = [];
  let dispositivo = "novo";
  // Os cartões da sessão (2.1): um ativo e um já bloqueado por um atendente; o pedido de bloqueio na
  // conversa bloqueia o primeiro, como a API.
  let bloqueado = false;
  const cartoes = (): CartaoDoCliente[] => [
    {
      product_id: "P-1", produto: "Visa Clásica", ultimos4: "4821", status: "Active",
      bloqueio: bloqueado ? { id: "BLQ-1", tipo: "completo", reversivel_ate: "2025-03-17T00:00:00Z" } : null,
    },
    {
      product_id: "P-2", produto: "Mastercard Oro", ultimos4: "7730", status: "Active",
      bloqueio: { id: "BLQ-2", tipo: "preventivo", reversivel_ate: "2025-03-18T00:00:00Z" },
    },
  ];
  const responder = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const auth = new Headers(init?.headers).get("Authorization");
      pedidos.push({ url, auth });
      if (url === "/api/personas") return responder(200, [ANA, BIA]);
      if (url === "/api/atendimento/fila") return responder(200, []);
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
      if (url === "/api/minhas/cartoes") return responder(200, cartoes());
      if (url === "/api/minhas/pre-casos") {
        return responder(200, [{ protocolo: "PC-00000417", transaction_id: "TRX-C2", estado: "recebido", criado_em: "2025-03-11T10:00:00Z" }]);
      }
      if (url === "/api/conversas" && init?.method === "POST") {
        const { idioma } = JSON.parse(String(init.body));
        idiomas.push(idioma);
        return responder(201, { conversa_id: "C1", idioma, estado: "livre", resposta: "Hola." });
      }
      if (url === "/api/conversas/C1/turnos" && init?.method === "POST") {
        const texto: string = JSON.parse(String(init.body)).texto;
        perguntas.push(texto);
        const bloqueia = texto.includes("bloquear");
        if (bloqueia) bloqueado = true;
        return responder(200, {
          conversa_id: "C1", numero: 1, idioma: idiomas.at(-1), intencao: bloqueia ? "bloquear" : "consultar",
          regra: bloqueia ? "POL-BLQ-02" : "POL-CON-03", acao: bloqueia ? "bloquear_cartao" : "responder",
          estado: "livre", resposta: bloqueia ? "bloqueado" : "respondido", transaction_id: bloqueia ? null : "TRX-C1",
          opcoes: [], proposta: null, protocolo: null, atendimento: null, bloqueio: null,
          descricao: null, interpretacao: "regras", efeito: null, fontes: [],
        });
      }
      return responder(404, { detail: "Not Found" });
    }),
  );
  return { pedidos, dispositivos, perguntas, idiomas, invalidar: () => (valido = false) };
}

beforeEach(() => sessionStorage.clear());
afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

const entrar = async (nome = "Ana Souza") => userEvent.click(await screen.findByRole("button", { name: `Enter as ${nome} →` }));
const transacoes = async () => screen.findByRole("region", { name: "My transactions" });

test("entrar como persona abre sessão e mostra só as transações dela", async () => {
  servidor();
  render(comSessao());
  await entrar();
  const linha = within(await transacoes()).getByText("Almacenes Éxito").closest("li");
  expect(linha).toHaveTextContent("declined · 51");
  expect(linha).toHaveTextContent("COP 189,900.55");
  expect(linha).toHaveTextContent("10/03");
  expect(screen.getByText("CLI-C · Ana Souza · registered device")).toBeInTheDocument();
});

test("cada persona traz quantas contestáveis tem e a frase pronta com uma compra dela", async () => {
  // DEV-073: o exemplo do guia é da própria persona, não uma transação da fixture.
  servidor();
  render(comSessao());
  const cartao = await screen.findByRole("button", { name: /Ana Souza/, pressed: true });
  expect(within(cartao).getByText("disputable").previousElementSibling).toHaveTextContent("4");
  expect(within(cartao).getByText("“No reconozco el cobro de 1.234,50 del 07/03”")).toBeInTheDocument();
  // Sem compra de exemplo, o cartão não tem frase.
  expect(screen.getByRole("button", { name: /Bia Lima/ })).not.toHaveTextContent("“");
});

test("pede as transações com o token emitido e nunca com o id do cliente", async () => {
  const { pedidos } = servidor();
  render(comSessao());
  await entrar();
  await within(await transacoes()).findByText("Almacenes Éxito");
  const lista = pedidos.find((p) => p.url === "/api/minhas/transacoes");
  expect(lista?.auth).toBe("Bearer tok-ana");
  expect(pedidos.every((p) => !p.url.includes("CLI-C"))).toBe(true);
});

test("sessão expirada volta para o acesso com aviso", async () => {
  const api = servidor();
  render(comSessao());
  api.invalidar();
  await entrar();
  expect(await screen.findByRole("alert")).toHaveTextContent("Your session expired");
  expect(screen.getByRole("heading", { name: "Talk to the bank about your transactions." })).toBeInTheDocument();
  expect(sessionStorage.getItem("jeje.sessao")).toBeNull();
});

test("sair apaga a sessão guardada", async () => {
  servidor();
  render(comSessao());
  await entrar();
  await transacoes();
  expect(sessionStorage.getItem("jeje.sessao")).toBe("tok-ana");
  await userEvent.click(screen.getByRole("button", { name: "Leave" }));
  expect(await screen.findByRole("heading", { name: "Talk to the bank about your transactions." })).toBeInTheDocument();
  expect(sessionStorage.getItem("jeje.sessao")).toBeNull();
});

test("recarregar a página com sessão guardada volta direto para o cliente", async () => {
  servidor();
  sessionStorage.setItem("jeje.sessao", "tok-ana");
  render(comSessao());
  expect(await transacoes()).toBeInTheDocument();
});

test("o dispositivo simulado é escolhido no acesso: sem escolha vai cadastrado, como no design, e a sessão mostra o escolhido", async () => {
  const { dispositivos } = servidor();
  render(comSessao());
  expect(await screen.findByRole("button", { name: /Registered device/, pressed: true })).toBeInTheDocument();
  await entrar();
  expect(await screen.findByText("CLI-C · Ana Souza · registered device")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Leave" }));
  await userEvent.click(await screen.findByRole("button", { name: /New device/ }));
  await entrar();
  expect(await screen.findByText("CLI-C · Ana Souza · new device")).toBeInTheDocument();
  expect(dispositivos).toEqual(["cadastrado", "novo"]);
});

test("recarregar a página mostra o dispositivo guardado pelo servidor", async () => {
  servidor();
  render(comSessao());
  await entrar();
  await screen.findByText("CLI-C · Ana Souza · registered device");
  cleanup();
  render(comSessao());
  // O dispositivo vem da sessão relida no servidor, não de um padrão da tela.
  expect(await screen.findByText("CLI-C · Ana Souza · registered device")).toBeInTheDocument();
});

async function perguntarSobreALinha() {
  const api = servidor();
  render(comSessao());
  await entrar();
  const linha = (await within(await transacoes()).findByText("Almacenes Éxito")).closest("li");
  // Sem conversa aberta, a pergunta abre uma, na língua da interface (espanhol, se não for português).
  await userEvent.click(within(linha as HTMLElement).getByRole("button", { name: "Ask about this one →" }));
  expect(await screen.findByText("respondido")).toBeInTheDocument();
  return api;
}

test("perguntar sobre esta manda à conversa em espanhol as pistas da linha, nunca o identificador", async () => {
  const api = await perguntarSobreALinha();
  expect(api.idiomas).toEqual(["es"]);
  expect(api.perguntas).toEqual(["¿Qué pasó con el cobro de 189.900,55 del 10/03 en Almacenes Éxito?"]);
});

test("perguntar sobre esta manda à conversa em português as pistas da linha", async () => {
  window.history.replaceState(null, "", "/?lang=pt");
  const api = servidor();
  render(comSessao());
  await userEvent.click(await screen.findByRole("button", { name: "Entrar como Ana Souza →" }));
  const lista = await screen.findByRole("region", { name: "Minhas transações" });
  const linha = (await within(lista).findByText("Almacenes Éxito")).closest("li");
  await userEvent.click(within(linha as HTMLElement).getByRole("button", { name: "Perguntar sobre esta →" }));
  expect(await screen.findByText("respondido")).toBeInTheDocument();
  expect(api.idiomas).toEqual(["pt"]);
  expect(api.perguntas).toEqual(["O que houve com a cobrança de 189.900,55 do dia 10/03 em Almacenes Éxito?"]);
});

test("cada persona mostra as dicas para escolher o caminho da demonstração", async () => {
  servidor();
  render(comSessao());
  const cartao = await screen.findByRole("button", { name: /Ana Souza/, pressed: true });
  const numero = (rotulo: string) => within(cartao).getByText(rotulo).previousElementSibling;
  expect(numero("cards to block")).toHaveTextContent("2");
  expect(numero("declines")).toHaveTextContent("3");
  expect(numero("recent requests")).toHaveTextContent("1");
});

test("os pedidos de revisão mostram o comércio, o valor e o dia, e a linha da transação leva o protocolo", async () => {
  servidor();
  render(comSessao());
  await entrar();
  const pedidos = await screen.findByRole("region", { name: "My requests" });
  expect(await within(pedidos).findByText("Mercado Sol · USD 45.90 · 08/03")).toBeInTheDocument();
  expect(within(pedidos).getByText("PC-00000417")).toBeInTheDocument();
  const linha = within(await transacoes()).getByText("Mercado Sol").closest("li");
  expect(linha).toHaveTextContent("PC-00000417");
});

const cartoesDaSessao = async () => screen.findByRole("region", { name: "Cards" });
const linhaDoCartao = async (final: string) => {
  const linha = (await within(await cartoesDaSessao()).findByText(`•••• ${final}`)).closest("li");
  if (!linha) throw new Error(`sem a linha do cartão ${final}`);
  return linha;
};

test("os cartões vêm da API: ativo, ou bloqueado com a etiqueta e a nota do design", async () => {
  servidor();
  render(comSessao());
  await entrar();
  const ativo = await linhaDoCartao("4821");
  expect(ativo).toHaveTextContent("Visa Clásica");
  expect(ativo).toHaveTextContent("active");
  expect(ativo.querySelector(".cartao-nota")).toBeNull();
  const preventivo = await linhaDoCartao("7730");
  expect(preventivo).toHaveTextContent("blocked · preventive");
  expect(preventivo).toHaveTextContent("An agent confirms or undoes this block.");
  expect(preventivo).toHaveAttribute("data-situacao", "preventivo");
});

test("um bloqueio pela conversa relê os cartões: o cartão sai bloqueado, com a nota de desfazer pela conversa", async () => {
  const api = servidor();
  render(comSessao());
  await entrar();
  expect(await linhaDoCartao("4821")).toHaveTextContent("active");
  await userEvent.type(screen.getByLabelText("Write as the customer, in Spanish or Portuguese"), "Quiero bloquear mi tarjeta");
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText("bloqueado")).toBeInTheDocument();
  await waitFor(async () => expect(await linhaDoCartao("4821")).toHaveTextContent("blocked · full"));
  const linha = await linhaDoCartao("4821");
  expect(linha).toHaveTextContent("Can be undone in the chat within 7 days.");
  expect(linha).toHaveAttribute("data-situacao", "completo");
  expect(api.perguntas).toEqual(["Quiero bloquear mi tarjeta"]);
});
