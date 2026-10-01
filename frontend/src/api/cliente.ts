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
/** Persona da lista de acesso, com as dicas de cada caminho da demonstração (PRD-009). */
export type PersonaDaDemo = components["schemas"]["PersonaDaDemo"];
export type SessaoAberta = components["schemas"]["SessaoAberta"];
export type Transacao = components["schemas"]["Transacao"];

/** Sessão recusada pela API (ausente, inválida ou expirada). */
export class SessaoExpirada extends Error {}

/** Acesso dos jurados ausente ou vencido (PRD-009): a tela volta para a senha. */
export class AcessoRestrito extends Error {}

/** Evento da janela que o portão (Acesso.tsx) escuta quando a API recusa por falta do acesso. */
export const ACESSO_RESTRITO = "jeje:acesso-restrito";

/** Pedido recusado por regra de negócio (ex.: proposta vencida), com a explicação da API. */
export class Recusado extends Error {}

async function json<T>(resposta: Response, ...esperados: number[]): Promise<T> {
  if (resposta.status === 401) {
    // O portão dos jurados recusa antes da sessão: a tela pede a senha de novo, sem sair da sessão.
    const corpo = (await resposta.json().catch(() => null)) as { detail?: unknown } | null;
    if (corpo?.detail === "acesso_restrito") {
      window.dispatchEvent(new Event(ACESSO_RESTRITO));
      throw new AcessoRestrito("acesso dos jurados ausente ou vencido");
    }
    throw new SessaoExpirada("sessão expirada");
  }
  if (resposta.status === 409) throw new Recusado(((await resposta.json()) as { detail: string }).detail);
  if (!esperados.includes(resposta.status)) throw new Error(`HTTP ${resposta.status}`);
  return (await resposta.json()) as T;
}

const comToken = (token: string) => ({ Authorization: `Bearer ${token}` });

export async function listarPersonas(): Promise<PersonaDaDemo[]> {
  return json<PersonaDaDemo[]>(await fetch("/api/personas"), 200);
}

/** Dispositivo simulado da sessão de teste (PRD-007): escolhido no acesso, nunca pelo chat. */
export type Dispositivo = "cadastrado" | "novo";
export type SessaoAtual = components["schemas"]["SessaoAtual"];

export async function abrirSessao(customerId: string, dispositivo: Dispositivo): Promise<SessaoAberta> {
  const resposta = await fetch("/api/sessoes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ customer_id: customerId, dispositivo }),
  });
  return json<SessaoAberta>(resposta, 201);
}

export async function sessaoAtual(token: string): Promise<SessaoAtual> {
  return json<SessaoAtual>(await fetch("/api/sessao", { headers: comToken(token) }), 200);
}

export async function minhasTransacoes(token: string): Promise<Transacao[]> {
  return json<Transacao[]>(await fetch("/api/minhas/transacoes", { headers: comToken(token) }), 200);
}

export type AvaliacaoDeContestacao = components["schemas"]["AvaliacaoDeContestacao"];
export type PreCaso = components["schemas"]["PreCaso"];

export async function proporContestacao(token: string, transacaoId: string): Promise<AvaliacaoDeContestacao> {
  const url = `/api/minhas/transacoes/${encodeURIComponent(transacaoId)}/contestacao/proposta`;
  return json<AvaliacaoDeContestacao>(await fetch(url, { method: "POST", headers: comToken(token) }), 200, 201);
}

export async function confirmarProposta(token: string, propostaId: string): Promise<PreCaso> {
  const url = `/api/minhas/propostas/${encodeURIComponent(propostaId)}/confirmacao`;
  return json<PreCaso>(await fetch(url, { method: "POST", headers: comToken(token) }), 200, 201);
}

export async function meusPreCasos(token: string): Promise<PreCaso[]> {
  return json<PreCaso[]>(await fetch("/api/minhas/pre-casos", { headers: comToken(token) }), 200);
}

export type Idioma = "es" | "pt";
export type ConversaAberta = components["schemas"]["ConversaAberta"];
export type ResultadoDoTurno = components["schemas"]["ResultadoDoTurno"];
export type Historico = components["schemas"]["Historico"];
export type Encaminhamento = components["schemas"]["Encaminhamento"];
export type Metricas = components["schemas"]["Metricas"];

/** Turno não registrado (503): a API desfez tudo, e reenviar a mesma mensagem é seguro. */
export class NaoRegistrado extends Error {}

const jsonComToken = (token: string) => ({ ...comToken(token), "Content-Type": "application/json" });

export async function abrirConversa(token: string, idioma: Idioma): Promise<ConversaAberta> {
  const resposta = await fetch("/api/conversas", {
    method: "POST",
    headers: jsonComToken(token),
    body: JSON.stringify({ idioma }),
  });
  return json<ConversaAberta>(resposta, 201);
}

export async function enviarMensagem(token: string, conversaId: string, texto: string): Promise<ResultadoDoTurno> {
  const resposta = await fetch(`/api/conversas/${encodeURIComponent(conversaId)}/turnos`, {
    method: "POST",
    headers: jsonComToken(token),
    body: JSON.stringify({ texto }),
  });
  if (resposta.status === 503) throw new NaoRegistrado(((await resposta.json()) as { detail: string }).detail);
  return json<ResultadoDoTurno>(resposta, 200);
}

/** Histórico da conversa guardada nesta aba; `null` se ela não existe (ou não é desta sessão). */
export async function historicoDaConversa(token: string, conversaId: string): Promise<Historico | null> {
  const resposta = await fetch(`/api/conversas/${encodeURIComponent(conversaId)}`, { headers: comToken(token) });
  if (resposta.status === 404) return null;
  return json<Historico>(resposta, 200);
}

export async function filaDoAtendimento(): Promise<Encaminhamento[]> {
  return json<Encaminhamento[]>(await fetch("/api/atendimento/fila"), 200);
}

/** O atendente assume o encaminhamento; 409 (já assumido) vira `Recusado` com a explicação. */
export async function assumirEncaminhamento(id: string): Promise<Encaminhamento> {
  const resposta = await fetch(`/api/atendimento/fila/${encodeURIComponent(id)}/assumir`, { method: "POST" });
  return json<Encaminhamento>(resposta, 200);
}

export type BloqueioDeCartao = components["schemas"]["BloqueioDeCartao"];

export async function bloqueiosDoAtendimento(): Promise<BloqueioDeCartao[]> {
  return json<BloqueioDeCartao[]>(await fetch("/api/atendimento/bloqueios?limite=100"), 200);
}

/** O atendente desfaz o bloqueio; 409 (já desfeito) vira `Recusado` com a explicação. */
export async function desbloquearCartao(id: string): Promise<BloqueioDeCartao> {
  const resposta = await fetch(`/api/atendimento/bloqueios/${encodeURIComponent(id)}/desbloqueio`, {
    method: "POST",
  });
  return json<BloqueioDeCartao>(resposta, 200);
}

export async function buscarMetricas(): Promise<Metricas> {
  return json<Metricas>(await fetch("/api/metricas"), 200);
}

export type PedidoDeReview = components["schemas"]["PedidoDeReview"];
export type ReviewRegistrada = components["schemas"]["ReviewRegistrada"];

/** Quem do time pode avaliar conversas; fora do modo de demonstração (404), ninguém. */
export async function listarTestadores(): Promise<string[]> {
  const resposta = await fetch("/api/testadores");
  if (resposta.status === 404) return [];
  return json<string[]>(resposta, 200);
}

export async function avaliarConversa(
  token: string,
  conversaId: string,
  review: PedidoDeReview,
): Promise<ReviewRegistrada> {
  const resposta = await fetch(`/api/conversas/${encodeURIComponent(conversaId)}/reviews`, {
    method: "POST",
    headers: jsonComToken(token),
    body: JSON.stringify(review),
  });
  return json<ReviewRegistrada>(resposta, 201);
}

export type SituacaoDoAcesso = components["schemas"]["SituacaoDoAcesso"];

/** Se a demonstração pede a senha dos jurados e se quem pergunta já entrou (PRD-009). */
export async function situacaoDoAcesso(): Promise<SituacaoDoAcesso> {
  const resposta = await fetch("/api/acesso");
  if (resposta.status !== 200) throw new Error(`HTTP ${resposta.status}`);
  return (await resposta.json()) as SituacaoDoAcesso;
}

/** Entra com a senha dos jurados: a API devolve o cookie de acesso; senha errada, `false`. */
export async function entrarComSenha(senha: string): Promise<boolean> {
  const resposta = await fetch("/api/acesso", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ senha }),
  });
  if (resposta.status === 204) return true;
  if (resposta.status === 401) return false;
  throw new Error(`HTTP ${resposta.status}`);
}
