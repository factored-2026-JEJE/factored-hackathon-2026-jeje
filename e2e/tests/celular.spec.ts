// No celular (ACH-156, NAV-02 da validação): a página cabe na largura da tela, sem rolar para o
// lado, o painel vira as abas internas do design (abaixo de 900 px) e o toque no Enviar manda a
// mensagem (o campo de texto não pode cobrir o botão).
import { devices, expect, test } from "@playwright/test";
import { entrarPeloAcesso, falasDaConversa, personas, UI } from "./comum";

for (const nome of ["Pixel 7", "iPhone 13"] as const) {
  const { viewport, deviceScaleFactor, userAgent } = devices[nome];

  test.describe(nome, () => {
    test.skip(({ browserName }) => browserName !== "chromium", "a emulação de celular é do Chromium");
    test.use({ viewport, deviceScaleFactor, userAgent, isMobile: true, hasTouch: true });

    test("a página cabe na tela e o Enviar recebe o toque", async ({ page, request }) => {
      const [persona] = await personas(request);
      await entrarPeloAcesso(page, persona!.nome, "es");
      const largura = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(largura).toBeLessThanOrEqual(viewport.width);
      // Abaixo de 900 px, as transações ficam numa aba interna: a conversa sai de cena e volta.
      const abas = page.getByRole("tablist", { name: UI.es.conversa });
      await abas.getByRole("tab", { name: UI.es.paineis[1] }).tap();
      await expect(page.getByRole("region", { name: UI.es.transacoes })).toBeVisible();
      await expect(page.getByLabel(UI.es.caixa)).toBeHidden();
      await abas.getByRole("tab", { name: UI.es.paineis[0] }).tap();

      const falas = falasDaConversa(page);
      await expect(falas).toHaveCount(0);
      await page.getByLabel(UI.es.caixa).fill("hola");
      await page.getByRole("button", { name: UI.es.enviar, exact: true }).tap();
      await expect(falas).toHaveCount(2);
    });

    test("as tabelas da Operação ficam dentro da tela e rolam por dentro (ACH-156)", async ({ page }) => {
      // A raiz do app corta o que passa da borda (overflow: hidden): a largura da página não mostra uma
      // tabela larga. Na Operação do design (2.10), cada tabela fica numa caixa da largura da tela, e
      // é a caixa que rola para o lado; sem a rolagem, o fim da tabela ficaria fora de alcance.
      await page.goto("/#operacao");
      const caixas = page.locator("#painel-operacao .cn-rolavel");
      await expect(caixas.first()).toBeVisible();
      const direita = await caixas.evaluateAll((cs) => Math.max(...cs.map((c) => c.getBoundingClientRect().right)));
      expect(direita).toBeLessThanOrEqual(viewport.width);
      const rolou = await caixas.first().evaluate((c) => {
        c.scrollLeft = 10_000;
        return c.scrollLeft;
      });
      expect(rolou).toBeGreaterThan(0);
    });
  });
}
