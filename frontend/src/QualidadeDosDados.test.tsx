// Painel de qualidade contra respostas no formato do contrato. Stub só na fronteira de rede
// (rota única); a integração real com a API é conferida no E2E.
import { render, screen, within } from "@testing-library/react";
import type { QualidadeTabela } from "./api/cliente";
import { QualidadeDosDados } from "./QualidadeDosDados";

function responder(status: number, corpo: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/dados/qualidade"
        ? new Response(JSON.stringify(corpo), { status })
        : new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 }),
    ),
  );
}

afterEach(() => vi.unstubAllGlobals());

const RECLAMACOES: QualidadeTabela = {
  tabela: "complaints",
  raw: 67095,
  curado: 67090,
  quarentena: 4,
  copias_descartadas: 1,
  motivos: { "Q-DOMINIO:status": 4 },
  anulacoes: { "A-REF:affected_product_id": 3, "A-PROP:affected_product_id": 44570 },
  normalizacoes: {},
};

function linha(tabela: string) {
  return within(screen.getByRole("row", { name: new RegExp(`^${tabela}`) }));
}

test("mostra uma linha por tabela com contagens e anulações somadas", async () => {
  responder(200, [RECLAMACOES]);
  render(<QualidadeDosDados />);
  await screen.findByRole("heading", { name: "Qualidade dos dados" });
  const celulas = linha("complaints").getAllByRole("cell").map((c) => c.textContent);
  expect(celulas).toEqual(["67.095", "67.090", "4", "1", "44.573", "0"]);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("alerta quando raw não fecha com curado, quarentena e cópias", async () => {
  responder(200, [{ ...RECLAMACOES, curado: 60000 }]);
  render(<QualidadeDosDados />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Contagens inconsistentes em: complaints");
});

test("informa quando ainda não houve carga", async () => {
  responder(200, []);
  render(<QualidadeDosDados />);
  expect(await screen.findByText("Nenhuma carga registrada ainda.")).toBeInTheDocument();
});

test("mostra erro quando o relatório não pode ser obtido", async () => {
  responder(500, { detail: "Internal Server Error" });
  render(<QualidadeDosDados />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Relatório indisponível (Error: HTTP 500)");
});
