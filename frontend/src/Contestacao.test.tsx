// Contestação contra um servidor mínimo na fronteira de rede; a regra é decidida pela API real
// (testada no backend e no E2E). Aqui: o que a tela promete e quantas vezes confirma.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Transacao } from "./api/cliente";
import { Contestacao } from "./Contestacao";

const TRANSACAO: Transacao = {
  transaction_id: "TRX-1",
  transaction_date: "2025-03-11T20:15:00",
  amount: "45.90",
  currency: "USD",
  transaction_status: "Approved",
  response_code: "00",
  transaction_type: "Purchase",
  merchant_name: "Streaming Plus",
  channel: "Web",
};

type Resposta = { status: number; corpo: unknown };

function servidor(avaliacao: Resposta, confirmacoes: Resposta[] = []) {
  const confirmados: string[] = [];
  let resolverPendente: (() => void) | null = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const r = (x: Resposta) => new Response(JSON.stringify(x.corpo), { status: x.status });
      if (url === "/api/minhas/transacoes/TRX-1/contestacao/proposta" && init?.method === "POST") return r(avaliacao);
      if (url === "/api/minhas/propostas/P1/confirmacao" && init?.method === "POST") {
        confirmados.push(url);
        const resposta = confirmacoes.shift() ?? { status: 201, corpo: {} };
        if (resposta.status === 0) {
          await new Promise<void>((ok) => (resolverPendente = ok));
          return r({ status: 201, corpo: PRE_CASO });
        }
        return r(resposta);
      }
      return r({ status: 404, corpo: { detail: "Not Found" } });
    }),
  );
  return { confirmados, liberar: () => resolverPendente?.() };
}

const PRE_CASO = { protocolo: "PC-00000007", transaction_id: "TRX-1", estado: "recebido", criado_em: "2025-03-12T10:00:00Z" };
const PROPOSTA = {
  status: 201,
  corpo: {
    decisao: { regra: "POL-DISP-01", acao: "propor_pre_caso", detalhe: null },
    proposta: { id: "P1", transaction_id: "TRX-1", expira_em: "2099-01-01T00:00:00Z" },
  },
};

afterEach(() => vi.unstubAllGlobals());

function montar(aoRegistrar = vi.fn()) {
  render(<Contestacao token="tok" transacao={TRANSACAO} aoRegistrar={aoRegistrar} aoExpirar={vi.fn()} />);
  return aoRegistrar;
}

test("elegível: confirma e só então mostra o protocolo devolvido pela API", async () => {
  const { confirmados } = servidor(PROPOSTA, [{ status: 201, corpo: PRE_CASO }]);
  const aoRegistrar = montar();
  await userEvent.click(screen.getByRole("button", { name: "Contestar" }));
  expect(await screen.findByText(/não estorna o valor/)).toBeInTheDocument();
  expect(screen.queryByText(/protocolo/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Confirmar contestação" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Pré-caso recebido: protocolo PC-00000007");
  expect(confirmados).toHaveLength(1);
  expect(aoRegistrar).toHaveBeenCalledTimes(1);
});

test("não elegível: explica e não oferece confirmação", async () => {
  servidor({ status: 200, corpo: { decisao: { regra: "POL-DISP-02", acao: "humano", detalhe: "Declined" }, proposta: null } });
  montar();
  await userEvent.click(screen.getByRole("button", { name: "Contestar" }));
  expect(await screen.findByRole("status")).toHaveTextContent("não pode ser contestada automaticamente");
  expect(screen.queryByRole("button", { name: "Confirmar contestação" })).not.toBeInTheDocument();
});

test("pré-caso já existente é informado com o protocolo", async () => {
  servidor({ status: 200, corpo: { decisao: { regra: "POL-DISP-03", acao: "responder", detalhe: "PC-00000003" }, proposta: null } });
  montar();
  await userEvent.click(screen.getByRole("button", { name: "Contestar" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Já existe o pré-caso PC-00000003");
});

test("clique duplo em confirmar envia uma única confirmação", async () => {
  const api = servidor(PROPOSTA, [{ status: 0, corpo: null }]);
  montar();
  await userEvent.click(screen.getByRole("button", { name: "Contestar" }));
  const confirmar = await screen.findByRole("button", { name: "Confirmar contestação" });
  await userEvent.dblClick(confirmar);
  api.liberar();
  expect(await screen.findByRole("status")).toHaveTextContent("PC-00000007");
  expect(api.confirmados).toHaveLength(1);
});

test("falha ao registrar não mostra protocolo e diz que nada foi criado", async () => {
  servidor(PROPOSTA, [{ status: 503, corpo: { detail: "Pré-caso não registrado; nada foi criado." } }]);
  const aoRegistrar = montar();
  await userEvent.click(screen.getByRole("button", { name: "Contestar" }));
  await userEvent.click(await screen.findByRole("button", { name: "Confirmar contestação" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("nada foi criado");
  expect(screen.queryByText(/protocolo/)).not.toBeInTheDocument();
  expect(aoRegistrar).not.toHaveBeenCalled();
});

test("proposta vencida mostra a explicação da API", async () => {
  servidor(PROPOSTA, [{ status: 409, corpo: { detail: "proposta vencida; peça uma nova avaliação" } }]);
  montar();
  await userEvent.click(screen.getByRole("button", { name: "Contestar" }));
  await userEvent.click(await screen.findByRole("button", { name: "Confirmar contestação" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("proposta vencida");
});
