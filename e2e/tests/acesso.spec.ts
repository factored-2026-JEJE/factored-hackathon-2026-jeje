import { expect, type APIRequestContext, test } from "@playwright/test";
import { entrarPeloAcesso, UI } from "./comum";

type Persona = { customer_id: string; nome: string };
type Transacao = { transaction_id: string; merchant_name: string | null; transaction_type: string | null };

async function personas(request: APIRequestContext): Promise<Persona[]> {
  const resposta = await request.get("/api/personas");
  expect(resposta.status()).toBe(200);
  return resposta.json();
}

async function token(request: APIRequestContext, customerId: string): Promise<string> {
  const resposta = await request.post("/api/sessoes", { data: { customer_id: customerId } });
  expect(resposta.status()).toBe(201);
  return (await resposta.json()).token;
}

async function transacoes(request: APIRequestContext, tok: string): Promise<Transacao[]> {
  const resposta = await request.get("/api/minhas/transacoes", { headers: { Authorization: `Bearer ${tok}` } });
  expect(resposta.status()).toBe(200);
  return resposta.json();
}

test("entrar como persona mostra na tela exatamente as transações da sessão", async ({ page, request }) => {
  const [primeira] = await personas(request);
  // Como no design, o dispositivo vem marcado em "cadastrado" (o bloqueio completo).
  await page.goto("/?lang=pt#cliente");
  await expect(page.getByRole("button", { name: UI.pt.cadastrado })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: UI.pt.novo })).toHaveAttribute("aria-pressed", "false");
  await entrarPeloAcesso(page, primeira!.nome, "pt");
  await expect(page.getByText(`${primeira!.customer_id} · ${primeira!.nome} · dispositivo cadastrado`)).toBeAttached();

  const tok = await page.evaluate(() => sessionStorage.getItem("jeje.sessao"));
  expect(tok).toBeTruthy();
  const esperadas = await transacoes(request, tok!);
  const linhas = page.getByRole("region", { name: UI.pt.transacoes }).getByRole("listitem");
  await expect(linhas).toHaveCount(esperadas.length);
  for (const [i, t] of esperadas.entries()) {
    await expect(linhas.nth(i).locator(".trx-comercio")).toHaveText(t.merchant_name ?? t.transaction_type ?? t.transaction_id);
  }
});

test("uma persona nunca alcança transação de outra, nem pelo endereço direto", async ({ request }) => {
  const [a, b] = await personas(request);
  const [tokA, tokB] = [await token(request, a!.customer_id), await token(request, b!.customer_id)];
  const deA = (await transacoes(request, tokA)).map((t) => t.transaction_id);
  const deB = (await transacoes(request, tokB)).map((t) => t.transaction_id);
  expect(deA.length).toBeGreaterThan(0);
  expect(deB.length).toBeGreaterThan(0);
  expect(deA.filter((id) => deB.includes(id))).toEqual([]);

  const alheia = await request.get(`/api/minhas/transacoes/${deB[0]}`, { headers: { Authorization: `Bearer ${tokA}` } });
  const inexistente = await request.get("/api/minhas/transacoes/TRX-NAO-EXISTE", { headers: { Authorization: `Bearer ${tokA}` } });
  expect(alheia.status()).toBe(404);
  expect(await alheia.json()).toEqual(await inexistente.json());

  const semToken = await request.get("/api/minhas/transacoes");
  expect(semToken.status()).toBe(401);
});
