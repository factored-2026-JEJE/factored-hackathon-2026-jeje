// O guia dos jurados (PRD-009, 2.10) tem endereço próprio, e o "Try" de um caminho leva à conversa
// do cliente com a frase. O caminho ambíguo só lê (lista as recusas), sem criar nada no banco que as
// outras jornadas usam.
import { expect, test } from "@playwright/test";

test("o guia dos jurados abre pelo endereço e leva à aba do cliente", async ({ page }) => {
  await page.goto("/#how-to-test");
  const guia = page.getByRole("heading", { name: "Three paths, in Spanish and Portuguese." });
  await expect(guia).toBeVisible();
  await expect(page.getByRole("tab", { name: "How to test" })).toHaveAttribute("aria-selected", "true");
  const ambiguo = page.getByRole("article", { name: "Ambiguous: a declined purchase" });
  await ambiguo.getByRole("button", { name: "Try in ES →" }).click();
  await expect(page.getByRole("tab", { name: "Customer" })).toHaveAttribute("aria-selected", "true");
  await expect(guia).toBeHidden();
  await expect(page.getByRole("tabpanel", { name: "Customer" })).toContainText("¿Por qué rechazaron mi compra?");
});
