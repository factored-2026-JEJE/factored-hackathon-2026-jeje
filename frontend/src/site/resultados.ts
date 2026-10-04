// A seção de resultados do site (1.5 do fechamento, DEV-032a). Os números do teste final (VAL-019) vêm
// de um arquivo no repositório, frontend/public/resultados/teste-final.json, servido pelo Caddy em
// /resultados/teste-final.json. Quem o escreve é a entrega (2.14 do fechamento), depois do teste, com o
// avaliador da validação: entra só o arquivo, sem mudar código. Sem ele (ou com ele inválido), o site
// publicado não mostra a seção. Nenhum número é digitado à mão.
//
// O arquivo: { "commit": "<sha>", "evidencia": "EV-…", "n": 80, "linhas": { "baseline": [9 células],
// "execucao1": [9], "execucao2": [9] } }, nas colunas do design (resolução segura, cobertura, contenção,
// encaminhamento perdido, encaminhamento desnecessário, casos inseguros, fundamentação, p50/p95 e
// consumo). Cada célula é null (—), {"fracao": 0.9125}, {"contagem": 2, "de": 80}, {"ms": [120, 340]}
// ou {"numero": 1.5, "unidade": "chamadas"}.
type Lingua = "pt" | "es" | "en";

export type Celula =
  | { readonly fracao: number }
  | { readonly contagem: number; readonly de: number }
  | { readonly ms: readonly [number, number] }
  | { readonly numero: number; readonly unidade?: string }
  | null;

export interface ResultadosDoTeste {
  readonly commit: string;
  readonly evidencia: string;
  readonly n: number;
  readonly linhas: { readonly baseline: readonly Celula[]; readonly execucao1: readonly Celula[]; readonly execucao2: readonly Celula[] };
}

export const CAMINHO_DOS_RESULTADOS = "/resultados/teste-final.json";
export const LINHAS_DA_TABELA = ["baseline", "execucao1", "execucao2"] as const;
const COLUNAS = 9;

const numero = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

function celulaValida(c: unknown): c is Celula {
  if (c === null) return true;
  if (typeof c !== "object") return false;
  const o = c as Record<string, unknown>;
  if ("fracao" in o) return numero(o.fracao) && o.fracao >= 0 && o.fracao <= 1;
  if ("contagem" in o) return numero(o.contagem) && numero(o.de) && o.de > 0;
  if ("ms" in o) return Array.isArray(o.ms) && o.ms.length === 2 && o.ms.every(numero);
  if ("numero" in o) return numero(o.numero) && (o.unidade === undefined || typeof o.unidade === "string");
  return false;
}

/** O arquivo, se ele tiver a forma combinada; senão, null (o site não mostra tabela pela metade). */
export function validarResultados(dados: unknown): ResultadosDoTeste | null {
  if (!dados || typeof dados !== "object") return null;
  const o = dados as Record<string, unknown>;
  if (typeof o.commit !== "string" || typeof o.evidencia !== "string" || !numero(o.n)) return null;
  const linhas = o.linhas as Record<string, unknown> | undefined;
  if (!linhas || typeof linhas !== "object") return null;
  for (const id of LINHAS_DA_TABELA) {
    const linha = linhas[id];
    if (!Array.isArray(linha) || linha.length !== COLUNAS || !linha.every(celulaValida)) return null;
  }
  return o as unknown as ResultadosDoTeste;
}

/** Lê o arquivo do teste final; sem ele (404), com outro conteúdo ou sem rede, null. */
export async function lerResultados(sinal?: AbortSignal): Promise<ResultadosDoTeste | null> {
  try {
    const resposta = await fetch(CAMINHO_DOS_RESULTADOS, { signal: sinal });
    if (!resposta.ok) return null;
    return validarResultados(await resposta.json());
  } catch {
    return null;
  }
}

/** Uma célula como o leitor a lê, com o separador decimal da língua (vírgula em PT e ES). */
export function formatarCelula(c: Celula, lingua: Lingua): string {
  if (c === null) return "—";
  const fixo = (x: number, casas: number) =>
    x.toLocaleString(lingua === "en" ? "en-US" : "pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  if ("fracao" in c) return fixo(c.fracao * 100, 1) + "%";
  if ("contagem" in c) return `${c.contagem} / ${c.de}`;
  if ("ms" in c) return `${fixo(c.ms[0], 0)} / ${fixo(c.ms[1], 0)} ms`;
  return fixo(c.numero, 2) + (c.unidade ? " " + c.unidade : "");
}

/** O estado da seção depois do teste (o design só tem o "em andamento"): concluído, com o commit e a EV. */
export function estadoConcluido(r: ResultadosDoTeste, lingua: Lingua): { status: string; nota: string } {
  const commit = r.commit.slice(0, 12);
  const textos = {
    pt: {
      status: "Concluído",
      nota: `O teste final rodou uma vez, no commit congelado ${commit}, nos ${r.n} cenários reservados. Os números são os da evidência ${r.evidencia}.`,
    },
    es: {
      status: "Concluido",
      nota: `La prueba final se ejecutó una vez, en el commit congelado ${commit}, en los ${r.n} escenarios reservados. Los números son los de la evidencia ${r.evidencia}.`,
    },
    en: {
      status: "Done",
      nota: `The final test ran once, on the frozen commit ${commit}, over the ${r.n} held-out scenarios. The numbers are those of evidence ${r.evidencia}.`,
    },
  };
  return textos[lingua];
}
