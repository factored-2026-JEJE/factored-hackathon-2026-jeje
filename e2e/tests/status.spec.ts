import { expect, test } from "@playwright/test";

// A prontidão da aba da operação (2.10) nos rótulos do design, em inglês, a língua padrão do app
// (especificação escrita aqui, sem importar código da UI).
const ROTULO_DO_BANCO = {
  ok: "ready",
  unreachable: "unreachable",
  not_migrated: "not migrated",
  reloading: "reloading",
} as const;

const curta = (versao: string) => (versao.length > 12 ? `${versao.slice(0, 4)}…${versao.slice(-4)}` : versao);

test("a prontidão mostra exatamente o estado que a API reporta", async ({ page, request }) => {
  const resposta = await request.get("/api/health/ready");
  expect([200, 503]).toContain(resposta.status());
  const prontidao = await resposta.json();

  await page.goto("/#operations");

  const grupo = page.getByRole("group", { name: "Readiness" });
  const rotulo = ROTULO_DO_BANCO[prontidao.database as keyof typeof ROTULO_DO_BANCO];
  await expect(grupo.getByText(rotulo, { exact: true })).toBeVisible();
  const versao = prontidao.dataset === null ? "no data loaded" : `${prontidao.dataset.source} · ${curta(prontidao.dataset.version)}`;
  await expect(grupo.getByText(versao, { exact: true })).toBeVisible();
});
