import { expect, test } from "@playwright/test";
import { auth, elegivel } from "./comum";

test("contestar, confirmar, ver o protocolo e reencontrá-lo sem duplicar", async ({ page, request }, info) => {
  const { persona, transacao: escolhida, token } = await elegivel(request, "pre_caso", info);
  const transacao = escolhida.transaction_id;
  await page.goto("/");
  await page.getByRole("button", { name: `Entrar como ${persona.nome}` }).click();
  const linhas = page.getByRole("table", { name: "Minhas transações" }).locator("tbody tr");
  await expect(linhas.first()).toBeVisible();

  const transacoes: { transaction_id: string }[] = await (await request.get("/api/minhas/transacoes", { headers: auth(token) })).json();
  const indice = transacoes.findIndex((t) => t.transaction_id === transacao);
  expect(indice).toBeGreaterThanOrEqual(0);
  const linha = linhas.nth(indice);
  await linha.getByRole("button", { name: "Contestar" }).click();
  await linha.getByRole("button", { name: "Confirmar contestação" }).click();
  const recebido = linha.getByRole("status");
  await expect(recebido).toContainText("Pré-caso recebido: protocolo PC-");
  const protocolo = (await recebido.textContent())!.match(/PC-\d+/)![0];

  // Efeito conferido no backend, não só na tela.
  const preCasos: { protocolo: string; transaction_id: string }[] = await (await request.get("/api/minhas/pre-casos", { headers: auth(token) })).json();
  expect(preCasos).toContainEqual(expect.objectContaining({ protocolo, transaction_id: transacao }));
  await expect(page.getByRole("region", { name: "Meus pré-casos" })).toContainText(protocolo);

  // Recarregar e contestar de novo: mesmo protocolo, nenhum pré-caso novo.
  await page.reload();
  await page.getByRole("table", { name: "Minhas transações" }).locator("tbody tr").nth(indice).getByRole("button", { name: "Contestar" }).click();
  await expect(page.getByText(`Já existe o pré-caso ${protocolo}`)).toBeVisible();
  // Só os pré-casos desta transação: o outro navegador pode contestar outra da mesma persona.
  const depois: { protocolo: string; transaction_id: string }[] = await (await request.get("/api/minhas/pre-casos", { headers: auth(token) })).json();
  expect(depois.filter((p) => p.transaction_id === transacao)).toEqual([expect.objectContaining({ protocolo, transaction_id: transacao })]);
});
