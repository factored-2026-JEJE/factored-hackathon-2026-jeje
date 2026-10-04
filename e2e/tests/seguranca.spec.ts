// Cabeçalhos de segurança servidos pelo Caddy em toda resposta, da página e da API: o navegador
// não adivinha o tipo do conteúdo, a página não pode ser embutida em outro site (clickjacking; só a
// própria origem, para o site abrir o app na janela dele) e o endereço não vaza como referer. O
// esperado está escrito aqui e é conferido nas respostas reais.
import { expect, test } from "@playwright/test";

const ESPERADOS = {
  "x-content-type-options": "nosniff",
  "x-frame-options": "SAMEORIGIN",
  "content-security-policy": "frame-ancestors 'self'",
  "referrer-policy": "no-referrer",
};

for (const caminho of ["/", "/api/health"]) {
  test(`cabeçalhos de segurança em ${caminho}`, async ({ request }) => {
    const resposta = await request.get(caminho);
    expect(resposta.ok()).toBeTruthy();
    const cabecalhos = resposta.headers();
    for (const [nome, valor] of Object.entries(ESPERADOS)) expect(cabecalhos[nome], nome).toBe(valor);
  });
}

// Publicação (ACH-115): o Cloudflare diz em X-Forwarded-Proto o esquema em que o visitante chegou.
// Pedido em http volta em https (308) antes de qualquer resposta, e quem chegou em https recebe o
// HSTS, para o navegador nunca mais mandar a senha dos jurados em http. Sem o cabeçalho (a stack
// local, sem proxy na frente), nada muda.
test("pedido que chegou em http volta em https, no mesmo endereço", async ({ request, baseURL }) => {
  const resposta = await request.get("/api/health?x=1", {
    headers: { "X-Forwarded-Proto": "http" },
    maxRedirects: 0,
  });
  expect(resposta.status()).toBe(308);
  const host = new URL(baseURL ?? "").hostname;
  expect(resposta.headers()["location"]).toBe(`https://${host}/api/health?x=1`);
});

test("HSTS só para quem chegou em https", async ({ request }) => {
  const seguro = await request.get("/", { headers: { "X-Forwarded-Proto": "https" } });
  const local = await request.get("/");
  expect(seguro.headers()["strict-transport-security"]).toBe("max-age=31536000");
  expect(local.headers()["strict-transport-security"]).toBeUndefined();
});
