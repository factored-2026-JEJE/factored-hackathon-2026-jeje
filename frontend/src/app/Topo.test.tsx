// A barra do topo do app (DEV-032b) contra um servidor mínimo na fronteira de rede: os casos na fila,
// a sessão de teste e a língua. A integração real é conferida no E2E.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LinguaDoAppProvider } from "./LinguaDoApp";
import { SessaoProvider } from "./sessao";
import { Topo } from "./Topo";

let naFila: unknown[] = [];

beforeEach(() => {
  naFila = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/atendimento/fila") return new Response(JSON.stringify(naFila), { status: 200 });
      if (url === "/api/sessao") {
        return new Response(JSON.stringify({ customer_id: "CLI-A", nome: "Ana Souza", dispositivo: "cadastrado" }), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 500 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

const topo = (versao: number) => (
  <LinguaDoAppProvider>
    <SessaoProvider>
      <Topo aba="cliente" versao={versao} aoEscolher={() => {}} />
    </SessaoProvider>
  </LinguaDoAppProvider>
);

test("a aba do atendente mostra quantos casos esperam, relidos a cada efeito da conversa", async () => {
  naFila = [{ id: "AT-1" }, { id: "AT-2" }];
  const { rerender } = render(topo(0));
  const atendente = screen.getByRole("tab", { name: /^Agent/ });
  expect(await within(atendente).findByText("2")).toBeVisible();
  naFila = [{ id: "AT-1" }, { id: "AT-2" }, { id: "AT-3" }];
  rerender(topo(1));
  expect(await within(atendente).findByText("3")).toBeVisible();
  naFila = [];
  rerender(topo(2));
  await vi.waitFor(() => expect(atendente).toHaveTextContent(/^Agent$/));
});

test("quem está na sessão aparece no topo, e o Leave a encerra", async () => {
  sessionStorage.setItem("jeje.sessao", "tok-ana");
  render(topo(0));
  expect(await screen.findByText("CLI-A · Ana Souza · registered device")).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "Leave" }));
  expect(screen.queryByText(/Ana Souza/)).toBeNull();
  expect(sessionStorage.getItem("jeje.sessao")).toBeNull();
});

test("a língua da barra troca os rótulos e o <html lang>", async () => {
  render(topo(0));
  expect(screen.getByRole("tab", { name: "Customer" })).toBeVisible();
  await userEvent.click(screen.getByRole("button", { name: "ES" }));
  expect(screen.getByRole("tab", { name: "Cliente" })).toBeVisible();
  expect(screen.getByRole("tab", { name: "Cómo probar" })).toBeVisible();
  expect(document.documentElement.lang).toBe("es");
  await userEvent.click(screen.getByRole("button", { name: "PT" }));
  expect(screen.getByRole("tab", { name: "Atendente" })).toBeVisible();
  expect(screen.getByRole("button", { name: "PT" })).toHaveAttribute("aria-pressed", "true");
  expect(document.documentElement.lang).toBe("pt-BR");
});

test("a língua escolhida no site chega à barra do app aberto na janela dele", async () => {
  // O pai é outra janela de verdade (o site); a mensagem dele, na própria origem, troca a língua.
  const moldura = document.createElement("iframe");
  document.body.append(moldura);
  const site = moldura.contentWindow;
  if (!site) throw new Error("o jsdom não criou a janela da moldura");
  vi.stubGlobal("parent", site);
  render(topo(0));
  expect(screen.getByRole("tab", { name: "Customer" })).toBeVisible();
  window.dispatchEvent(new MessageEvent("message", { data: { type: "jeje-lang", lang: "pt" }, origin: window.location.origin, source: site }));
  expect(await screen.findByRole("tab", { name: "Cliente" })).toBeVisible();
  expect(screen.getByRole("tab", { name: "Como testar" })).toBeVisible();
  moldura.remove();
});
