// Gera src/api/schema.d.ts a partir do contrato versionado (contrato/openapi.json).
// Uso (via compose/make): node scripts/gerar-tipos.ts /contrato/openapi.json src/api/schema.d.ts
import { readFileSync, writeFileSync } from "node:fs";
import openapiTS, { astToString } from "openapi-typescript";

export async function gerarTipos(caminhoContrato: string): Promise<string> {
  const contrato = JSON.parse(readFileSync(caminhoContrato, "utf8"));
  return astToString(await openapiTS(contrato));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const [origem, destino] = process.argv.slice(2);
  if (!origem || !destino) throw new Error("uso: gerar-tipos.ts <contrato.json> <saida.d.ts>");
  writeFileSync(destino, await gerarTipos(origem));
}
