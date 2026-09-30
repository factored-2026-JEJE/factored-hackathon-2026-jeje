// Abas da demonstração contra um servidor que só entrega as personas (o resto fica indisponível):
// cada área tem endereço próprio, e a aba escondida continua montada.
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
  expect(await screen.findByRole("heading", { name: "Acesso de teste" })).toBeVisible();
  expect(screen.getByRole("tab", { name: "Cliente" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("heading", { name: "Fila do atendimento humano", hidden: true })).not.toBeVisible();
  await userEvent.click(screen.getByRole("tab", { name: "Atendente" }));
  expect(screen.getByRole("heading", { name: "Fila do atendimento humano" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Bloqueios de cartão" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Acesso de teste", hidden: true })).not.toBeVisible();
  expect(window.location.hash).toBe("#atendente");
});

test("o endereço escolhe a aba ao abrir, e a aba escondida continua montada", async () => {
  // Sem hashchange: a aba vem da leitura do endereço ao abrir.
  window.history.replaceState(null, "", "/#operacao");
  render(<App />);
  expect(await screen.findByRole("tab", { name: "Operação" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("tabpanel", { name: "Operação" })).toBeVisible();
  expect(document.getElementById("painel-cliente")).not.toBeVisible();
  // O acesso (e a conversa, depois de entrar) não é desmontado ao trocar de aba.
  expect(await screen.findByRole("button", { name: "Entrar como Ana Souza", hidden: true })).not.toBeVisible();
});
