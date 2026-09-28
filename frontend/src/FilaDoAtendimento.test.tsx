// Fila do atendente contra um servidor mínimo na fronteira de rede: mostra o resumo que a API
// entregou, na ordem, e busca de novo quando a conversa cria um encaminhamento.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Encaminhamento } from "./api/cliente";
import { FilaDoAtendimento } from "./FilaDoAtendimento";

const FRAUDE: Encaminhamento = {
  id: "AT-00000001",
  customer_id: "CLI-A",
  regra: "POL-HUM-01",
  idioma: "pt",
  pedido: "roubaram meu cartão",
  transacao: null,
  acoes: [{ acao: "interpretar", resultado: "POL-HUM-01: roubaram" }],
  pendencias: ["Tratar relato de fraude: bloqueio e análise do cartão (relato de fraude)"],
  estado: "aberto",
  criado_em: "2026-09-28T10:00:00Z",
};

const LIMITE: Encaminhamento = {
  ...FRAUDE,
  id: "AT-00000002",
  regra: "POL-HUM-02",
  idioma: "es",
  pedido: "No reconozco la compra en Boutique Moda",
  transacao: {
    transaction_id: "TRX-A4",
    data: "2025-03-15T11:00:00",
    valor: "5000.00",
    moeda: "USD",
    comercio: "Boutique Moda",
    status: "Approved",
  },
  acoes: [{ acao: "avaliar_contestacao", resultado: "POL-HUM-02: acima do limite simulado" }],
  pendencias: ["Revisar contestação que a automação não pode registrar (acima do limite simulado)"],
};

type Assumir = { status: number; corpo: unknown } | "pendente";

/** Servidor na fronteira de rede: filas na ordem pedida; `assumir` responde as tentativas. */
function servidor(filas: Encaminhamento[][], assumir: Assumir[] = []) {
  const chamadas: string[] = [];
  let liberar: (() => void) | null = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push(`${init?.method ?? "GET"} ${url}`);
      const r = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
      if (init?.method === "POST") {
        const proxima = assumir.shift() ?? { status: 500, corpo: {} };
        if (proxima === "pendente") {
          await new Promise<void>((ok) => (liberar = ok));
          return r(200, { ...FRAUDE, estado: "em_atendimento" });
        }
        return r(proxima.status, proxima.corpo);
      }
      return r(200, filas.shift() ?? []);
    }),
  );
  return { chamadas, liberar: () => liberar?.() };
}

afterEach(() => vi.unstubAllGlobals());

test("mostra cada encaminhamento com pedido, fatos, ações e pendências, na ordem da API", async () => {
  servidor([[FRAUDE, LIMITE]]);
  render(<FilaDoAtendimento versao={0} />);
  const itens = await screen.findAllByRole("listitem", { name: /Encaminhamento AT-/ });
  expect(itens.map((i) => i.getAttribute("aria-label"))).toEqual(["Encaminhamento AT-00000001", "Encaminhamento AT-00000002"]);
  const [, item] = itens;
  if (!item) throw new Error("segundo encaminhamento ausente");
  const segundo = within(item);
  expect(segundo.getByText(/POL-HUM-02 · ES · cliente CLI-A/)).toBeInTheDocument();
  expect(segundo.getByText("Pedido: “No reconozco la compra en Boutique Moda”")).toBeInTheDocument();
  expect(segundo.getByText(/Transação TRX-A4: Boutique Moda, USD 5000.00, Approved/)).toBeInTheDocument();
  expect(within(segundo.getByRole("list", { name: "Ações tentadas" })).getByText("avaliar_contestacao: POL-HUM-02: acima do limite simulado")).toBeInTheDocument();
  expect(within(segundo.getByRole("list", { name: "Pendências" })).getByText("Revisar contestação que a automação não pode registrar (acima do limite simulado)")).toBeInTheDocument();
});

test("fila vazia diz que não há encaminhamento e busca de novo quando a versão muda", async () => {
  const { chamadas } = servidor([[], [FRAUDE]]);
  const { rerender } = render(<FilaDoAtendimento versao={0} />);
  expect(await screen.findByText("Nenhum encaminhamento aberto.")).toBeInTheDocument();
  rerender(<FilaDoAtendimento versao={1} />);
  expect(await screen.findByRole("listitem", { name: "Encaminhamento AT-00000001" })).toBeInTheDocument();
  expect(chamadas).toEqual(["GET /api/atendimento/fila", "GET /api/atendimento/fila"]);
});

test("assumir tira da fila só depois que a API confirma", async () => {
  const { chamadas, liberar } = servidor([[FRAUDE, LIMITE], [LIMITE]], ["pendente"]);
  render(<FilaDoAtendimento versao={0} />);
  await userEvent.click(await screen.findByRole("button", { name: "Assumir AT-00000001" }));
  expect(screen.getByRole("listitem", { name: "Encaminhamento AT-00000001" })).toBeInTheDocument();
  liberar();
  expect(await screen.findByText("Você assumiu AT-00000001.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("listitem", { name: "Encaminhamento AT-00000001" })).not.toBeInTheDocument());
  expect(chamadas).toEqual([
    "GET /api/atendimento/fila",
    "POST /api/atendimento/fila/AT-00000001/assumir",
    "GET /api/atendimento/fila",
  ]);
});

test("encaminhamento já assumido por outro mostra o motivo e atualiza a fila", async () => {
  const { chamadas } = servidor([[FRAUDE], []], [{ status: 409, corpo: { detail: "Encaminhamento já assumido" } }]);
  render(<FilaDoAtendimento versao={0} />);
  await userEvent.click(await screen.findByRole("button", { name: "Assumir AT-00000001" }));
  expect(await screen.findByText("AT-00000001: Encaminhamento já assumido.")).toBeInTheDocument();
  expect(await screen.findByText("Nenhum encaminhamento aberto.")).toBeInTheDocument();
  expect(chamadas).toHaveLength(3);
});
