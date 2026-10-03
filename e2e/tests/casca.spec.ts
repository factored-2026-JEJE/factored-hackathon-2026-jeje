// A casca do app (DEV-032b) no navegador, contra a stack real: a língua da interface vem do endereço
// (como o site abre o app) ou da barra do topo, e a área aberta continua a mesma.
import { expect, test } from "@playwright/test";

test("a língua vem do endereço e da barra do topo, sem trocar a área aberta", async ({ page }) => {
  await page.goto("/?lang=pt#atendente");
  await expect(page.getByRole("tab", { name: "Atendente" })).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("html")).toHaveAttribute("lang", "pt-BR");
  await page.getByRole("group", { name: "Language" }).getByRole("button", { name: "ES" }).click();
  await expect(page.getByRole("tab", { name: "Agente" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "Cómo probar" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await page.getByRole("group", { name: "Language" }).getByRole("button", { name: "EN" }).click();
  await expect(page.getByRole("tab", { name: "Agent" })).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/#atendente$/);
});
