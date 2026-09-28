import { expect, test } from "@playwright/test";

type Linha = {
  grupo: string;
  contagem: number;
  base: number;
  proporcao: number | null;
  proporcao_soma: number | null;
};
type Indicador = {
  id: string;
  pergunta: string;
  tipo: "distribuicao" | "taxa";
  consulta: string;
  unidade_soma: string | null;
  linhas: Linha[];
};

const inteiro = (n: number) => n.toLocaleString("pt-BR");
const pct = (p: number | null) =>
  p === null ? "—" : p.toLocaleString("pt-BR", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });

async function indicadores(request: import("@playwright/test").APIRequestContext) {
  const resposta = await request.get("/api/dados/eda");
  expect(resposta.status()).toBe(200);
  return (await resposta.json()) as Indicador[];
}

test("seção da EDA mostra exatamente os números e as consultas da API", async ({ page, request }) => {
  const todos = await indicadores(request);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Por que este fluxo" })).toBeVisible();
  for (const ind of todos) {
    const artigo = page.getByRole("article", { name: ind.pergunta });
    await expect(artigo).toBeVisible();
    for (const l of ind.linhas) {
      const esperado = [
        ind.tipo === "taxa" ? `${inteiro(l.contagem)} de ${inteiro(l.base)}` : inteiro(l.contagem),
        pct(l.proporcao),
        ...(ind.unidade_soma !== null ? [pct(l.proporcao_soma)] : []),
      ];
      const linha = artigo.getByRole("row", { name: new RegExp(`^${l.grupo.replace(/[()]/g, "\\$&")} `) });
      await expect(linha.getByRole("cell")).toHaveText(esperado);
    }
    await expect(artigo.locator("pre")).toHaveText(ind.consulta);
  }
});

// Oráculos independentes do código da EDA:
// - fixture: contas feitas à mão sobre data/fixture/gerar.py (revisão e quarentena tiram 2 versões);
// - dados reais (versão exata): total de transações da recontagem do validador (ACH-015/DADOS-01) e
//   taxas por motivo do DuckDB da sessão cli-2 (ACH-022), arredondadas como lá.
const VERSAO_S3 = "48348fcfec8725b69c4be9247b12071b27878e0c1cd0339cc31e0f5c4324758e";

test("EDA bate com o oráculo independente da origem carregada", async ({ request }) => {
  const prontidao = await (await request.get("/api/health/ready")).json();
  const por = Object.fromEntries((await indicadores(request)).map((i) => [i.id, i]));
  const grupo = (id: string, nome: string) => por[id]!.linhas.find((l) => l.grupo === nome)!;

  if (prontidao.dataset.source === "fixture") {
    const status = Object.fromEntries(por["status-das-transacoes"]!.linhas.map((l) => [l.grupo, l.contagem]));
    expect(status).toEqual({ Approved: 8, Declined: 2, Pending: 1 });
    expect(grupo("reclamacoes-por-categoria", "Transactions").contagem).toBe(1);
    expect(grupo("reclamacoes-por-categoria", "Transactions").base).toBe(2);
  } else {
    expect(prontidao.dataset.version, "oráculo registrado para outra versão").toBe(VERSAO_S3);
    const total = por["status-das-transacoes"]!.linhas.reduce((t, l) => t + l.contagem, 0);
    expect(total).toBe(4425008);
    expect(Number(((grupo("resolucao-por-motivo", "Transaccional").proporcao ?? 0) * 100).toFixed(1))).toBe(91.5);
    expect(Math.round((grupo("motivos-de-contato", "Transaccional").proporcao_soma ?? 0) * 100)).toBe(24);
  }
});
