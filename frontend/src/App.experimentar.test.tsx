// O "Try in ES/PT" do design (experimentar), que o guia e o atendente usam, contra um servidor mínimo na
// fronteira de rede. A área do atendente é trocada por um botão que chama o experimentar, como os do
// design farão; a casca, a sessão e a conversa são as de verdade.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsDaArea } from "./abas/area";
import { App } from "./App";

vi.mock("./abas/Atendente", () => ({
  AreaDoAtendente: ({ experimentar }: PropsDaArea) => (
    <button type="button" onClick={() => experimentar("Me robaron la tarjeta")}>
      Try in ES
    </button>
  ),
}));

const PERSONAS = [
  { customer_id: "CLI-A", nome: "Ana Souza", cartoes_bloqueaveis: 0, transacoes_recusadas: 0, pre_casos_recentes: 0, contestaveis: 0, exemplo: null },
  { customer_id: "CLI-B", nome: "Bruno Lima", cartoes_bloqueaveis: 1, transacoes_recusadas: 2, pre_casos_recentes: 0, contestaveis: 1, exemplo: null },
];

let pedidos: { url: string; corpo: unknown }[] = [];

beforeEach(() => {
  pedidos = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const corpo = init?.body ? JSON.parse(String(init.body)) : null;
      pedidos.push({ url, corpo });
      const responder = (status: number, dados: unknown) => new Response(JSON.stringify(dados), { status });
      if (url === "/api/personas") return responder(200, PERSONAS);
      if (url === "/api/sessoes") {
        const cliente = PERSONAS.find((p) => p.customer_id === (corpo as { customer_id: string }).customer_id);
        return responder(201, { token: "tok", expira_em: "2099-01-01T00:00:00Z", cliente, dispositivo: (corpo as { dispositivo: string }).dispositivo });
      }
      if (url === "/api/minhas/transacoes") return responder(200, []);
      if (url === "/api/minhas/pre-casos") return responder(200, []);
      if (url === "/api/conversas") {
        return responder(201, { conversa_id: "C1", idioma: (corpo as { idioma: string }).idioma, estado: "livre", resposta: "Hola." });
      }
      if (url === "/api/conversas/C1/turnos") {
        return responder(200, {
          idioma: "es", estado: "com_humano", resposta: "Te paso con un agente.", regra: "POL-HUM-01", acao: "humano",
          interpretacao: "regras", intencao: "fraude", opcoes: [], protocolo: null, atendimento: "AT-00000001",
          transaction_id: null, resolucao: null, descricao: null, efeito: null, fontes: [], recibo: null,
        });
      }
      return responder(500, {});
    }),
  );
  window.history.replaceState(null, "", "/#atendente");
});

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

test("o Try entra sozinho com a persona da demonstração e o dispositivo cadastrado, e a frase vai para a conversa", async () => {
  // O app na janela do site: cada turno vai para o pai, que acende o caminho no mapa.
  const postMessage = vi.fn();
  vi.stubGlobal("parent", { postMessage });
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Try in ES" }));
  expect(await screen.findByText("Te paso con un agente.")).toBeVisible();
  expect(screen.getByRole("tab", { name: "Customer" })).toHaveAttribute("aria-selected", "true");
  expect(window.location.hash).toBe("#cliente");
  const sessao = pedidos.find((p) => p.url === "/api/sessoes");
  expect(sessao?.corpo).toEqual({ customer_id: "CLI-B", dispositivo: "cadastrado" });
  expect(pedidos.find((p) => p.url === "/api/conversas")?.corpo).toEqual({ idioma: "es" });
  expect(pedidos.filter((p) => p.url === "/api/conversas/C1/turnos").map((p) => p.corpo)).toEqual([{ texto: "Me robaron la tarjeta" }]);
  expect(postMessage).toHaveBeenCalledWith(
    expect.objectContaining({ type: "jeje-turn", rule: "POL-HUM-01", human: true }),
    window.location.origin,
  );
});
