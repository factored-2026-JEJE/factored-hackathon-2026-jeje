// Os tipos versionados precisam ser exatamente os gerados do contrato versionado:
// mudar a API (contrato) sem regenerar os tipos (make contrato) quebra aqui.
import { readFileSync } from "node:fs";
import { gerarTipos } from "../../scripts/gerar-tipos";

test("tipos gerados coincidem com o contrato versionado", async () => {
  const esperado = await gerarTipos("/contrato/openapi.json");
  const versionado = readFileSync("src/api/schema.d.ts", "utf8");
  expect(versionado).toBe(esperado);
});
