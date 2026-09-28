// Seção da EDA contra respostas no formato do contrato (stub só na rota; E2E confere a API real).
import { render, screen, within } from "@testing-library/react";
import type { IndicadorEda } from "./api/cliente";
import { IndicadoresDaEda } from "./IndicadoresDaEda";

function responder(status: number, corpo: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/dados/eda"
        ? new Response(JSON.stringify(corpo), { status })
        : new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

const MOTIVOS: IndicadorEda = {
  id: "motivos-de-contato",
  pergunta: "Qual motivo concentra os contatos e o tempo de atendimento?",
  tipo: "distribuicao",
  consulta: "SELECT reason_category AS grupo FROM raw.call_center_interactions",
  unidade_soma: "segundos de atendimento",
  linhas: [
    { grupo: "Transaccional", contagem: 240056, base: 686296, proporcao: 0.34979, soma: 1, proporcao_soma: 0.2403 },
  ],
};
const RESOLUCAO: IndicadorEda = {
  id: "resolucao-por-motivo",
  pergunta: "Em que motivos o primeiro contato já resolve?",
  tipo: "taxa",
  consulta: "SELECT 1",
  unidade_soma: null,
  linhas: [{ grupo: "Queja", contagem: 51021, base: 117021, proporcao: 0.436, soma: null, proporcao_soma: null }],
};

function linhaDe(pergunta: string, grupo: string) {
  const artigo = screen.getByRole("article", { name: pergunta });
  return within(within(artigo).getByRole("row", { name: new RegExp(`^${grupo}`) }))
    .getAllByRole("cell")
    .map((celula) => celula.textContent);
}

test("distribuição mostra contagem, participação e participação no tempo", async () => {
  responder(200, [MOTIVOS]);
  render(<IndicadoresDaEda />);
  await screen.findByRole("heading", { name: "Por que este fluxo" });
  expect(linhaDe(MOTIVOS.pergunta, "Transaccional")).toEqual(["240.056", "35,0%", "24,0%"]);
});

test("taxa mostra numerador e base do próprio grupo", async () => {
  responder(200, [RESOLUCAO]);
  render(<IndicadoresDaEda />);
  await screen.findByRole("heading", { name: "Por que este fluxo" });
  expect(linhaDe(RESOLUCAO.pergunta, "Queja")).toEqual(["51.021 de 117.021", "43,6%"]);
});

test("cada indicador traz a consulta que o produziu", async () => {
  responder(200, [MOTIVOS]);
  render(<IndicadoresDaEda />);
  const artigo = await screen.findByRole("article", { name: MOTIVOS.pergunta });
  expect(within(artigo).getByText(MOTIVOS.consulta)).toBeInTheDocument();
});

test("mostra erro quando os indicadores não podem ser obtidos", async () => {
  responder(503, { detail: "indisponível" });
  render(<IndicadoresDaEda />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Indicadores indisponíveis (Error: HTTP 503)");
});
