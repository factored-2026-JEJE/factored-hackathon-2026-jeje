// Fila do atendente contra um servidor mínimo na fronteira de rede: mostra o resumo que a API
// entregou, na ordem, e busca de novo quando a conversa cria um encaminhamento.
import { render, screen, within } from "@testing-library/react";
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

function servidor(...respostas: Encaminhamento[][]) {
  const chamadas: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      chamadas.push(url);
      return new Response(JSON.stringify(respostas.shift() ?? []), { status: 200 });
    }),
  );
  return chamadas;
}

afterEach(() => vi.unstubAllGlobals());

test("mostra cada encaminhamento com pedido, fatos, ações e pendências, na ordem da API", async () => {
  servidor([FRAUDE, LIMITE]);
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
  const chamadas = servidor([], [FRAUDE]);
  const { rerender } = render(<FilaDoAtendimento versao={0} />);
  expect(await screen.findByText("Nenhum encaminhamento aberto.")).toBeInTheDocument();
  rerender(<FilaDoAtendimento versao={1} />);
  expect(await screen.findByRole("listitem", { name: "Encaminhamento AT-00000001" })).toBeInTheDocument();
  expect(chamadas).toEqual(["/api/atendimento/fila", "/api/atendimento/fila"]);
});
