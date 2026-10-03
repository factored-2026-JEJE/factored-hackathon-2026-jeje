// A língua da primeira frase do cliente, que abre a conversa do site e a do "Try in ES/PT" do app.
import { idiomaDaFrase } from "./frasesDoCliente";

test("a língua da frase pelas marcas do português e do espanhol, e nada quando não dá para dizer", () => {
  expect(idiomaDaFrase("Roubaram meu cartão")).toBe("pt");
  expect(idiomaDaFrase("Não reconheço uma cobrança")).toBe("pt");
  expect(idiomaDaFrase("Me robaron la tarjeta")).toBe("es");
  expect(idiomaDaFrase("¿Por qué rechazaron mi compra?")).toBe("es");
  expect(idiomaDaFrase("ok")).toBeNull();
});
