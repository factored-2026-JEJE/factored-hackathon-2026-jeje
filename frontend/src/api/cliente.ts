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

export type QualidadeTabela = components["schemas"]["QualidadeTabela"];

/** Relatório da curadoria da última carga (uma linha por tabela curada). */
export async function buscarQualidade(sinal?: AbortSignal): Promise<QualidadeTabela[]> {
  const resposta = await fetch("/api/dados/qualidade", { signal: sinal });
  if (resposta.status !== 200) throw new Error(`HTTP ${resposta.status}`);
  return (await resposta.json()) as QualidadeTabela[];
}

export type IndicadorEda = components["schemas"]["Resultado"];

/** Indicadores da EDA calculados sobre a carga atual, cada um com a consulta que o produziu. */
export async function buscarEda(sinal?: AbortSignal): Promise<IndicadorEda[]> {
  const resposta = await fetch("/api/dados/eda", { signal: sinal });
  if (resposta.status !== 200) throw new Error(`HTTP ${resposta.status}`);
  return (await resposta.json()) as IndicadorEda[];
}

export type Persona = components["schemas"]["Persona"];
export type SessaoAberta = components["schemas"]["SessaoAberta"];
export type Transacao = components["schemas"]["Transacao"];

/** Sessão recusada pela API (ausente, inválida ou expirada). */
export class SessaoExpirada extends Error {}

async function json<T>(resposta: Response, esperado: number): Promise<T> {
  if (resposta.status === 401) throw new SessaoExpirada("sessão expirada");
  if (resposta.status !== esperado) throw new Error(`HTTP ${resposta.status}`);
  return (await resposta.json()) as T;
}

const comToken = (token: string) => ({ Authorization: `Bearer ${token}` });

export async function listarPersonas(): Promise<Persona[]> {
  return json<Persona[]>(await fetch("/api/personas"), 200);
}

export async function abrirSessao(customerId: string): Promise<SessaoAberta> {
  const resposta = await fetch("/api/sessoes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_id: customerId }),
  });
  return json<SessaoAberta>(resposta, 201);
}

export async function sessaoAtual(token: string): Promise<Persona> {
  return json<Persona>(await fetch("/api/sessao", { headers: comToken(token) }), 200);
}

export async function minhasTransacoes(token: string): Promise<Transacao[]> {
  return json<Transacao[]>(await fetch("/api/minhas/transacoes", { headers: comToken(token) }), 200);
}
