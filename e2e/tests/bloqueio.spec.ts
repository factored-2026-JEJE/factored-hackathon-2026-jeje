// Bloqueio simulado de cartão (PRD-007) no navegador: com dispositivo cadastrado, o cliente bloqueia
// o cartão pela conversa, o bloqueio aparece no console do atendente e o próprio cliente o desfaz
// dentro do prazo, com um sim explícito. Todo efeito mostrado na tela é conferido na API.
//
// Usa o cartão numerado da segunda persona da fixture (data/fixture/gerar.py), que nenhuma outra
// jornada toca. Roda só no Chromium: com um cartão só, o Firefox disputaria o mesmo bloqueio.
import { expect, test } from "@playwright/test";
import { personas } from "./comum";

test("bloquear o cartão pela conversa e desfazer dentro do prazo, com o console acompanhando", async ({ page, request, browserName }) => {
  test.skip(browserName !== "chromium", "um cartão só para a jornada: roda num navegador");
  const prontidao = await (await request.get("/api/health/ready")).json();
  test.skip(prontidao.dataset.source !== "fixture", "a jornada usa o cartão da segunda persona da fixture");

  const [, segunda] = await personas(request);
  await page.goto("/");
  await page.getByRole("radio", { name: "Cadastrado" }).check();
  await page.getByRole("button", { name: `Entrar como ${segunda!.nome}` }).click();
  await expect(page.getByText("Dispositivo (simulação): cadastrado")).toBeVisible();
  await page.getByRole("button", { name: "Conversar em español" }).click();
  const falas = page.getByRole("log", { name: "Mensagens" }).locator("li");
  await expect(falas).toHaveCount(1);

  // Bloqueio pelo atalho: completo, porque o dispositivo é cadastrado, e sem encaminhamento.
  await page.getByRole("group", { name: "Atalhos" }).getByRole("button", { name: "Bloquear cartão" }).click();
  await expect(falas).toHaveCount(3);
  const bloqueado = falas.last().locator("p").first();
  await expect(bloqueado).toContainText("Bloqueé tu tarjeta de débito terminada en 9876 (bloqueo completo simulado, referencia BL-");
  const bloqueio = (await bloqueado.textContent())!.match(/BL-\d{8}/)![0];

  // O aviso ao atendente é o bloqueio no console.
  await page.getByRole("tab", { name: "Atendente" }).click();
  const painel = page.getByRole("region", { name: "Bloqueios de cartão" });
  await expect(painel.getByRole("listitem", { name: `Bloqueio ${bloqueio}` })).toContainText("bloqueio completo");

  // Dentro do prazo, o cliente desfaz pela conversa, e só com o sim.
  await page.getByRole("tab", { name: "Cliente" }).click();
  await page.getByLabel("Mensagem").fill("quiero desbloquear mi tarjeta");
  await page.getByRole("button", { name: "Enviar", exact: true }).click();
  await expect(falas).toHaveCount(5);
  await expect(falas.last().locator("p").first()).toHaveText(
    `¿Confirmas que quieres deshacer el bloqueo de tu tarjeta de débito terminada en 9876 (referencia ${bloqueio})? Responde sí o no.`,
  );
  const antes: { id: string }[] = await (await request.get("/api/atendimento/bloqueios?limite=100")).json();
  expect(antes.map((b) => b.id)).toContain(bloqueio);
  await page.getByRole("button", { name: "Sí, confirmo" }).click();
  await expect(falas).toHaveCount(7);
  await expect(falas.last().locator("p").first()).toHaveText(
    `Listo: deshice el bloqueo de tu tarjeta de débito terminada en 9876 (referencia ${bloqueio}).`,
  );

  // Some do console, na tela e na API.
  await page.getByRole("tab", { name: "Atendente" }).click();
  await expect(painel.getByRole("listitem", { name: `Bloqueio ${bloqueio}` })).toHaveCount(0);
  const depois: { id: string }[] = await (await request.get("/api/atendimento/bloqueios?limite=100")).json();
  expect(depois.map((b) => b.id)).not.toContain(bloqueio);
});
