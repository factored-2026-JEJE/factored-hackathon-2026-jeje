// O guia dos jurados (PRD-009): os três caminhos com as frases nas duas línguas e o caminho até
// cada aba. As respostas em si vêm da API (testadas no backend e no E2E).
import { render, screen } from "@testing-library/react";
import { ComoTestar } from "./ComoTestar";

test("o guia mostra os três caminhos em espanhol e português e leva a cada aba", () => {
  render(<ComoTestar />);
  expect(screen.getByRole("heading", { name: "How to test this demo" })).toBeInTheDocument();
  for (const caminho of ["Normal path: contest a charge", "Ambiguous path", "Human path"]) {
    expect(screen.getByRole("heading", { name: caminho })).toBeInTheDocument();
  }
  // O exemplo da contestação é de cada persona (DEV-073), não uma transação da fixture.
  expect(screen.queryByText(/45,90/)).not.toBeInTheDocument();
  expect(screen.getByText(/the customer list shows a ready sentence for each customer/)).toBeInTheDocument();
  for (const frase of [
    "¿Por qué rechazaron mi compra?",
    "Por que recusaram minha compra?",
    "Me robaron la tarjeta",
    "Roubaram meu cartão",
  ]) {
    expect(screen.getByText(frase)).toBeInTheDocument();
  }
  expect(screen.getByRole("link", { name: "Cliente" })).toHaveAttribute("href", "#cliente");
  expect(screen.getByRole("link", { name: "Atendente" })).toHaveAttribute("href", "#atendente");
  expect(screen.getByRole("link", { name: "Operação" })).toHaveAttribute("href", "#operacao");
});
