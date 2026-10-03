// Os números do site lidos da API do produto (DEV-032a): a EDA, a carga dos dados e o portão TF-IDF.
// Quando a API não responde (o site aberto sem a senha dos jurados, por exemplo), ficam os valores do
// design, que são os das evidências citadas em cada número (DADOS-08, a qualidade da carga e o README).
import { buscarEda, buscarModeloDeIntencao, buscarQualidade, type IndicadorEda, type QualidadeTabela } from "../api/cliente";
import type { Conteudo, Idioma, Resolvido } from "./conteudo";

export interface NumerosAoVivo {
  /** Contatos de motivo transacional: a parte dos atendimentos, a base e a parte do tempo. */
  readonly contatos: { readonly proporcao: number; readonly base: number; readonly tempo: number } | null;
  /** Transacionais resolvidos no primeiro contato. */
  readonly primeiroContato: number | null;
  /** "Cargo no reconocido" entre as reclamações de transação. */
  readonly cargoNaoReconhecido: number | null;
  readonly carga: { readonly transacoes: number; readonly clientes: number; readonly reclamacoes: number } | null;
  /** Acurácia do portão TF-IDF no teste do BANKING77, por idioma. */
  readonly tfidf: { readonly es: number; readonly pt: number } | null;
}

export const SEM_NUMEROS: NumerosAoVivo = { contatos: null, primeiroContato: null, cargoNaoReconhecido: null, carga: null, tfidf: null };

/** Os valores que o design mostra, os mesmos das evidências; o texto ao vivo troca exatamente estes. */
export const VALORES_DO_DESIGN = {
  contatos: { proporcao: 0.35, base: 686296, tempo: 0.24 },
  primeiroContato: 0.915,
  cargoNaoReconhecido: 0.906,
  carga: { transacoes: 4425008, clientes: 150000, reclamacoes: 67095 },
  tfidf: { es: 0.892, pt: 0.896 },
} as const;

const linha = (indicadores: readonly IndicadorEda[], id: string, grupo: string) =>
  indicadores.find((i) => i.id === id)?.linhas.find((l) => l.grupo === grupo);

/** Os números do problema na EDA ao vivo (as mesmas consultas que a aba Operação mostra). */
export function daEda(indicadores: readonly IndicadorEda[]): Pick<NumerosAoVivo, "contatos" | "primeiroContato" | "cargoNaoReconhecido"> {
  const transacional = linha(indicadores, "motivos-de-contato", "Transaccional");
  const resolvidos = linha(indicadores, "resolucao-por-motivo", "Transaccional");
  const cargo = linha(indicadores, "reclamacoes-de-transacao", "Cargo no reconocido");
  return {
    contatos:
      transacional && transacional.proporcao != null && transacional.proporcao_soma != null
        ? { proporcao: transacional.proporcao, base: transacional.base, tempo: transacional.proporcao_soma }
        : null,
    primeiroContato: resolvidos?.proporcao ?? null,
    cargoNaoReconhecido: cargo?.proporcao ?? null,
  };
}

/** O tamanho da carga atual, pela qualidade de cada tabela curada. */
export function daQualidade(tabelas: readonly QualidadeTabela[]): NumerosAoVivo["carga"] {
  const curado = (nome: string) => tabelas.find((t) => t.tabela === nome)?.curado;
  const transacoes = curado("transactions");
  const clientes = curado("customers");
  const reclamacoes = curado("complaints");
  return transacoes != null && clientes != null && reclamacoes != null ? { transacoes, clientes, reclamacoes } : null;
}

/** Lê o que a API tiver; cada parte que falhar fica sem número ao vivo. */
export async function lerNumerosAoVivo(sinal?: AbortSignal): Promise<NumerosAoVivo> {
  const [eda, qualidade, modelo] = await Promise.allSettled([buscarEda(sinal), buscarQualidade(sinal), buscarModeloDeIntencao(sinal)]);
  const es = modelo.status === "fulfilled" ? modelo.value.metricas_teste.es?.acuracia : undefined;
  const pt = modelo.status === "fulfilled" ? modelo.value.metricas_teste.pt?.acuracia : undefined;
  return {
    ...(eda.status === "fulfilled" ? daEda(eda.value) : { contatos: null, primeiroContato: null, cargoNaoReconhecido: null }),
    carga: qualidade.status === "fulfilled" ? daQualidade(qualidade.value) : null,
    tfidf: es != null && pt != null ? { es, pt } : null,
  };
}

// O formato do design: em português e espanhol, milhar com ponto e decimal com vírgula; em inglês, o
// contrário. As acurácias das barras vêm sempre com vírgula, como no design ("0,892").
const local = (idioma: Idioma) => (idioma === "en" ? "en-US" : "pt-BR");
export const porcento = (p: number, idioma: Idioma) =>
  (p * 100).toLocaleString(local(idioma), { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + "%";
export const inteiro = (n: number, idioma: Idioma) => n.toLocaleString(local(idioma));
export const acuracia = (a: number) => a.toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

/**
 * O conteúdo com os números ao vivo no lugar dos do design: cada número trocado é o mesmo valor do
 * design formatado no idioma, então, com a API dando o que as evidências dizem, nada muda na tela.
 */
export function comNumerosAoVivo(t: Resolvido<Conteudo>, n: NumerosAoVivo, idioma: Idioma): Resolvido<Conteudo> {
  const D = VALORES_DO_DESIGN;
  const pc = (p: number) => porcento(p, idioma);
  const nr = (x: number) => inteiro(x, idioma);
  const stats = t.problem.stats.map((s, i) => {
    if (i === 0 && n.contatos) return { ...s, v: pc(n.contatos.proporcao), l: s.l.replace(nr(D.contatos.base), nr(n.contatos.base)) };
    if (i === 1 && n.contatos) return { ...s, v: pc(n.contatos.tempo) };
    if (i === 2 && n.primeiroContato != null) return { ...s, v: pc(n.primeiroContato) };
    if (i === 3 && n.cargoNaoReconhecido != null) return { ...s, v: pc(n.cargoNaoReconhecido) };
    return s;
  });
  const dataStops = t.dataStops.map((s) => {
    if (s.id !== "versao" || !s.stat || !n.carga) return s;
    const l = s.stat.l.replace(nr(D.carga.clientes), nr(n.carga.clientes)).replace(nr(D.carga.reclamacoes), nr(n.carga.reclamacoes));
    return { ...s, stat: { ...s.stat, v: nr(n.carga.transacoes), l } };
  });
  const tfidf = n.tfidf;
  const list = t.models.list.map((m) => {
    if (!tfidf || m.barsSrc !== "TFIDF" || !m.bars) return m;
    const bars = m.bars.map((b) => {
      const a = b.l === "ES" ? tfidf.es : b.l === "PT" ? tfidf.pt : null;
      return a == null ? b : { ...b, v: acuracia(a), w: Math.round(a * 1000) / 10 };
    });
    return { ...m, bars };
  });
  return { ...t, problem: { ...t.problem, stats }, dataStops, models: { ...t.models, list } };
}
