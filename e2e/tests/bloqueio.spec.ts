// Bloqueio simulado de cartão (PRD-007) no navegador: com dispositivo cadastrado, o cliente bloqueia
// o cartão pela conversa, o bloqueio aparece no console do atendente e o próprio cliente o desfaz
// dentro do prazo, com um sim explícito. O bloqueio do relato de roubo o cliente também desfaz em
// até 7 dias (PRD-009), e o caso do atendente fica sabendo. Todo efeito mostrado na tela é conferido.
//
// Usa o cartão numerado da segunda persona da fixture (data/fixture/gerar.py), que nenhuma outra
// jornada toca; as jornadas deste arquivo rodam em série. Roda só no Chromium: com um cartão só, o
// Firefox disputaria o mesmo bloqueio.
import { expect, test } from "@playwright/test";
import { dizerNaConversa, entrarPeloAcesso, falasDaConversa, personas, UI } from "./comum";

test("bloquear o cartão pela conversa e desfazer dentro do prazo, com o console acompanhando", async ({ page, request, browserName }) => {
  test.skip(browserName !== "chromium", "um cartão só para a jornada: roda num navegador");
  const prontidao = await (await request.get("/api/health/ready")).json();
  test.skip(prontidao.dataset.source !== "fixture", "a jornada usa o cartão da segunda persona da fixture");

  const [, segunda] = await personas(request);
  await entrarPeloAcesso(page, segunda!.nome, "es", "cadastrado");
  await expect(page.getByText(`${segunda!.customer_id} · ${segunda!.nome} · dispositivo registrado`)).toBeAttached();
  const falas = falasDaConversa(page);
  await expect(falas).toHaveCount(0);

  // Bloqueio pelo atalho: completo, porque o dispositivo é cadastrado, e sem encaminhamento.
  await page.getByRole("group", { name: UI.es.atalhos }).getByRole("button", { name: "Bloquear tarjeta" }).click();
  await expect(falas).toHaveCount(2);
  const bloqueado = falas.last().locator("p").first();
  await expect(bloqueado).toContainText("Bloqueé tu tarjeta de débito terminada en 9876 (bloqueo completo simulado, referencia BL-");
  const bloqueio = (await bloqueado.textContent())!.match(/BL-\d{8}/)![0];

  // O painel de cartões da sessão relê o cartão (2.1): bloqueado, completo, com a nota de desfazer.
  const cartao = page.getByRole("region", { name: UI.es.cartoes }).getByRole("listitem").filter({ hasText: "•••• 9876" });
  await expect(cartao).toContainText("bloqueada · completo");
  await expect(cartao).toContainText("Se puede deshacer por el chat en hasta 7 días.");

  // O aviso ao atendente é o bloqueio no console.
  await page.getByRole("tab", { name: UI.es.agente }).click();
  const painel = page.getByRole("region", { name: UI.es.bloqueios });
  await expect(painel.getByLabel(bloqueio, { exact: true })).toContainText(UI.es.completo);

  // Dentro do prazo, o cliente desfaz pela conversa, e só com o sim.
  await page.getByRole("tab", { name: UI.es.cliente }).click();
  await dizerNaConversa(page, "quiero desbloquear mi tarjeta", "es");
  await expect(falas).toHaveCount(4);
  await expect(falas.last().locator("p").first()).toHaveText(
    `¿Confirmas que quieres deshacer el bloqueo de tu tarjeta de débito terminada en 9876 (referencia ${bloqueio})? Responde sí o no.`,
  );
  const antes: { id: string }[] = await (await request.get("/api/atendimento/bloqueios?limite=100")).json();
  expect(antes.map((b) => b.id)).toContain(bloqueio);
  await page.getByRole("group", { name: UI.es.opcoes }).getByRole("button", { name: "Sí, confirmo" }).click();
  await expect(falas).toHaveCount(6);
  await expect(falas.last().locator("p").first()).toHaveText(
    `Listo: deshice el bloqueo de tu tarjeta de débito terminada en 9876 (referencia ${bloqueio}).`,
  );
  await expect(cartao).toContainText("activa");
  await expect(cartao).not.toContainText("bloqueada");

  // Some do console, na tela e na API.
  await page.getByRole("tab", { name: UI.es.agente }).click();
  await expect(painel.getByLabel(bloqueio, { exact: true })).toHaveCount(0);
  const depois: { id: string }[] = await (await request.get("/api/atendimento/bloqueios?limite=100")).json();
  expect(depois.map((b) => b.id)).not.toContain(bloqueio);
});

test("relato de roubo: o cliente desfaz o bloqueio em até 7 dias pela conversa, e o caso do atendente fica sabendo", async ({ page, request, browserName }) => {
  test.skip(browserName !== "chromium", "um cartão só para a jornada: roda num navegador");
  const prontidao = await (await request.get("/api/health/ready")).json();
  test.skip(prontidao.dataset.source !== "fixture", "a jornada usa o cartão da segunda persona da fixture");

  const [, segunda] = await personas(request);
  await entrarPeloAcesso(page, segunda!.nome, "es", "cadastrado");
  const falas = falasDaConversa(page);
  await expect(falas).toHaveCount(0);

  // O relato bloqueia o cartão e encaminha; o bloqueio fica ligado ao caso.
  const relato = (await (await dizerNaConversa(page, "Me robaron la tarjeta", "es")).textContent())!;
  const bloqueio = relato.match(/BL-\d{8}/)![0];
  const atendimento = relato.match(/AT-\d{8}/)![0];

  // Urgência (PRD-009): numa conversa nova, o cliente desfaz dentro do prazo, e só com o sim.
  await page.getByRole("button", { name: UI.es.nova }).click();
  await expect(falas).toHaveCount(0);
  await dizerNaConversa(page, "quiero desbloquear mi tarjeta", "es");
  await page.getByRole("group", { name: UI.es.opcoes }).getByRole("button", { name: "Sí, confirmo" }).click();
  await expect(falas).toHaveCount(4);
  await expect(falas.last().locator("p").first()).toHaveText(
    `Listo: deshice el bloqueo de tu tarjeta de débito terminada en 9876 (referencia ${bloqueio}).`,
  );

  // O caso, na fila do atendente, mostra que o cliente desfez o bloqueio.
  await page.getByRole("tab", { name: UI.es.agente }).click();
  const caso = page.getByRole("region", { name: UI.es.fila }).getByRole("article", { name: atendimento });
  await expect(caso).toContainText(UI.es.desfeitoPeloCliente(bloqueio));
  // Sem sobra para as outras jornadas: o atendente assume o caso, que fica na tela como assumido.
  await caso.getByRole("button", { name: `${UI.es.assumir} ${atendimento}` }).click();
  await expect(caso.getByRole("button", { name: `${UI.es.assumido} ${atendimento}` })).toHaveAttribute("aria-pressed", "true");
  const fila: { id: string }[] = await (await request.get("/api/atendimento/fila?limite=100")).json();
  expect(fila.map((e) => e.id)).not.toContain(atendimento);
});
