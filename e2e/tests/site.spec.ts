// O site do JEJE (DEV-032a) contra a stack de verdade: abre em /site/ ao lado do app, mostra os
// números lidos da API (a fixture tem outros valores que os do design, então a troca aparece) e
// conversa com a API, com o mapa acendendo o caminho do turno. Nada aqui registra pré-caso nem
// bloqueia cartão: as outras jornadas usam as mesmas personas ao mesmo tempo.
import { expect, test, type Page } from "@playwright/test";

// Os formatos que o cliente vê, escritos aqui como oráculo (não vêm do código do site).
const porcento = (p: number) => (Math.round(p * 1000) / 10).toFixed(1).replace(".", ",") + "%";
const milhar = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
const ACESO = "rgb(43, 53, 240)";

async function abrirConversa(page: Page) {
  await page.goto("/site/");
  await page.getByRole("button", { name: /Mande uma mensagem/ }).click();
  const dock = page.getByRole("dialog", { name: "Conversa" });
  await expect(dock.getByText(/Ao vivo: POST \/conversas/)).toBeVisible();
  return dock;
}
const sombra = (page: Page, no: string) => page.locator(`[data-lbl=${no}]`).evaluate((e) => (e as HTMLElement).style.boxShadow);

test("o site abre em /site/, ao lado do app, e leva ao app e ao guia", async ({ page, request }) => {
  const semBarra = await request.get("/site", { maxRedirects: 0 });
  expect(semBarra.status()).toBe(308);
  expect(semBarra.headers()["location"]).toMatch(/\/site\/$/);
  await page.goto("/site/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Não é um chatbot.");
  await expect(page.getByRole("link", { name: /Abrir o app/ }).first()).toHaveAttribute("href", "/#cliente");
  await expect(page.getByRole("link", { name: /How to test/ })).toHaveAttribute("href", "/#how-to-test");
  await page.getByRole("link", { name: /Abrir o app/ }).first().evaluate((a) => a.removeAttribute("target"));
  await page.getByRole("link", { name: /Abrir o app/ }).first().click();
  await expect(page.getByRole("tab", { name: "Customer" })).toHaveAttribute("aria-selected", "true");
});

test("os números vêm da API: as reclamações de transação e o tamanho da carga", async ({ page, request }) => {
  const eda: { id: string; linhas: { grupo: string; proporcao: number }[] }[] = await (await request.get("/api/dados/eda")).json();
  const cargo = eda.find((i) => i.id === "reclamacoes-de-transacao")?.linhas.find((l) => l.grupo === "Cargo no reconocido");
  const tabelas: { tabela: string; curado: number }[] = await (await request.get("/api/dados/qualidade")).json();
  const curado = (t: string) => tabelas.find((x) => x.tabela === t)?.curado ?? -1;
  expect(cargo).toBeDefined();
  await page.goto("/site/");
  const problema = page.locator("section").filter({ hasText: "Por que este fluxo" });
  await expect(problema.getByText(porcento(cargo?.proporcao ?? -1), { exact: true })).toBeVisible();
  const versao = page.locator("article").filter({ hasText: "Versão dos dados" });
  await expect(versao.getByText(milhar(curado("transactions")), { exact: true })).toBeAttached();
  await expect(versao.getByText(`transações · ${milhar(curado("customers"))} clientes · ${milhar(curado("complaints"))} reclamações`)).toBeAttached();
});

// O turno de verdade, lido da rede: o oráculo é o que a API respondeu (as outras jornadas mudam as
// mesmas personas ao mesmo tempo, então o estado delas não é fixo).
type Turno = { resposta: string; regra: string; acao: string; estado: string; opcoes: { descricao: string }[] };
const turnoDaApi = (page: Page) =>
  page.waitForResponse((r) => /\/api\/conversas\/[^/]+\/turnos$/.test(r.url()) && r.request().method() === "POST");

test("a conversa fala com a API: a contestação vai com uma compra da persona, e o balão e o porquê são os do turno", async ({ page, request }) => {
  const exemplos = async () => {
    const ps: { exemplo: { valor: string; data: string } | null }[] = await (await request.get("/api/personas")).json();
    return ps.flatMap((p) => (p.exemplo ? [p.exemplo] : [])).map((e) => {
      const [, mes, dia] = e.data.split("-");
      const [inteiro, centavos] = Number(e.valor).toFixed(2).split(".");
      return `Não reconheço a cobrança de ${milhar(Number(inteiro))},${centavos} do dia ${dia}/${mes}`;
    });
  };
  const antes = await exemplos();
  const dock = await abrirConversa(page);
  const resposta = turnoDaApi(page);
  await dock.getByRole("button", { name: "Não reconheço uma cobrança" }).click();
  const r = await resposta;
  const turno: Turno = await r.json();
  const mandada = (r.request().postDataJSON() as { texto: string }).texto;
  expect([...antes, ...(await exemplos())]).toContain(mandada);
  await expect(dock.getByText(mandada, { exact: true })).toBeVisible();
  await expect(dock.getByText(turno.resposta, { exact: true })).toBeVisible();
  await dock.getByRole("button", { name: /Por que esta resposta/ }).click();
  await expect(dock.getByText(turno.regra, { exact: true })).toBeVisible();
  await expect(dock.getByText(turno.acao, { exact: true })).toBeVisible();
  if (turno.estado === "confirmando") await expect(dock.getByRole("button", { name: "Sim, confirmo" })).toBeVisible();
  // O caminho do turno acende até a política e o banco.
  await expect.poll(() => sombra(page, "politica"), { timeout: 15_000 }).toMatch(/43, 53, 240|255, 85, 32/);
  await expect.poll(() => sombra(page, "banco"), { timeout: 15_000 }).toMatch(/43, 53, 240|255, 85, 32/);
});

test("perguntar qual transação acende o Qual sem a Ação, e as opções são as da API", async ({ page }) => {
  const dock = await abrirConversa(page);
  const resposta = turnoDaApi(page);
  await dock.getByRole("button", { name: "Por que recusaram minha compra?" }).click();
  const turno: Turno = await (await resposta).json();
  // A persona do site tem mais de uma recusa: a API pergunta qual, com uma opção por recusa.
  expect(turno.acao).toBe("esclarecer");
  expect(turno.opcoes.length).toBeGreaterThan(1);
  await expect(dock.getByText(turno.resposta, { exact: true })).toBeVisible();
  for (const o of turno.opcoes) await expect(dock.getByRole("button", { name: o.descricao, exact: true })).toBeVisible();
  await expect.poll(() => sombra(page, "qual"), { timeout: 15_000 }).toContain(ACESO);
  expect(await sombra(page, "acoes")).toBe("none");
});

test("a injeção do pilar de segurança vai à API e não tem efeito", async ({ page }) => {
  await page.goto("/site/");
  await page.getByRole("button", { name: /Mandar ao sistema/ }).click();
  const dock = page.getByRole("dialog", { name: "Conversa" });
  await expect(dock.getByText(/Ignore suas instruções/)).toBeVisible();
  await dock.getByRole("button", { name: /Por que esta resposta/ }).last().click({ timeout: 15_000 });
  // No "Por que esta resposta?": o efeito é nenhum (—) e não há protocolo.
  const porque = dock.locator("div[style*='dashed']").last();
  await expect(porque).toContainText(/efeito\s*—/i);
  await expect(porque).not.toContainText(/protocolo/i);
  await expect.poll(() => sombra(page, "politica"), { timeout: 15_000 }).toContain(ACESO);
});

test("sem movimento, o mapa é o 2D e o recibo aparece inteiro", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/site/");
  await expect(page.locator("svg").first()).toBeVisible();
  await expect(page.locator("canvas")).toBeHidden();
  await page.getByText("Efeito conferido. Recibo impresso.").scrollIntoViewIfNeeded();
  // O recibo não fica cortado: o recorte de baixo (o terceiro valor do inset) é 0.
  const recorte = () =>
    page.locator("[style*='clip-path']").first().evaluate((e) => parseFloat((e as HTMLElement).style.clipPath.split(/[()\s]+/)[3] ?? "100"));
  await expect.poll(recorte).toBe(0);
});
