// O guia dos jurados (PRD-009) tem endereço próprio, e os links levam às áreas da demonstração.
import { expect, test } from "@playwright/test";

test("o guia dos jurados abre pelo endereço e leva à aba do cliente", async ({ page }) => {
  await page.goto("/#how-to-test");
  const guia = page.getByRole("heading", { name: "How to test this demo" });
  await expect(guia).toBeVisible();
  await expect(page.getByRole("tab", { name: "How to test" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("link", { name: "Cliente" }).first().click();
  await expect(page.getByRole("tab", { name: "Cliente" })).toHaveAttribute("aria-selected", "true");
  await expect(guia).toBeHidden();
});
