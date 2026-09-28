import { expect, test } from "@playwright/test";

type Qualidade = {
  tabela: string;
  raw: number;
  curado: number;
  quarentena: number;
  copias_descartadas: number;
  motivos: Record<string, number>;
  anulacoes: Record<string, number>;
  normalizacoes: Record<string, number>;
};

const soma = (c: Record<string, number>) => Object.values(c).reduce((t, n) => t + n, 0);
const pt = (n: number) => n.toLocaleString("pt-BR");

// Oráculos independentes do pipeline:
// - fixture: defeitos deliberados escritos em data/fixture/gerar.py;
// - dados reais (versão exata do manifesto): recontagem DuckDB do validador (EV-009, ACH-016/017/019).
const ESPERADO_FIXTURE = {
  transactions: { quarentena: 1, motivos: { "Q-TIPO:amount": 1 } },
  complaints: { anulacao: ["A-PROP:affected_product_id", 1] as const },
};
const ESPERADO_S3 = {
  versao: "48348fcfec8725b69c4be9247b12071b27878e0c1cd0339cc31e0f5c4324758e",
  anulacoes: {
    customers: ["A-REF:registration_branch_id", 149995] as const,
    complaints: ["A-PROP:affected_product_id", 44570] as const,
  },
  usdNormalizados: 2437979,
};

test("painel de qualidade mostra os números da API e fecha a conta de cada tabela", async ({ page, request }) => {
  const tabelas: Qualidade[] = await (await request.get("/api/dados/qualidade")).json();
  expect(tabelas.length).toBeGreaterThan(0);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Qualidade dos dados" })).toBeVisible();
  for (const t of tabelas) {
    expect(t.raw).toBe(t.curado + t.quarentena + t.copias_descartadas);
    const celulas = page.getByRole("row", { name: new RegExp(`^${t.tabela} `) }).getByRole("cell");
    await expect(celulas).toHaveText([
      pt(t.raw), pt(t.curado), pt(t.quarentena), pt(t.copias_descartadas),
      pt(soma(t.anulacoes)), pt(soma(t.normalizacoes)),
    ]);
  }
  await expect(page.getByText("Contagens inconsistentes")).toHaveCount(0);
});

test("curadoria bate com o oráculo independente da origem carregada", async ({ request }) => {
  const prontidao = await (await request.get("/api/health/ready")).json();
  const tabelas: Qualidade[] = await (await request.get("/api/dados/qualidade")).json();
  const de = (nome: string) => tabelas.find((t) => t.tabela === nome)!;

  if (prontidao.dataset.source === "fixture") {
    expect(de("transactions").quarentena).toBe(ESPERADO_FIXTURE.transactions.quarentena);
    expect(de("transactions").motivos).toEqual(ESPERADO_FIXTURE.transactions.motivos);
    const [codigo, n] = ESPERADO_FIXTURE.complaints.anulacao;
    expect(de("complaints").anulacoes[codigo]).toBe(n);
  } else {
    // Dados mudaram? Refaça a recontagem independente e atualize o oráculo (nunca pule).
    expect(prontidao.dataset.version, "oráculo independente registrado para outra versão").toBe(
      ESPERADO_S3.versao,
    );
    for (const [tabela, [codigo, n]] of Object.entries(ESPERADO_S3.anulacoes)) {
      expect(de(tabela).anulacoes[codigo]).toBe(n);
    }
    expect(de("transactions").normalizacoes["N-USD:amount_usd"]).toBe(ESPERADO_S3.usdNormalizados);
    expect(tabelas.every((t) => t.quarentena === 0)).toBe(true);
  }
});
