import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// Oráculo independente do código Python: sha256sum (coreutils) sobre "tabela\n" + manifesto,
// em ordem alfabética, para as tabelas configuradas no compose.
function versaoEsperada(): string {
  const script = `
    for t in $(printf '%s' "$DATASET_TABLES" | tr ',' '\\n' | sort); do
      printf '%s\\n' "$t"; cat "$DATASET_MANIFEST_DIR/$t.csv"
    done | sha256sum | cut -d' ' -f1`;
  return execFileSync("sh", ["-c", script], { encoding: "utf8" }).trim();
}

test("stack sobe pronta com exatamente a versão de dados do manifesto versionado", async ({ page, request }) => {
  const esperada = versaoEsperada();
  expect(esperada).toMatch(/^[0-9a-f]{64}$/);

  const resposta = await request.get("/api/health/ready");
  expect(resposta.status()).toBe(200);
  const prontidao = await resposta.json();
  expect(prontidao.status).toBe("ready");
  expect(prontidao.dataset.version).toBe(esperada);

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Pronto para atender" })).toBeVisible();
  await expect(page.getByText(`versão ${esperada.slice(0, 12)} (${prontidao.dataset.source})`)).toBeVisible();
});
