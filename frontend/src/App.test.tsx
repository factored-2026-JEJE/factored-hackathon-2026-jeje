// Abas da demonstração contra um servidor que só entrega as personas (o resto fica indisponível):
// cada área tem endereço próprio, e a aba escondida continua montada. Os rótulos são os do design, em
// inglês por padrão (app/conteudo.ts).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/personas"
        ? new Response(JSON.stringify([{ customer_id: "CLI-A", nome: "Ana Souza" }]), { status: 200 })
        : new Response(JSON.stringify({}), { status: 500 }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

test("abre na aba do cliente e troca de área pelas abas, com endereço próprio", async () => {
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Talk to the bank about your transactions." })).toBeVisible();
  expect(screen.getByRole("tab", { name: "Customer" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("heading", { name: "The case arrives ready.", hidden: true })).not.toBeVisible();
  await userEvent.click(screen.getByRole("tab", { name: "Agent" }));
  expect(screen.getByRole("heading", { name: "The case arrives ready." })).toBeVisible();
  expect(screen.getByRole("region", { name: "Card blocks" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Talk to the bank about your transactions.", hidden: true })).not.toBeVisible();
  expect(window.location.hash).toBe("#agent");
});

test("o endereço escolhe a aba ao abrir, e a aba escondida continua montada", async () => {
  // Sem hashchange: a aba vem da leitura do endereço ao abrir.
  window.history.replaceState(null, "", "/#operations");
  render(<App />);
  expect(await screen.findByRole("tab", { name: "Operations" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel", { name: "Operations" })).toBeVisible();
  expect(document.getElementById("painel-cliente")).not.toBeVisible();
  // O acesso (e a conversa, depois de entrar) não é desmontado ao trocar de aba.
  expect(await screen.findByRole("button", { name: "Enter as Ana Souza →", hidden: true })).not.toBeVisible();
});

test("os endereços em português de antes abrem a mesma aba, para não quebrar os links citados", async () => {
  window.history.replaceState(null, "", "/#operacao");
  render(<App />);
  expect(await screen.findByRole("tab", { name: "Operations" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tab", { name: "Agent" })).toHaveAttribute("href", "#agent");
  expect(screen.getByRole("tab", { name: "Customer" })).toHaveAttribute("href", "#customer");
});

test("o guia dos jurados tem aba e endereço próprios (#how-to-test)", async () => {
  window.history.replaceState(null, "", "/#how-to-test");
  render(<App />);
  expect(await screen.findByRole("tab", { name: "How to test" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("heading", { name: "Three paths, in Spanish and Portuguese." })).toBeVisible();
  expect(document.getElementById("painel-cliente")).not.toBeVisible();
});

test("trocar de aba avisa o site, com o endereço da aba, só quando a aba muda", async () => {
  // O app na janela do site: o pai é outra janela, que recebe o endereço para a barra dela.
  const postMessage = vi.fn();
  vi.stubGlobal("parent", { postMessage });
  render(<App />);
  await screen.findByRole("heading", { name: "Talk to the bank about your transactions." });
  expect(postMessage).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("tab", { name: "Agent" }));
  expect(postMessage).toHaveBeenCalledExactlyOnceWith({ type: "jeje-app-route", hash: "#agent" }, window.location.origin);
  await userEvent.click(screen.getByRole("tab", { name: "How to test" }));
  expect(postMessage).toHaveBeenLastCalledWith({ type: "jeje-app-route", hash: "#how-to-test" }, window.location.origin);
  expect(postMessage).toHaveBeenCalledTimes(2);
});
