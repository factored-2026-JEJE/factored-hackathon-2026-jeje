// Página de status contra respostas HTTP reais no formato do contrato. O único stub é o `fetch`
// (fronteira de rede); a integração real com a API é verificada no E2E.
import { render, screen } from "@testing-library/react";
import type { Prontidao } from "./api/cliente";
import { StatusDoSistema } from "./StatusDoSistema";

// Servidor mínimo na fronteira de rede: só a rota da readiness existe; o resto é 404.
function responder(status: number, corpo: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/health/ready"
        ? new Response(JSON.stringify(corpo), { status })
        : new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

test("mostra pronto com versão e origem do dataset", async () => {
  const corpo: Prontidao = {
    status: "ready",
    database: "ok",
    dataset: { version: "abc123def456789", source: "s3", loaded_at: "2026-09-28T03:00:00Z" },
  };
  responder(200, corpo);
  render(<StatusDoSistema />);
  expect(await screen.findByRole("heading", { name: "Pronto para atender" })).toBeInTheDocument();
  expect(screen.getByText(/versão abc123def456 \(s3\)/)).toBeInTheDocument();
  expect(screen.getByText("conectado")).toBeInTheDocument();
});

test("mostra indisponível e banco sem migrations quando a API responde 503", async () => {
  responder(503, { status: "unavailable", database: "not_migrated", dataset: null });
  render(<StatusDoSistema />);
  expect(await screen.findByRole("heading", { name: "Indisponível" })).toBeInTheDocument();
  expect(screen.getByText("sem migrations aplicadas")).toBeInTheDocument();
});

test("mostra que os dados estão sendo recarregados quando a API está em recarga", async () => {
  responder(503, { status: "unavailable", database: "reloading", dataset: null });
  render(<StatusDoSistema />);
  expect(await screen.findByRole("heading", { name: "Indisponível" })).toBeInTheDocument();
  expect(screen.getByText("recarregando os dados")).toBeInTheDocument();
});

test("mostra nenhum dataset quando o banco está ok mas sem carga", async () => {
  responder(503, { status: "unavailable", database: "ok", dataset: null });
  render(<StatusDoSistema />);
  expect(await screen.findByText("nenhum dataset carregado")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Indisponível" })).toBeInTheDocument();
});

test("mostra API inacessível quando a requisição falha na rede", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }),
  );
  render(<StatusDoSistema />);
  expect(await screen.findByRole("alert")).toHaveTextContent("API inacessível");
});

test("trata status HTTP fora do contrato como erro", async () => {
  responder(500, { detail: "Internal Server Error" });
  render(<StatusDoSistema />);
  expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 500");
});

test("mostra verificando enquanto a API não responde", () => {
  vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
  render(<StatusDoSistema />);
  expect(screen.getByRole("status")).toHaveTextContent("Verificando o sistema");
});
