// Pré-caso pela conversa (a única porta do cliente): registrar, ver o protocolo na conversa e na
// lista, e contestar de novo numa conversa nova sem criar outro pré-caso.
import { expect, type Page, test } from "@playwright/test";
import { auth, dataTexto, elegivel, type Transacao, valorTexto } from "./comum";

const contestar = (t: Transacao) =>
  `No reconozco el cobro de ${valorTexto(t.amount)} del ${dataTexto(t.transaction_date)}` +
  (t.merchant_name ? ` en ${t.merchant_name}` : "");

async function dizer(page: Page, texto: string) {
  const mensagens = page.getByRole("log", { name: "Mensagens" }).locator("li");
  const antes = await mensagens.count();
  await page.getByPlaceholder("Escribe tu mensaje").fill(texto);
  await page.getByRole("button", { name: "Enviar", exact: true }).click();
  await expect(mensagens).toHaveCount(antes + 2);
  return mensagens.last();
}

test("contestar pela conversa, confirmar, ver o protocolo e contestar de novo sem duplicar", async ({ page, request }, info) => {
  const { persona, transacao, token } = await elegivel(request, "pre_caso", info);
  await page.goto("/");
  await page.getByRole("button", { name: `Entrar como ${persona.nome}` }).click();
  await page.getByRole("button", { name: "Conversar em español" }).click();
  await expect(page.getByRole("log", { name: "Mensagens" }).locator("li")).toHaveCount(1);

  await expect(await dizer(page, contestar(transacao))).toContainText("¿Confirmas?");
  await page.getByRole("button", { name: "Sí, confirmo" }).click();
  const recebido = page.getByRole("status").filter({ hasText: "Pré-caso recebido" });
  await expect(recebido).toContainText("Pré-caso recebido: protocolo PC-");
  const protocolo = (await recebido.textContent())!.match(/PC-\d+/)![0];

  // Efeito conferido no backend, não só na tela.
  const preCasos: { protocolo: string; transaction_id: string }[] = await (await request.get("/api/minhas/pre-casos", { headers: auth(token) })).json();
  expect(preCasos).toContainEqual(expect.objectContaining({ protocolo, transaction_id: transacao.transaction_id }));
  await expect(page.getByRole("region", { name: "Meus pré-casos" })).toContainText(protocolo);

  // Conversa nova, mesma contestação: o assistente devolve o protocolo existente, nada novo.
  await page.getByRole("button", { name: "Nova conversa" }).click();
  await page.getByRole("button", { name: "Conversar em español" }).click();
  await expect(page.getByRole("log", { name: "Mensagens" }).locator("li")).toHaveCount(1);
  await expect(await dizer(page, contestar(transacao))).toContainText(`Ya existe la solicitud ${protocolo}`);
  // Só os pré-casos desta transação: o outro navegador pode contestar outra da mesma persona.
  const depois: { protocolo: string; transaction_id: string }[] = await (await request.get("/api/minhas/pre-casos", { headers: auth(token) })).json();
  expect(depois.filter((p) => p.transaction_id === transacao.transaction_id)).toEqual([
    expect.objectContaining({ protocolo, transaction_id: transacao.transaction_id }),
  ]);
});
