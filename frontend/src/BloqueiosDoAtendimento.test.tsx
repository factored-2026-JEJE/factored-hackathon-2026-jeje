// Bloqueios de cartão no console do atendente contra um servidor mínimo na fronteira de rede:
// mostra o que a API entregou (só tipo e final do cartão), desbloqueia só com a confirmação dela e
// busca de novo quando a conversa bloqueia.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { BloqueioDeCartao } from "./api/cliente";
import { BloqueiosDoAtendimento } from "./BloqueiosDoAtendimento";

const COMPLETO: BloqueioDeCartao = {
  id: "BL-00000002",
  customer_id: "CLI-A",
  product_id: "CRT-A1",
  produto: "Tarjeta Crédito",
  ultimos4: "9241",
  tipo: "completo",
  motivo: "pedido",
  dispositivo: "cadastrado",
  criado_em: "2026-09-30T10:00:00Z",
  reversivel_ate: "2026-10-07T10:00:00Z",
  desfeito_em: null,
  desfeito_por: null,
  atendimento: null,
};

const PREVENTIVO: BloqueioDeCartao = {
  ...COMPLETO,
  id: "BL-00000001",
  customer_id: "CLI-B",
  product_id: "CRT-B1",
  ultimos4: null,
  tipo: "preventivo",
  motivo: "roubo_perda",
  dispositivo: "novo",
  atendimento: "AT-00000007",
};

type Desbloqueio = { status: number; corpo: unknown } | "pendente";

/** Servidor na fronteira de rede: listas na ordem pedida; `desbloqueios` responde as tentativas. */
function servidor(listas: BloqueioDeCartao[][], desbloqueios: Desbloqueio[] = []) {
  const chamadas: string[] = [];
  let liberar: (() => void) | null = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      chamadas.push(`${init?.method ?? "GET"} ${url}`);
      const r = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
      if (init?.method === "POST") {
        const proxima = desbloqueios.shift() ?? { status: 500, corpo: {} };
        if (proxima === "pendente") {
          await new Promise<void>((ok) => (liberar = ok));
          return r(200, { ...COMPLETO, desfeito_em: "2026-09-30T11:00:00Z", desfeito_por: "atendente" });
        }
        return r(proxima.status, proxima.corpo);
      }
      const lista = listas.shift();
      return lista ? r(200, lista) : r(500, {});
    }),
  );
  return { chamadas, liberar: () => liberar?.() };
}

afterEach(() => vi.unstubAllGlobals());

test("mostra cada bloqueio ativo com o cartão só pelo tipo e pelo final, na ordem da API", async () => {
  servidor([[COMPLETO, PREVENTIVO]]);
  render(<BloqueiosDoAtendimento versao={0} />);
  const itens = await screen.findAllByRole("listitem", { name: /Bloqueio BL-/ });
  expect(itens.map((i) => i.getAttribute("aria-label"))).toEqual(["Bloqueio BL-00000002", "Bloqueio BL-00000001"]);
  const [item1, item2] = itens;
  if (!item1 || !item2) throw new Error("bloqueio ausente");
  const [primeiro, segundo] = [within(item1), within(item2)];
  expect(primeiro.getByText(/Tarjeta Crédito final 9241 · bloqueio completo · cliente CLI-A/)).toBeInTheDocument();
  expect(primeiro.getByText(/Motivo: pedido do cliente · dispositivo cadastrado/)).toBeInTheDocument();
  expect(segundo.getByText(/Tarjeta Crédito · bloqueio preventivo · cliente CLI-B/)).toBeInTheDocument();
  expect(segundo.getByText(/Motivo: relato de roubo ou perda · dispositivo novo/)).toBeInTheDocument();
  // O bloqueio ligado a um caso mostra qual: o caso fica sabendo se ele for desfeito.
  expect(segundo.getByText(/caso AT-00000007/)).toBeInTheDocument();
  expect(primeiro.queryByText(/caso AT-/)).not.toBeInTheDocument();
});

test("sem bloqueio ativo diz isso e busca de novo quando a versão muda", async () => {
  const { chamadas } = servidor([[], [PREVENTIVO]]);
  const { rerender } = render(<BloqueiosDoAtendimento versao={0} />);
  expect(await screen.findByText("Nenhum bloqueio ativo.")).toBeInTheDocument();
  rerender(<BloqueiosDoAtendimento versao={1} />);
  expect(await screen.findByRole("listitem", { name: "Bloqueio BL-00000001" })).toBeInTheDocument();
  expect(chamadas).toEqual(["GET /api/atendimento/bloqueios?limite=100", "GET /api/atendimento/bloqueios?limite=100"]);
});

test("desbloquear tira da lista só depois que a API confirma", async () => {
  const { chamadas, liberar } = servidor([[COMPLETO, PREVENTIVO], [PREVENTIVO]], ["pendente"]);
  render(<BloqueiosDoAtendimento versao={0} />);
  await userEvent.click(await screen.findByRole("button", { name: "Desbloquear BL-00000002" }));
  expect(screen.getByRole("listitem", { name: "Bloqueio BL-00000002" })).toBeInTheDocument();
  liberar();
  expect(await screen.findByText("Você desbloqueou BL-00000002.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByRole("listitem", { name: "Bloqueio BL-00000002" })).not.toBeInTheDocument());
  expect(chamadas).toEqual([
    "GET /api/atendimento/bloqueios?limite=100",
    "POST /api/atendimento/bloqueios/BL-00000002/desbloqueio",
    "GET /api/atendimento/bloqueios?limite=100",
  ]);
});

test("bloqueio já desfeito por outro mostra o motivo da API e atualiza a lista", async () => {
  const { chamadas } = servidor([[COMPLETO], []], [{ status: 409, corpo: { detail: "Bloqueio já desfeito" } }]);
  render(<BloqueiosDoAtendimento versao={0} />);
  await userEvent.click(await screen.findByRole("button", { name: "Desbloquear BL-00000002" }));
  expect(await screen.findByText("BL-00000002: Bloqueio já desfeito.")).toBeInTheDocument();
  expect(await screen.findByText("Nenhum bloqueio ativo.")).toBeInTheDocument();
  expect(chamadas).toHaveLength(3);
});

test("console fora do ar avisa em vez de mostrar lista vazia", async () => {
  servidor([]);
  render(<BloqueiosDoAtendimento versao={0} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Bloqueios indisponíveis.");
  expect(screen.queryByText("Nenhum bloqueio ativo.")).not.toBeInTheDocument();
});
