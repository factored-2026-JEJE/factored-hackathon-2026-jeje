// Cabeçalhos de segurança servidos pelo Caddy em toda resposta, da página e da API: o navegador
// não adivinha o tipo do conteúdo, a página não pode ser embutida em outro site (clickjacking) e
// o endereço não vaza como referer. O esperado está escrito aqui e é conferido nas respostas reais.
import { expect, test } from "@playwright/test";

const ESPERADOS = {
  "x-content-type-options": "nosniff",
  "x-frame-options": "DENY",
  "content-security-policy": "frame-ancestors 'none'",
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
