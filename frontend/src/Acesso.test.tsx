// Portão dos jurados (PRD-009) contra um servidor mínimo na fronteira de rede: quem decide é a API
// (testada no backend); aqui, a tela só abre a demonstração quando a API diz que pode.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Acesso } from "./Acesso";
import { listarPersonas } from "./api/cliente";

const CERTA = "senha-certa-dos-jurados";

/** Servidor na fronteira de rede: o acesso e uma rota protegida; `vencer` expira o cookie. */
function servidor(restrito: boolean, liberadoNoInicio: boolean) {
  const enviadas: string[] = [];
  let liberado = liberadoNoInicio;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const r = (status: number, corpo?: unknown) =>
        new Response(corpo === undefined ? null : JSON.stringify(corpo), { status });
      if (url === "/api/acesso" && init?.method === "POST") {
        const { senha } = JSON.parse(String(init.body)) as { senha: string };
        enviadas.push(senha);
        if (senha !== CERTA) return r(401, { detail: "senha_incorreta" });
        liberado = true;
        return r(204);
      }
      if (url === "/api/acesso") return r(200, { restrito, liberado });
      if (url === "/api/personas") return liberado ? r(200, []) : r(401, { detail: "acesso_restrito" });
      return r(404, { detail: "Not Found" });
    }),
  );
  return { enviadas, vencer: () => (liberado = false) };
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

test("sem senha configurada, a demonstração abre direto", async () => {
  servidor(false, true);
  render(
    <Acesso>
      <p>demonstração</p>
    </Acesso>,
  );
  expect(await screen.findByText("demonstração")).toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
});

test("com senha, só a certa abre a demonstração, que começa pelo guia dos jurados", async () => {
  const { enviadas } = servidor(true, false);
  render(
    <Acesso>
      <p>demonstração</p>
    </Acesso>,
  );
  await userEvent.type(await screen.findByLabelText("Password"), "chute");
  await userEvent.click(screen.getByRole("button", { name: "Enter" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Wrong password.");
  expect(screen.queryByText("demonstração")).not.toBeInTheDocument();
  await userEvent.clear(screen.getByLabelText("Password"));
  await userEvent.type(screen.getByLabelText("Password"), CERTA);
  await userEvent.click(screen.getByRole("button", { name: "Enter" }));
  expect(await screen.findByText("demonstração")).toBeInTheDocument();
  expect(window.location.hash).toBe("#how-to-test");
  expect(enviadas).toEqual(["chute", CERTA]);
});

test("acesso que vence no meio do uso volta para a senha", async () => {
  const { vencer } = servidor(true, true);
  render(
    <Acesso>
      <p>demonstração</p>
    </Acesso>,
  );
  expect(await screen.findByText("demonstração")).toBeInTheDocument();
  vencer();
  await expect(listarPersonas()).rejects.toThrow("acesso dos jurados");
  expect(await screen.findByLabelText("Password")).toBeInTheDocument();
  expect(screen.queryByText("demonstração")).not.toBeInTheDocument();
});
