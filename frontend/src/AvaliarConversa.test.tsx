// Avaliação da conversa contra um servidor mínimo na fronteira de rede: a tela só aparece quando a
// API lista testadores, envia exatamente o que foi escolhido e mostra a Issue que a API devolveu.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AvaliarConversa } from "./AvaliarConversa";

function servidor(testadores: { status: number; corpo: unknown }, review = { status: 201, corpo: {} as unknown }) {
  const enviados: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const r = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
      if (url === "/api/testadores") return r(testadores.status, testadores.corpo);
      if (url === "/api/conversas/C1/reviews" && init?.method === "POST") {
        enviados.push(JSON.parse(String(init.body)));
        return r(review.status, review.corpo);
      }
      return r(404, { detail: "Not Found" });
    }),
  );
  return enviados;
}

const TIME = { status: 200, corpo: ["enzo200325", "Prism411"] };

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

async function preencher(testador = "Prism411") {
  const u = userEvent.setup();
  await u.selectOptions(await screen.findByLabelText("Quem está testando"), testador);
  await u.click(screen.getByRole("button", { name: "2" }));
  await u.click(screen.getByRole("button", { name: "Não resolveu" }));
  await u.type(screen.getByLabelText("O que deu errado ou como deveria ter sido"), "Pediu o valor de novo.");
  return u;
}

test("fora do modo de demonstração (sem testadores) não mostra nada", async () => {
  servidor({ status: 404, corpo: { detail: "Not Found" } });
  const { container } = render(<AvaliarConversa token="T" conversaId="C1" aoExpirar={() => {}} />);
  await act(async () => {
    await new Promise((ok) => setTimeout(ok, 0));
  });
  expect(container).toBeEmptyDOMElement();
});

test("envia o que foi escolhido e mostra a Issue devolvida pela API", async () => {
  const enviados = servidor(TIME, { status: 201, corpo: { review_id: 1, issue_url: "https://github.com/o/r/issues/7" } });
  render(<AvaliarConversa token="T" conversaId="C1" aoExpirar={() => {}} />);
  const u = await preencher();
  await u.click(screen.getByRole("button", { name: "Registrar avaliação" }));
  expect(enviados).toEqual([{ avaliador: "Prism411", nota: 2, resolveu: "nao", comentario: "Pediu o valor de novo." }]);
  expect(await screen.findByRole("link", { name: "Ver a Issue" })).toHaveAttribute("href", "https://github.com/o/r/issues/7");
});

test("só envia com quem testa, a nota e se resolveu escolhidos", async () => {
  servidor(TIME);
  render(<AvaliarConversa token="T" conversaId="C1" aoExpirar={() => {}} />);
  const u = userEvent.setup();
  const enviar = await screen.findByRole("button", { name: "Registrar avaliação" });
  expect(enviar).toBeDisabled();
  await u.selectOptions(screen.getByLabelText("Quem está testando"), "enzo200325");
  await u.click(screen.getByRole("button", { name: "5" }));
  expect(enviar).toBeDisabled();
  await u.click(screen.getByRole("button", { name: "Resolveu" }));
  expect(enviar).toBeEnabled();
});

test("lembra quem está testando na próxima conversa", async () => {
  servidor(TIME, { status: 201, corpo: { review_id: 1, issue_url: null } });
  const { unmount } = render(<AvaliarConversa token="T" conversaId="C1" aoExpirar={() => {}} />);
  const u = await preencher("enzo200325");
  await u.click(screen.getByRole("button", { name: "Registrar avaliação" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Review enviada");
  expect(screen.queryByRole("link")).toBeNull();
  unmount();
  render(<AvaliarConversa token="T" conversaId="C2" aoExpirar={() => {}} />);
  expect(await screen.findByLabelText("Quem está testando")).toHaveValue("enzo200325");
});

test("falha ao enviar avisa e deixa tentar de novo", async () => {
  servidor(TIME, { status: 500, corpo: {} });
  render(<AvaliarConversa token="T" conversaId="C1" aoExpirar={() => {}} />);
  const u = await preencher();
  await u.click(screen.getByRole("button", { name: "Registrar avaliação" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível enviar a review");
  expect(screen.getByRole("button", { name: "Registrar avaliação" })).toBeEnabled();
});

test("sessão expirada ao enviar volta para a escolha do cliente", async () => {
  servidor(TIME, { status: 401, corpo: { detail: "Sessão inválida ou expirada" } });
  const aoExpirar = vi.fn();
  render(<AvaliarConversa token="T" conversaId="C1" aoExpirar={aoExpirar} />);
  const u = await preencher();
  await u.click(screen.getByRole("button", { name: "Registrar avaliação" }));
  await vi.waitFor(() => expect(aoExpirar).toHaveBeenCalledOnce());
});
