// No celular (ACH-156, NAV-02 da validação): a página cabe na largura da tela, sem rolar para o
// lado, e o toque no Enviar manda a mensagem (o campo de texto não pode cobrir o botão).
import { devices, expect, test } from "@playwright/test";
import { personas } from "./comum";

for (const nome of ["Pixel 7", "iPhone 13"] as const) {
  const { viewport, deviceScaleFactor, userAgent } = devices[nome];

  test.describe(nome, () => {
    test.skip(({ browserName }) => browserName !== "chromium", "a emulação de celular é do Chromium");
    test.use({ viewport, deviceScaleFactor, userAgent, isMobile: true, hasTouch: true });

    test("a página cabe na tela e o Enviar recebe o toque", async ({ page, request }) => {
      const [persona] = await personas(request);
      await page.goto("/");
      await page.getByRole("button", { name: `Entrar como ${persona.nome}` }).click();
      await expect(page.getByRole("table", { name: "Minhas transações" })).toBeVisible();
      const largura = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(largura).toBeLessThanOrEqual(viewport.width);

      await page.getByRole("button", { name: "Conversar em español" }).click();
      const falas = page.getByRole("log", { name: "Mensagens" }).locator("li");
      await expect(falas).toHaveCount(1);
      await page.getByLabel("Mensagem").fill("hola");
      await page.getByRole("button", { name: "Enviar" }).tap();
      await expect(falas).toHaveCount(3);
    });
  });
}
