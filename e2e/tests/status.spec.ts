import { expect, test } from "@playwright/test";

// Especificação dos rótulos exibidos para cada estado do banco (não importa código da UI).
const ROTULO_ESPERADO = {
  ok: "conectado",
  unreachable: "inacessível",
  not_migrated: "sem migrations aplicadas",
  reloading: "recarregando os dados",
} as const;

test("página de status mostra exatamente o estado que a API reporta", async ({ page, request }) => {
  const resposta = await request.get("/api/health/ready");
  expect([200, 503]).toContain(resposta.status());
  const prontidao = await resposta.json();

  await page.goto("/#operacao");

  const titulo = prontidao.status === "ready" ? "Pronto para atender" : "Indisponível";
  await expect(page.getByRole("heading", { name: titulo })).toBeVisible();
  const rotulo = ROTULO_ESPERADO[prontidao.database as keyof typeof ROTULO_ESPERADO];
  await expect(page.getByText(rotulo, { exact: true })).toBeVisible();
  if (prontidao.dataset === null) {
    await expect(page.getByText("nenhum dataset carregado")).toBeVisible();
  } else {
    await expect(page.getByText(`versão ${prontidao.dataset.version.slice(0, 12)}`, { exact: false })).toBeVisible();
  }
});
