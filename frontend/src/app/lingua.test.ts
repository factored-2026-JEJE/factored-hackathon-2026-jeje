// A língua da interface do app ao abrir (DEV-032b): o ?lang= do site vence, e o padrão é o inglês.
import { linguaInicial, marcarDocumento } from "./lingua";

test("a língua do ?lang= vale ao abrir; sem ela, ou com uma desconhecida, o app abre em inglês", () => {
  expect(linguaInicial("?lang=es")).toBe("es");
  expect(linguaInicial("?tab=cliente&lang=pt")).toBe("pt");
  expect(linguaInicial("?lang=fr")).toBe("en");
  expect(linguaInicial("")).toBe("en");
});

test("o <html lang> acompanha a língua, com o português do Brasil", () => {
  marcarDocumento("pt");
  expect(document.documentElement.lang).toBe("pt-BR");
  marcarDocumento("es");
  expect(document.documentElement.lang).toBe("es");
});
