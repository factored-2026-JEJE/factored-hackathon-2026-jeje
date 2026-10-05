// O site do JEJE (DEV-032a) contra a stack de verdade: abre em /site/ ao lado do app, abre o app de
// verdade numa janela (design de 03/10), mostra os números lidos da API (a fixture tem outros valores
// que os do design, então a troca aparece) e conversa com a API, com o mapa acendendo o caminho do
// turno, inclusive o da conversa feita no app da janela. Nada aqui registra pré-caso nem bloqueia
// cartão: as outras jornadas usam as mesmas personas ao mesmo tempo. O site abre em inglês; as
// jornadas abrem em português (?lang=pt), a língua dos oráculos escritos aqui.
import { expect, test, type Page } from "@playwright/test";

// Os formatos que o cliente vê, escritos aqui como oráculo (não vêm do código do site).
const porcento = (p: number) => (Math.round(p * 1000) / 10).toFixed(1).replace(".", ",") + "%";
const milhar = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
const ACESO = "rgb(43, 53, 240)";

// A barra do dock aparece depois de 55% da tela rolada (design de 03/10).
async function rolarAteABarra(page: Page) {
  await page.evaluate(() => window.scrollTo(0, window.innerHeight));
  await expect(page.getByRole("button", { name: /Mande uma mensagem/ })).toHaveCSS("opacity", "1");
}

async function abrirConversa(page: Page) {
  await page.goto("/site/?lang=pt");
  await rolarAteABarra(page);
  await page.getByRole("button", { name: /Mande uma mensagem/ }).click();
  const dock = page.getByRole("dialog", { name: "Conversa" });
  await expect(dock.getByText(/Ao vivo: POST \/conversas/)).toBeVisible();
  return dock;
}
const sombra = (page: Page, no: string) => page.locator(`[data-lbl=${no}]`).evaluate((e) => (e as HTMLElement).style.boxShadow);

test("o site abre em /site/, ao lado do app, e leva ao app e ao guia", async ({ page, request }) => {
  // O site inteiro e o app na janela, duas vezes: mais que os 30 s numa máquina carregada.
  test.setTimeout(90_000);
  const semBarra = await request.get("/site", { maxRedirects: 0 });
  expect(semBarra.status()).toBe(308);
  expect(semBarra.headers()["location"]).toMatch(/\/site\/$/);
  await page.goto("/site/?lang=pt");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Seguro por desenho,");
  // O app abre numa janela dentro do site: o app de verdade, na mesma origem, na língua do site.
  await page.getByRole("button", { name: /Abrir o app/ }).first().click();
  const janela = page.getByRole("dialog", { name: "JEJE app" });
  const app = page.frameLocator('iframe[title="JEJE app"]');
  await expect(app.getByRole("tab", { name: "Cliente" })).toHaveAttribute("aria-selected", "true");
  await expect(janela.getByRole("link", { name: /Nova aba/ })).toHaveAttribute("href", "/?lang=pt#customer");
  // Trocar de aba no app muda o endereço na barra da janela (jeje-app-route).
  await app.getByRole("tab", { name: "Atendente" }).click();
  await expect(janela.getByText("#agent", { exact: true })).toBeVisible();
  // O Esc é do site: com o foco dentro do app, a tecla vai para o app (como no design). Um toque na
  // barra da janela devolve o foco ao site.
  await janela.getByText("#agent", { exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(janela).toBeHidden();
  // O guia dos jurados abre na mesma janela, na aba dele.
  await page.getByRole("button", { name: /How to test/ }).click();
  await expect(app.getByRole("tab", { name: "Como testar" })).toHaveAttribute("aria-selected", "true");
  await janela.getByRole("button", { name: /Fechar/ }).click();
  await expect(janela).toBeHidden();
});

test("a conversa feita no app da janela acende o caminho do turno no mapa do site", async ({ page }) => {
  // O site inteiro e o app na janela, com a sessão e a conversa: mais que os 30 s numa máquina carregada.
  test.setTimeout(90_000);
  await page.goto("/site/?lang=pt");
  // O mapa acende com o bloco do mapa inteiro na tela: o link "O mapa" do cabeçalho leva até ele.
  await page.getByRole("navigation").getByRole("link", { name: "O mapa" }).click();
  await expect(page.getByRole("button", { name: /Mande uma mensagem/ })).toHaveCSS("opacity", "1");
  // No mapa inteiro, a rolagem acende o caminho todo da mensagem, inclusive o "Qual".
  await expect.poll(() => sombra(page, "qual"), { timeout: 15_000 }).toContain(ACESO);
  await page.getByRole("button", { name: /Abrir o app/ }).last().click();
  const app = page.frameLocator('iframe[title="JEJE app"]');
  // O app da janela abre na língua do site (pt): entra pela primeira persona, com o dispositivo cadastrado.
  await app.getByRole("button", { name: /^Entrar como .* →$/ }).click();
  // Uma mensagem sem transação: o caminho do turno não passa pelo "Qual", e passa pela política.
  const resposta = turnoDaApi(page);
  await app.getByLabel("Escreva como cliente, em espanhol ou português").fill("xyz");
  await app.getByRole("button", { name: "Enviar", exact: true }).click();
  const turno: Turno = await (await resposta).json();
  expect(turno.opcoes).toEqual([]);
  await expect.poll(() => sombra(page, "qual"), { timeout: 15_000 }).toBe("none");
  await expect.poll(() => sombra(page, "politica"), { timeout: 15_000 }).toMatch(/43, 53, 240|255, 85, 32/);
});

test("no celular, o menu do cabeçalho leva às seções e fecha", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/site/?lang=pt");
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await menu.click();
  await expect(menu).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("link", { name: "Modelos" }).last().click();
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
});

test("os números vêm da API: as reclamações de transação e o tamanho da carga", async ({ page, request }) => {
  const eda: { id: string; linhas: { grupo: string; proporcao: number }[] }[] = await (await request.get("/api/dados/eda")).json();
  const cargo = eda.find((i) => i.id === "reclamacoes-de-transacao")?.linhas.find((l) => l.grupo === "Cargo no reconocido");
  const tabelas: { tabela: string; curado: number }[] = await (await request.get("/api/dados/qualidade")).json();
  const curado = (t: string) => tabelas.find((x) => x.tabela === t)?.curado ?? -1;
  expect(cargo).toBeDefined();
  await page.goto("/site/?lang=pt");
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
  await page.goto("/site/?lang=pt");
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
  await page.goto("/site/?lang=pt");
  await expect(page.locator("svg").first()).toBeVisible();
  await expect(page.locator("canvas")).toBeHidden();
  await page.getByText("Efeito conferido. Recibo impresso.").scrollIntoViewIfNeeded();
  // O recibo não fica cortado: o recorte de baixo (o terceiro valor do inset) é 0.
  const recorte = () =>
    page.locator("[style*='clip-path']").first().evaluate((e) => parseFloat((e as HTMLElement).style.clipPath.split(/[()\s]+/)[3] ?? "100"));
  await expect.poll(recorte).toBe(0);
});

test("com o arquivo do teste final, a seção de resultados e o link do menu aparecem, com o commit congelado e a evidência", async ({ page, request }) => {
  // O arquivo do repositório (2.14), servido como está: a seção diz que o teste acabou, no commit dele.
  const arquivo = await request.get("/resultados/teste-final.json");
  expect(arquivo.status()).toBe(200);
  const r = (await arquivo.json()) as { commit: string; evidencia: string; n: number };
  await page.goto("/site/?lang=pt");
  const secao = page.locator("#resultados");
  await expect(secao).toHaveCount(1);
  await expect(page.getByRole("navigation").getByRole("link", { name: "Resultados" })).toHaveCount(1);
  await expect(secao).toContainText("Concluído");
  await expect(secao).toContainText(`no commit congelado ${r.commit.slice(0, 12)}, nos ${r.n} cenários reservados`);
  await expect(secao).toContainText(r.evidencia);
});

test("um arquivo que não existe em /resultados/ dá 404, e não a página do app", async ({ request }) => {
  // O 404 de verdade é o que faz o site esconder a seção quando o arquivo falta (resultados.ts).
  expect((await request.get("/resultados/nao-existe.json")).status()).toBe(404);
});
