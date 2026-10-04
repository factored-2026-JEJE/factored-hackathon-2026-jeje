// O guia dos jurados (DEV-032b, 2.10): os três caminhos do design com o "Try in ES/PT", que manda a
// frase à conversa pela casca, e o caminho normal com a frase do exemplo da persona (DEV-073).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PersonaDaDemo } from "../api/cliente";
import { AreaComoTestar } from "./ComoTestar";

const COM_EXEMPLO: PersonaDaDemo = {
  customer_id: "CLI-A",
  nome: "Lucía",
  cartoes_bloqueaveis: 1,
  transacoes_recusadas: 2,
  pre_casos_recentes: 0,
  contestaveis: 3,
  exemplo: { valor: "1234.5", moeda: "USD", data: "2025-03-14" },
};

function servidor(personas: PersonaDaDemo[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(personas), { status: 200 })),
  );
}

afterEach(() => vi.unstubAllGlobals());

test("o caminho normal com a frase do exemplo da persona, e o Try manda cada frase à conversa", async () => {
  servidor([COM_EXEMPLO]);
  const experimentar = vi.fn();
  render(<AreaComoTestar versao={0} aoMudar={() => {}} experimentar={experimentar} />);
  const normal = within(screen.getByRole("article", { name: "Normal: dispute a charge" }));
  expect(await normal.findByText("“No reconozco el cobro de 1.234,50 del 14/03”")).toBeInTheDocument();
  expect(normal.getByText("“Não reconheço a cobrança de 1.234,50 do dia 14/03”")).toBeInTheDocument();
  await userEvent.click(normal.getByRole("button", { name: "Try in ES →" }));
  await userEvent.click(normal.getByRole("button", { name: "Try in PT →" }));
  const humano = within(screen.getByRole("article", { name: "Human: a stolen card" }));
  await userEvent.click(humano.getByRole("button", { name: "Try in PT →" }));
  expect(experimentar.mock.calls).toEqual([
    ["No reconozco el cobro de 1.234,50 del 14/03"],
    ["Não reconheço a cobrança de 1.234,50 do dia 14/03"],
    ["Roubaram meu cartão"],
  ]);
});

test("sem persona com exemplo, as frases do design; e o que conferir", async () => {
  servidor([{ ...COM_EXEMPLO, exemplo: null }]);
  render(<AreaComoTestar versao={0} aoMudar={() => {}} experimentar={() => {}} />);
  const ambiguo = within(screen.getByRole("article", { name: "Ambiguous: a declined purchase" }));
  expect(ambiguo.getByText("“¿Por qué rechazaron mi compra?”")).toBeInTheDocument();
  const normal = within(screen.getByRole("article", { name: "Normal: dispute a charge" }));
  expect(await normal.findByText("“No reconozco el cobro de 45,90 del 10/03”")).toBeInTheDocument();
  const conferir = within(screen.getByRole("region", { name: "What to check" }));
  expect(conferir.getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getAllByRole("article")).toHaveLength(3);
});
