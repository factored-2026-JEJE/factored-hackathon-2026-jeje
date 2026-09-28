import { expect, type APIRequestContext, test } from "@playwright/test";

type Persona = { customer_id: string; nome: string };
const auth = (token: string) => ({ Authorization: `Bearer ${token}` });

/**
 * N-ésima transação que a política deixa contestar agora (POL-DISP-01). Cada navegador usa um N
 * diferente: os projetos rodam em paralelo contra o mesmo banco.
 */
async function elegivel(request: APIRequestContext, pular: number) {
  const personas: Persona[] = await (await request.get("/api/personas")).json();
  for (const persona of personas) {
    const { token } = await (await request.post("/api/sessoes", { data: { customer_id: persona.customer_id } })).json();
    const transacoes: { transaction_id: string }[] = await (
      await request.get("/api/minhas/transacoes?limite=20", { headers: auth(token) })
    ).json();
    for (const t of transacoes) {
      const decisao = await (await request.get(`/api/minhas/transacoes/${t.transaction_id}/contestacao`, { headers: auth(token) })).json();
      if (decisao.regra === "POL-DISP-01" && pular-- === 0) return { persona, transacao: t.transaction_id, token };
    }
  }
  throw new Error("nenhuma transação elegível entre as personas");
}

test("contestar, confirmar, ver o protocolo e reencontrá-lo sem duplicar", async ({ page, request }, info) => {
  const { persona, transacao, token } = await elegivel(request, info.project.name === "firefox" ? 1 : 0);
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
  const depois: unknown[] = await (await request.get("/api/minhas/pre-casos", { headers: auth(token) })).json();
  expect(depois.length).toBe(preCasos.length);
});
