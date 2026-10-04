// Pré-caso pela conversa (a única porta do cliente): registrar mesmo quando a resposta do "sí" se
// perde (ACH-105), ver o protocolo na conversa e na lista, e contestar de novo numa conversa nova
// sem criar outro pré-caso.
import { expect, type Page, test } from "@playwright/test";
import { auth, dataTexto, dizerNaConversa, elegivel, entrarPeloAcesso, falasDaConversa, type Transacao, UI, valorTexto } from "./comum";

const contestar = (t: Transacao) =>
  `No reconozco el cobro de ${valorTexto(t.amount)} del ${dataTexto(t.transaction_date)}` +
  (t.merchant_name ? ` en ${t.merchant_name}` : "");

const dizer = (page: Page, texto: string) => dizerNaConversa(page, texto, "es");

test("contestar pela conversa, perder a resposta do sim, ver o protocolo e contestar de novo sem duplicar", async ({ page, request }, info) => {
  const { persona, transacao, token } = await elegivel(request, "pre_caso", info);
  await entrarPeloAcesso(page, persona.nome, "es");
  await expect(falasDaConversa(page)).toHaveCount(0);

  await expect(await dizer(page, contestar(transacao))).toContainText("¿Confirmas?");
  // A API registra o "sí", mas a resposta não chega à tela: a conexão cai na volta.
  await page.route(
    "**/api/conversas/*/turnos",
    async (rota) => {
      await rota.fetch();
      await rota.abort("connectionreset");
    },
    { times: 1 },
  );
  await page.getByRole("group", { name: UI.es.opcoes }).getByRole("button", { name: "Sí, confirmo" }).click();
  // A tela relê a conversa e mostra o que ficou registrado, sem pedir para reenviar.
  const registrado = falasDaConversa(page).last();
  await expect(registrado).toContainText("Registré la solicitud con el protocolo PC-");
  await expect(page.getByRole("button", { name: UI.es.reenviar })).toHaveCount(0);
  const protocolo = (await registrado.textContent())!.match(/PC-\d+/)![0];

  // Efeito conferido no backend, não só na tela: o protocolo mostrado é o registrado, só um, e a
  // conversa tem exatamente os dois turnos (nada foi reenviado).
  const preCasos: { protocolo: string; transaction_id: string }[] = await (await request.get("/api/minhas/pre-casos", { headers: auth(token) })).json();
  expect(preCasos.filter((p) => p.transaction_id === transacao.transaction_id)).toEqual([
    expect.objectContaining({ protocolo, transaction_id: transacao.transaction_id }),
  ]);
  const conversa = await page.evaluate(() => sessionStorage.getItem("jeje.conversa"));
  const historico: { turnos: { acao: string }[] } = await (await request.get(`/api/conversas/${conversa}`, { headers: auth(token) })).json();
  expect(historico.turnos.map((t) => t.acao)).toEqual(["propor_pre_caso", "registrar_pre_caso"]);
  await expect(page.getByRole("region", { name: UI.es.pedidos })).toContainText(protocolo);

  // Conversa nova, mesma contestação: o assistente devolve o protocolo existente, nada novo.
  await page.getByRole("button", { name: UI.es.nova }).click();
  await expect(falasDaConversa(page)).toHaveCount(0);
  await expect(await dizer(page, contestar(transacao))).toContainText(`Ya existe la solicitud ${protocolo}`);
  // Só os pré-casos desta transação: o outro navegador pode contestar outra da mesma persona.
  const depois: { protocolo: string; transaction_id: string }[] = await (await request.get("/api/minhas/pre-casos", { headers: auth(token) })).json();
  expect(depois.filter((p) => p.transaction_id === transacao.transaction_id)).toEqual([
    expect.objectContaining({ protocolo, transaction_id: transacao.transaction_id }),
  ]);
});
