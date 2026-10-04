// A aba do atendente (DEV-032b, 2.10) contra um servidor mínimo na fronteira de rede: o caso pronto
// como no design (o pedido pela regra, os fatos, as ações, as pendências e as falas), o "Take case"
// e o "Unblock" só depois de a API confirmar, e a fila vazia com as frases para experimentar.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BloqueioDeCartao, Encaminhamento, PersonaDaDemo } from "../api/cliente";
import { AreaDoAtendente } from "./Atendente";

const FRAUDE: Encaminhamento = {
  id: "AT-00000031",
  customer_id: "CLI-A",
  regra: "POL-HUM-01",
  idioma: "es",
  pedido: "Me robaron la tarjeta",
  transacao: {
    transaction_id: "TRX-A1",
    data: "2025-03-10T10:00:00",
    valor: "1234.5",
    moeda: "USD",
    comercio: "Mercado Sol",
    status: "Approved",
  },
  acoes: [
    { acao: "bloquear_cartao", resultado: "BL-00000007" },
    { acao: "interpretar", resultado: "POL-HUM-01: robaron" },
    { acao: "acao_nova", resultado: "x" },
  ],
  pendencias: ["Tratar relato de fraude"],
  estado: "aberto",
  criado_em: "2026-10-03T14:01:01Z",
};

const BLOQUEIO: BloqueioDeCartao = {
  id: "BL-00000007",
  customer_id: "CLI-A",
  product_id: "CRT-A1",
  produto: "Tarjeta Crédito",
  ultimos4: "4417",
  tipo: "completo",
  motivo: "roubo_perda",
  dispositivo: "cadastrado",
  criado_em: "2026-10-03T14:01:01Z",
  reversivel_ate: "2026-10-10T14:01:01Z",
  desfeito_em: null,
  desfeito_por: null,
  atendimento: "AT-00000031",
};

const LUCIA: PersonaDaDemo = {
  customer_id: "CLI-A",
  nome: "Lucía",
  cartoes_bloqueaveis: 1,
  transacoes_recusadas: 2,
  pre_casos_recentes: 0,
  contestaveis: 3,
  exemplo: null,
};

type Resposta = { status: number; corpo: unknown };

/** Servidor na fronteira de rede: a fila e os bloqueios na ordem pedida; os POST respondem na ordem. */
function servidor(filas: Encaminhamento[][], bloqueios: BloqueioDeCartao[][], posts: Resposta[] = []) {
  const chamadas: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push(`${init?.method ?? "GET"} ${url}`);
      const r = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
      if (init?.method === "POST") {
        const proxima = posts.shift() ?? { status: 500, corpo: {} };
        return r(proxima.status, proxima.corpo);
      }
      if (url.startsWith("/api/personas")) return r(200, [LUCIA]);
      if (url.startsWith("/api/atendimento/bloqueios")) return r(200, bloqueios.shift() ?? []);
      return r(200, filas.shift() ?? []);
    }),
  );
  return chamadas;
}

const area = (extra: Partial<Parameters<typeof AreaDoAtendente>[0]> = {}) => ({
  versao: 0,
  aoMudar: vi.fn(),
  experimentar: vi.fn(),
  ...extra,
});

afterEach(() => vi.unstubAllGlobals());

test("o caso chega pronto: o pedido pela regra, os fatos, as ações, as pendências e as falas", async () => {
  servidor([[FRAUDE]], [[BLOQUEIO]]);
  render(<AreaDoAtendente {...area()} />);
  const caso = await screen.findByRole("article", { name: "AT-00000031" });
  const c = within(caso);
  expect(c.getByText("POL-HUM-01")).toBeInTheDocument();
  expect(c.getByText("Reports fraud, theft or loss of the card")).toBeInTheDocument();
  expect(c.getByText("Confirm the block and next steps with the customer")).toBeInTheDocument();
  // O nome do cliente vem das personas; o valor e o dia, da transação do caso.
  await waitFor(() => expect(c.getAllByText("CLI-A · Lucía")).toHaveLength(2));
  expect(c.getByText("Mercado Sol · USD 1,234.50 · 10/03")).toBeInTheDocument();
  expect(c.getByText("•••• 4417 · blocked · full")).toBeInTheDocument();
  expect(c.getByText("full block (simulated) ✓")).toBeInTheDocument();
  expect(c.getByText("read the message ✓")).toBeInTheDocument();
  expect(c.getByText("acao_nova ✓")).toBeInTheDocument();
  expect(c.getByText("21/280")).toBeInTheDocument();
  expect(c.getByText("“Me robaron la tarjeta”")).toBeInTheDocument();
  expect(screen.getByText("Queue · 1")).toBeInTheDocument();
});

test("a regra que o design não desenhou e a desconhecida", async () => {
  const limite = { ...FRAUDE, id: "AT-00000032", regra: "POL-HUM-02" };
  const nova = { ...FRAUDE, id: "AT-00000033", regra: "POL-NOVA-01", pendencias: ["Olhar à mão", "E responder"] };
  servidor([[limite, nova]], [[]]);
  render(<AreaDoAtendente {...area()} />);
  const c1 = within(await screen.findByRole("article", { name: "AT-00000032" }));
  expect(c1.getByText("Dispute above the simulated limit")).toBeInTheDocument();
  expect(c1.getByText("Review the dispute by hand")).toBeInTheDocument();
  const c2 = within(screen.getByRole("article", { name: "AT-00000033" }));
  expect(c2.getAllByText("POL-NOVA-01")).toHaveLength(2); // no topo e no lugar do pedido
  expect(c2.getByText("Olhar à mão; E responder")).toBeInTheDocument();
});

test("o desbloqueio anotado no caso diz qual bloqueio saiu e quem o desfez", async () => {
  const desfeito = {
    ...FRAUDE,
    acoes: [
      { acao: "bloquear_cartao", resultado: "BL-00000007" },
      { acao: "desbloquear_cartao", resultado: "BL-00000007: desfeito pelo cliente" },
    ],
  };
  servidor([[desfeito]], [[]]);
  render(<AreaDoAtendente {...area()} />);
  const c = within(await screen.findByRole("article", { name: "AT-00000031" }));
  expect(c.getByText("unblock (simulated) · BL-00000007 · undone by the customer ✓")).toBeInTheDocument();
  // Sem o bloqueio ativo, o caso não mostra mais o cartão bloqueado.
  expect(c.queryByText(/•••• 4417/)).not.toBeInTheDocument();
});

test("Take case: só depois de a API confirmar, e o caso fica na tela como assumido", async () => {
  const props = area();
  const chamadas = servidor([[FRAUDE], []], [[], []], [{ status: 200, corpo: { ...FRAUDE, estado: "em_atendimento" } }]);
  render(<AreaDoAtendente {...props} />);
  await userEvent.click(await screen.findByRole("button", { name: "Take case AT-00000031" }));
  const assumido = await screen.findByRole("button", { name: "Taken by you AT-00000031" });
  expect(assumido).toHaveAttribute("aria-pressed", "true");
  expect(chamadas).toContain("POST /api/atendimento/fila/AT-00000031/assumir");
  await waitFor(() => expect(screen.getByText("Queue · 0")).toBeInTheDocument());
  expect(screen.getByRole("article", { name: "AT-00000031" })).toBeInTheDocument();
  expect(props.aoMudar).toHaveBeenCalledTimes(1);
});

test("Take case recusado: o aviso, e o caso segue para assumir", async () => {
  const props = area();
  servidor([[FRAUDE], [FRAUDE]], [[], []], [{ status: 409, corpo: { detail: "Já assumido" } }]);
  render(<AreaDoAtendente {...props} />);
  await userEvent.click(await screen.findByRole("button", { name: "Take case AT-00000031" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Could not take this case.");
  expect(screen.getByRole("button", { name: "Take case AT-00000031" })).toHaveAttribute("aria-pressed", "false");
  expect(props.aoMudar).not.toHaveBeenCalled();
});

test("Unblock: o bloqueio sai depois da API, e a lista vazia diz que não há cartão bloqueado", async () => {
  const props = area();
  const chamadas = servidor([[], []], [[BLOQUEIO], []], [{ status: 200, corpo: { ...BLOQUEIO, desfeito_por: "atendente" } }]);
  render(<AreaDoAtendente {...props} />);
  const linha = within(await screen.findByLabelText("BL-00000007"));
  expect(linha.getByText("•••• 4417")).toBeInTheDocument();
  expect(linha.getByText(/^blocked · full · since \d\d:\d\d:\d\d$/)).toBeInTheDocument();
  expect(screen.getByText("Card blocks · 1")).toBeInTheDocument();
  await userEvent.click(linha.getByRole("button", { name: "Unblock BL-00000007" }));
  expect(await screen.findByText("No blocked cards.")).toBeInTheDocument();
  expect(chamadas).toContain("POST /api/atendimento/bloqueios/BL-00000007/desbloqueio");
  expect(props.aoMudar).toHaveBeenCalledTimes(1);
});

test("o bloqueio preventivo tem a etiqueta tracejada", async () => {
  servidor([[]], [[{ ...BLOQUEIO, tipo: "preventivo", atendimento: null }]]);
  render(<AreaDoAtendente {...area()} />);
  const etiqueta = await screen.findByText(/^blocked · preventive · since/);
  expect(etiqueta).toHaveClass("cn-preventivo");
});

test("a fila vazia sugere três frases, que vão para a conversa", async () => {
  const props = area();
  servidor([[]], [[]]);
  render(<AreaDoAtendente {...props} />);
  expect(await screen.findByText("The queue is empty.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "“Me robaron la tarjeta”" }));
  expect(props.experimentar).toHaveBeenCalledWith("Me robaron la tarjeta");
  expect(screen.getAllByRole("button", { name: /^“/ })).toHaveLength(3);
});

test("cada efeito da conversa relê a fila e os bloqueios", async () => {
  const chamadas = servidor([[], [FRAUDE]], [[], []]);
  const { rerender } = render(<AreaDoAtendente {...area()} />);
  await screen.findByText("The queue is empty.");
  rerender(<AreaDoAtendente {...area({ versao: 1 })} />);
  expect(await screen.findByRole("article", { name: "AT-00000031" })).toBeInTheDocument();
  expect(chamadas.filter((c) => c === "GET /api/atendimento/fila")).toHaveLength(2);
});
