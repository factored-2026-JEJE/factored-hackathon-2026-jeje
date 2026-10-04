// O arquivo de resultados do teste final (1.5 do fechamento): só a forma combinada entra no site, e cada
// número sai com o separador da língua. O oráculo são os valores escritos aqui.
import { type Celula, estadoConcluido, formatarCelula, type ResultadosDoTeste, validarResultados } from "./resultados";

const linha: Celula[] = [
  { fracao: 0.9125 },
  { fracao: 0.95 },
  { fracao: 0.8 },
  { fracao: 0.0125 },
  { fracao: 0.05 },
  { contagem: 2, de: 80 },
  { fracao: 1 },
  { ms: [120, 1340] },
  { numero: 1.5, unidade: "LLM" },
];
const ARQUIVO: ResultadosDoTeste = { commit: "0123456789abcdef", evidencia: "EV-300", n: 80, linhas: { baseline: linha, execucao1: linha, execucao2: linha } };

test("o arquivo com as três linhas de nove células entra; outra forma não entra", () => {
  expect(validarResultados(ARQUIVO)).toEqual(ARQUIVO);
  expect(validarResultados({ ...ARQUIVO, linhas: { ...ARQUIVO.linhas, execucao2: linha.slice(0, 8) } })).toBeNull();
  expect(validarResultados({ ...ARQUIVO, linhas: { baseline: linha, execucao1: linha } })).toBeNull();
  expect(validarResultados({ ...ARQUIVO, linhas: { ...ARQUIVO.linhas, baseline: [{ fracao: 1.4 }, ...linha.slice(1)] } })).toBeNull();
  expect(validarResultados({ ...ARQUIVO, commit: 7 })).toBeNull();
  expect(validarResultados("<!doctype html>")).toBeNull();
});

test("cada célula sai com o separador da língua: vírgula em português e espanhol, ponto em inglês", () => {
  expect(formatarCelula({ fracao: 0.9125 }, "pt")).toBe("91,3%");
  expect(formatarCelula({ fracao: 0.9125 }, "en")).toBe("91.3%");
  expect(formatarCelula({ contagem: 2, de: 80 }, "es")).toBe("2 / 80");
  expect(formatarCelula({ ms: [120, 1340] }, "pt")).toBe("120 / 1.340 ms");
  expect(formatarCelula({ numero: 1.5, unidade: "LLM" }, "en")).toBe("1.50 LLM");
  expect(formatarCelula(null, "en")).toBe("—");
});

test("depois do teste, a seção diz que acabou, com o commit congelado e a evidência", () => {
  expect(estadoConcluido(ARQUIVO, "pt")).toEqual({
    status: "Concluído",
    nota: "O teste final rodou uma vez, no commit congelado 0123456789ab, nos 80 cenários reservados. Os números são os da evidência EV-300.",
  });
  expect(estadoConcluido(ARQUIVO, "en").status).toBe("Done");
});
