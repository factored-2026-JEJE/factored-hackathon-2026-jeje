// Cliente HTTP do frontend. Tipos vêm do contrato gerado (schema.d.ts), nunca reescritos à mão.
import type { components } from "./schema";

export type Prontidao = components["schemas"]["Readiness"];

/** Readiness real da API. 200 (pronta) e 503 (indisponível) trazem o mesmo corpo `Readiness`. */
export async function buscarProntidao(sinal?: AbortSignal): Promise<Prontidao> {
  const resposta = await fetch("/api/health/ready", { signal: sinal });
  if (resposta.status !== 200 && resposta.status !== 503) {
    throw new Error(`HTTP ${resposta.status}`);
  }
  return (await resposta.json()) as Prontidao;
}
