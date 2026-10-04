// Os formatos do console (DEV-032b, 2.10), os do design: a hora local em HH:MM:SS, o dia em dd/mm e
// os números com o separador da língua (o money() do design põe o ponto no milhar em ES e PT).
import { diaMes, dinheiro, hora, numero, percentual } from "./formato";

test("a hora local em HH:MM:SS, e o que não é data vira traço", () => {
  const local = new Date(2026, 9, 3, 7, 5, 9).toISOString();
  expect(hora(local)).toBe("07:05:09");
  expect(hora("não é data")).toBe("—");
});

test("o dia em dd/mm, da data ou do instante", () => {
  expect(diaMes("2025-03-14")).toBe("14/03");
  expect(diaMes("2025-03-04T23:59:00")).toBe("04/03");
  expect(diaMes("")).toBe("—");
});

test("o dinheiro com duas casas, no separador de cada língua", () => {
  expect(dinheiro("1234567.5", "en")).toBe("1,234,567.50");
  expect(dinheiro("1234567.5", "es")).toBe("1.234.567,50");
  expect(dinheiro(45.9, "pt")).toBe("45,90");
  expect(dinheiro("abc", "pt")).toBe("abc");
});

test("as contagens e as proporções no mesmo separador", () => {
  expect(numero(4425008, "en")).toBe("4,425,008");
  expect(numero(4425008, "es")).toBe("4.425.008");
  expect(percentual(0.915, "en")).toBe("91.5%");
  expect(percentual(0.915, "pt")).toMatch(/^91,5\s?%$/);
  expect(percentual(null, "es")).toBe("—");
});
