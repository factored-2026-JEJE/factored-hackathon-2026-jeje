// O "Por que esta resposta?" e o painel de cartões na língua da interface (ACH-167): o que a API manda
// em português ou em espanhol (quem leu, a regra AJUDA, a ação aguardar_humano, o produto do cartão).
import { textos } from "../../app/conteudo";
import { nomeDoProduto } from "../../Atendimento";
import { linhasDoPorQue, nomeDaRegra, quemLeu } from "./porQue";

test("quem leu sem palavra conhecida sai na língua da interface", () => {
  expect(quemLeu("regras (sem palavra conhecida)", textos("es"), "es")).toBe("reglas (sin palabra conocida)");
  expect(quemLeu("regras (sem palavra conhecida)", textos("en"), "en")).toBe("rules (no known word)");
});

test("a regra do não entendi tem o nome da língua da interface, e a ação de aguardar o atendente tem rótulo", () => {
  expect(nomeDaRegra("AJUDA", "es")).toBe("AYUDA");
  expect(nomeDaRegra("POL-CON-02", "es")).toBe("POL-CON-02");
  const linhas = linhasDoPorQue({ regra: "AJUDA", acao: "aguardar_humano" }, textos("en"), "en");
  expect(linhas.map(([, v]) => v)).not.toContain("aguardar_humano");
  expect(linhas[0]?.[1]).toBe("HELP");
});

test("o produto do cartão, que vem da base em espanhol, sai na língua da interface", () => {
  expect(nomeDoProduto("Tarjeta Crédito", "pt")).toBe("Cartão de crédito");
  expect(nomeDoProduto("Tarjeta Débito", "en")).toBe("Debit card");
  expect(nomeDoProduto("Tarjeta Débito", "es")).toBe("Tarjeta de débito");
  expect(nomeDoProduto("Visa Clásica", "pt")).toBe("Visa Clásica");
});
