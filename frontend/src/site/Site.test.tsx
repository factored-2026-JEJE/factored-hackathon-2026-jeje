// O site (DEV-032a) no jsdom: os links até o app, a troca de idioma e a conversa, de exemplo (sem a
// API) e de verdade. Na de verdade, a resposta da API entra pela borda (fetch); a lógica do site que
// monta a conversa, as opções e o "Por que esta resposta?" é a de produção.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PersonaDaDemo, ResultadoDoTurno } from "../api/cliente";
import { Site, escolherPersona } from "./Site";

const persona = (p: Partial<PersonaDaDemo>): PersonaDaDemo => ({
  customer_id: "CLI-X",
  nome: "X",
  cartoes_bloqueaveis: 0,
  transacoes_recusadas: 0,
  pre_casos_recentes: 0,
  contestaveis: 0,
  exemplo: null,
  ...p,
});

beforeEach(() => {
  localStorage.clear();
  // O jsdom não rola; o site pede a rolagem até o mapa ao mandar uma mensagem.
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
});
afterEach(() => vi.unstubAllGlobals());

describe("sem a API (o site público)", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("sem rede")))));

  it("leva ao app e ao guia, e troca o idioma do site", async () => {
    render(<Site />);
    expect(screen.getAllByRole("link", { name: /Abrir o app/ })[0]).toHaveAttribute("href", "/#cliente");
    expect(screen.getByRole("link", { name: /How to test/ })).toHaveAttribute("href", "/#how-to-test");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Não é um chatbot.");
    await userEvent.click(screen.getByRole("button", { name: "ES" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("No es un chatbot.");
    expect(localStorage.getItem("jeje.site.lang")).toBe("es");
  });

  it("a conversa mostra o exemplo do design, com as opções e o porquê", async () => {
    render(<Site />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Mande uma mensagem/ })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: /Mande uma mensagem/ }));
    const dock = screen.getByRole("dialog", { name: "Conversa" });
    await userEvent.click(within(dock).getByRole("button", { name: "Não reconheço uma cobrança" }));
    expect(within(dock).getByText("Não reconheço a cobrança de 45,90 do dia 10/03")).toBeInTheDocument();
    expect(within(dock).getByText(/Encontrei a cobrança de USD 45,90/)).toBeInTheDocument();
    await userEvent.click(within(dock).getByRole("button", { name: /Por que esta resposta/ }));
    expect(within(dock).getByText("POL-DISP-01")).toBeInTheDocument();
    await userEvent.click(within(dock).getByRole("button", { name: "Sim, confirmo" }));
    expect(within(dock).getByText(/protocolo PC-000417/)).toBeInTheDocument();
    // A nota diz que são turnos de exemplo (fatos.ts), não a API.
    expect(within(dock).getByText(/Turnos de exemplo/)).toBeInTheDocument();
  });
});

describe("com a API (acesso aberto)", () => {
  const turno: ResultadoDoTurno = {
    conversa_id: "CV-1",
    numero: 1,
    idioma: "pt",
    intencao: "contestar",
    regra: "POL-DISP-01",
    acao: "propor_pre_caso",
    estado: "confirmando",
    resposta: "Encontrei a cobrança de USD 64,50 de 09/03 na Loja Fixa. Registro um pedido de revisão?",
    transaction_id: "TX-FX-7",
    opcoes: [],
    proposta: { id: "PR-1", transaction_id: "TX-FX-7", expira_em: "2026-10-02T20:00:00Z" },
    protocolo: null,
    atendimento: null,
    bloqueio: null,
    descricao: "Contestação dentro dos limites simulados",
    interpretacao: "regras",
    efeito: null,
    fontes: ["transacoes:TX-FX-7"],
    resolucao: { resolvedor: "filtro", calibracao: null, probabilidade: null, possiveis: null },
    recibo: { transaction_id: "TX-FX-7", arquivo: "transactions.csv", linha: 7, versao_dos_dados: "abc123def4567890" },
  };
  const pedidos: { url: string; corpo: unknown }[] = [];

  beforeEach(() => {
    pedidos.length = 0;
    const json = (status: number, corpo: unknown) =>
      Promise.resolve(new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        pedidos.push({ url, corpo: init?.body ? JSON.parse(String(init.body)) : null });
        if (url === "/api/acesso") return json(200, { restrito: false, liberado: true });
        if (url === "/api/personas")
          return json(200, [
            persona({ customer_id: "CLI-SEM", nome: "Sem exemplo" }),
            persona({ customer_id: "CLI-FX1", nome: "Valentina", cartoes_bloqueaveis: 1, transacoes_recusadas: 2, exemplo: { valor: "64.50", moeda: "USD", data: "2025-03-09" } }),
          ]);
        if (url === "/api/sessoes") return json(201, { token: "TOKEN", expira_em: "2026-10-03T00:00:00Z", cliente: { customer_id: "CLI-FX1", nome: "Valentina" }, dispositivo: "cadastrado" });
        if (url === "/api/conversas") return json(201, { conversa_id: "CV-1", idioma: "pt", estado: "aguardando_pedido", resposta: "Olá" });
        if (url === "/api/conversas/CV-1/turnos") return json(200, turno);
        return json(404, {});
      }),
    );
  });

  it("a contestação vai com uma compra da persona, e o balão mostra o turno da API", async () => {
    render(<Site />);
    await userEvent.click(screen.getByRole("button", { name: /Mande uma mensagem/ }));
    const dock = screen.getByRole("dialog", { name: "Conversa" });
    await waitFor(() => expect(within(dock).getByText(/Ao vivo: POST \/conversas/)).toBeInTheDocument());
    await act(() => userEvent.click(within(dock).getByRole("button", { name: "Não reconheço uma cobrança" })));
    // A frase é a do guia do app, com o valor e o dia da compra de exemplo da persona.
    await waitFor(() => expect(within(dock).getByText(turno.resposta)).toBeInTheDocument());
    expect(pedidos.find((p) => p.url === "/api/sessoes")?.corpo).toEqual({ customer_id: "CLI-FX1", dispositivo: "cadastrado" });
    expect(pedidos.find((p) => p.url === "/api/conversas/CV-1/turnos")?.corpo).toEqual({ texto: "Não reconheço a cobrança de 64,50 do dia 09/03" });
    expect(within(dock).getByText("Não reconheço a cobrança de 64,50 do dia 09/03")).toBeInTheDocument();
    await userEvent.click(within(dock).getByRole("button", { name: /Por que esta resposta/ }));
    for (const v of ["POL-DISP-01", "Contestação dentro dos limites simulados", "propor_pre_caso", "filtro exato", "transactions.csv", "7", "abc123def456"])
      expect(within(dock).getByText(v)).toBeInTheDocument();
    // Na confirmação, os botões mandam o texto que o cliente digitaria.
    await act(() => userEvent.click(within(dock).getByRole("button", { name: "Sim, confirmo" })));
    await waitFor(() => expect(pedidos.filter((p) => p.url === "/api/conversas/CV-1/turnos")).toHaveLength(2));
    expect(pedidos.at(-1)?.corpo).toEqual({ texto: "Sim, confirmo" });
  });
});

describe("a persona da conversa de verdade", () => {
  it("prefere a que tem exemplo para contestar, cartão e mais de uma recusa", () => {
    const a = persona({ customer_id: "A", transacoes_recusadas: 5 });
    const b = persona({ customer_id: "B", exemplo: { valor: "1", moeda: "USD", data: "2025-01-01" } });
    const c = persona({ customer_id: "C", exemplo: { valor: "1", moeda: "USD", data: "2025-01-01" }, cartoes_bloqueaveis: 1 });
    expect(escolherPersona([a, b, c])?.customer_id).toBe("C");
    expect(escolherPersona([a, b])?.customer_id).toBe("B");
    expect(escolherPersona([])).toBeUndefined();
  });
});
