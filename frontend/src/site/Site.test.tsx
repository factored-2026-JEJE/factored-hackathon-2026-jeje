// O site (DEV-032a) no jsdom: a janela do app, a troca de idioma e a conversa, de exemplo (sem a API) e
// de verdade. Na de verdade, a resposta da API entra pela borda (fetch); a lógica do site que monta a
// conversa, as opções e o "Por que esta resposta?" é a de produção. A barra do dock só aparece depois de
// 55% da tela rolada, e o jsdom não rola: os cliques nela não conferem o pointer-events.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PersonaDaDemo, ResultadoDoTurno } from "../api/cliente";
import { CONTEUDO_DO_MAIN } from "./fatos";
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

// O site inteiro no jsdom (o template do design tem ~5 mil nós) leva segundos por interação numa
// máquina carregada: os testes com várias interações têm um limite maior.
const LONGO = 20_000;

describe("sem a API (o site público)", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("sem rede")))));

  it("leva ao app e ao guia, e troca o idioma do site", async () => {
    render(<Site />);
    // O inglês é o padrão (design de 03/10); o app abre numa janela dentro do site, com o app de verdade.
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Not a chatbot.");
    await userEvent.click(screen.getAllByRole("button", { name: /Open the app/ })[0] as HTMLElement);
    const janela = screen.getByRole("dialog", { name: "JEJE app" });
    expect(within(janela).getByTitle("JEJE app")).toHaveAttribute("src", "/?lang=en&tab=cliente#cliente");
    expect(within(janela).getByRole("link", { name: /New tab/ })).toHaveAttribute("href", "/#cliente");
    await userEvent.click(within(janela).getByRole("button", { name: /Close/ }));
    expect(screen.queryByRole("dialog", { name: "JEJE app" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /How to test/ }));
    expect(within(screen.getByRole("dialog", { name: "JEJE app" })).getByTitle("JEJE app")).toHaveAttribute(
      "src",
      "/?lang=en&tab=guia#how-to-test",
    );
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "JEJE app" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "ES" }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("No es un chatbot.");
    expect(localStorage.getItem("jeje.site.locale")).toBe("es");
    expect(document.documentElement.lang).toBe("es");
  }, LONGO);

  it("o placar do atacante é o do portão de release no congelado (1 em 128, ACH-160) e abre a fonte dele", async () => {
    render(<Site />);
    const placar = screen.getByRole("button", { name: /^1\/128/ });
    expect(placar).toHaveTextContent("a fraud report inside a dispute went without an agent (ACH-160)");
    expect(placar).toHaveTextContent("On the fixed commit (f57b057), the gate passed: 0 of 128.");
    expect(placar).toHaveTextContent("↗ NOV-13a");
    await userEvent.click(placar);
    expect(await screen.findByText("evidencias/NOV-13a · EV-278 · EV-283")).toBeInTheDocument();
  }, LONGO);

  it("a conversa mostra o exemplo do design, com as opções e o porquê", async () => {
    localStorage.setItem("jeje.site.locale", "pt");
    render(<Site />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Mande uma mensagem/ })).toBeEnabled());
    await userEvent.setup({ pointerEventsCheck: 0 }).click(screen.getByRole("button", { name: /Mande uma mensagem/ }));
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
  }, LONGO);
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
    localStorage.setItem("jeje.site.locale", "pt");
    render(<Site />);
    await userEvent.setup({ pointerEventsCheck: 0 }).click(screen.getByRole("button", { name: /Mande uma mensagem/ }));
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
  }, LONGO);
});

describe("a persona da conversa de verdade", () => {
  const exemplo = { valor: "1", moeda: "USD", data: "2025-01-01" };
  it("prefere a que tem exemplo para contestar; depois, a com mais de uma recusa; depois, cartão", () => {
    const a = persona({ customer_id: "A", transacoes_recusadas: 5 });
    const b = persona({ customer_id: "B", exemplo });
    const c = persona({ customer_id: "C", exemplo, cartoes_bloqueaveis: 1 });
    const d = persona({ customer_id: "D", exemplo, transacoes_recusadas: 2 });
    expect(escolherPersona([a, b, c])?.customer_id).toBe("C");
    expect(escolherPersona([a, b])?.customer_id).toBe("B");
    expect(escolherPersona([c, d])?.customer_id).toBe("D");
    expect(escolherPersona([])).toBeUndefined();
  }, LONGO);
});

describe("a janela do app (design de 03/10)", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("sem rede")))));

  const abrir = async () => {
    render(<Site />);
    await userEvent.click(screen.getAllByRole("button", { name: /Open the app/ })[0] as HTMLElement);
    const quadro = within(screen.getByRole("dialog", { name: "JEJE app" })).getByTitle("JEJE app") as HTMLIFrameElement;
    if (!quadro.contentWindow) throw new Error("o jsdom não criou a janela do app");
    return quadro.contentWindow;
  };
  const doApp = (app: Window, data: unknown, origin = location.origin) =>
    act(() => window.dispatchEvent(new MessageEvent("message", { data, origin, source: app })));

  it("a barra mostra a aba que o app avisa, só da janela dele e da própria origem", async () => {
    const app = await abrir();
    const janela = screen.getByRole("dialog", { name: "JEJE app" });
    expect(within(janela).getByText("#cliente")).toBeInTheDocument();
    await doApp(app, { type: "jeje-app-route", hash: "#atendente" }, "https://outro.example");
    await doApp(window, { type: "jeje-app-route", hash: "#atendente" });
    expect(within(janela).getByText("#cliente")).toBeInTheDocument();
    await doApp(app, { type: "jeje-app-route", hash: "#atendente" });
    expect(within(janela).getByText("#atendente")).toBeInTheDocument();
  }, LONGO);

  it("a língua trocada no site vai para o app aberto, na própria origem", async () => {
    const app = await abrir();
    const postar = vi.spyOn(app, "postMessage");
    await userEvent.click(screen.getByRole("button", { name: "PT" }));
    expect(postar).toHaveBeenCalledExactlyOnceWith({ type: "jeje-lang", lang: "pt" }, location.origin);
  }, LONGO);

  it("o ?lang= do endereço vence a língua guardada", () => {
    localStorage.setItem("jeje.site.locale", "pt");
    window.history.replaceState(null, "", "/site/?lang=es");
    render(<Site />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("No es un chatbot.");
    window.history.replaceState(null, "", "/");
  }, LONGO);
});

describe("a seção de resultados (1.5 do fechamento)", () => {
  const celula = { fracao: 0.9125 };
  const linha = (c: unknown) => Array.from({ length: 9 }, () => c);
  const ARQUIVO = { commit: "0123456789abcdef", evidencia: "EV-300", n: 80, linhas: { baseline: linha(celula), execucao1: linha({ contagem: 2, de: 80 }), execucao2: linha(null) } };
  const servir = (resultados: unknown | null) =>
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url === "/resultados/teste-final.json" && resultados !== null
          ? Promise.resolve(new Response(JSON.stringify(resultados), { status: 200 }))
          : Promise.reject(new TypeError("sem rede")),
      ),
    );

  it("sem o arquivo do teste final, a seção e o link do menu não aparecem", async () => {
    servir(null);
    const { container } = render(<Site />);
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument());
    expect(container.querySelector("#resultados")).toBeNull();
    expect(screen.queryByRole("link", { name: "Results" })).toBeNull();
  }, LONGO);

  it("com o arquivo, a tabela mostra os números de cada linha e a seção diz que acabou", async () => {
    servir(ARQUIVO);
    const { container } = render(<Site />);
    await waitFor(() => expect(container.querySelector("#resultados")).not.toBeNull());
    const secao = within(container.querySelector("#resultados") as HTMLElement);
    // As 9 células de cada linha vêm depois do rótulo dela, na grade.
    const celulas = (rotulo: string) => {
      let el: Element | null | undefined = secao.getByText(rotulo).closest("div");
      return Array.from({ length: 9 }, () => {
        el = el?.nextElementSibling;
        return el?.textContent;
      });
    };
    expect(celulas("Baseline · rules only")).toEqual(Array(9).fill("91.3%"));
    expect(celulas("System · run 1")).toEqual(Array(9).fill("2 / 80"));
    expect(celulas("System · run 2")).toEqual(Array(9).fill("—"));
    expect(secao.getByText("Done")).toBeInTheDocument();
    expect(secao.getByText(/frozen commit 0123456789ab/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Results" }).length).toBeGreaterThan(0);
  }, LONGO);

  it("com o arquivo, a tabela 2 diz o resultado do VAL-019a como saiu (negativo) e a curva do leitor no limiar entregue", async () => {
    servir(ARQUIVO);
    const { container } = render(<Site />);
    await waitFor(() => expect(container.querySelector("#resultados")).not.toBeNull());
    const secao = container.querySelector("#resultados") as HTMLElement;
    expect(secao).toHaveTextContent("first-turn accuracy goes from 71.3% with rules only to 79.3% with the system");
    expect(secao).toHaveTextContent("Undue actions rise +0.5 pp [+0.0; +1.6], and the bound exceeds 1 point: the criterion written before the test was not met");
    expect(secao).toHaveTextContent("the system automates 81.6% of first messages in ES and 78.9% in PT");
    expect(within(secao).getByText("VAL-019b")).toBeInTheDocument();
  }, LONGO);

  it("as fontes do teste final e da tabela 2 são as evidências deles, não mais pendentes", () => {
    expect(CONTEUDO_DO_MAIN.sources["VAL-019"]).toEqual(["evid", "evidencias/VAL-019 · EV-276"]);
    expect(CONTEUDO_DO_MAIN.sources["VAL-019a"]).toEqual(["evid", "evidencias/VAL-019a · EV-277"]);
  });
});
