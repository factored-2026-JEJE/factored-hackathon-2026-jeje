// A aba da operação (2.10) contra a stack: o turno feito agora está entre os eventos da API, com o
// request_id da resposta (2.1b), e os últimos turnos na tela são os que a API deu à página, na ordem,
// com a regra. As outras jornadas fazem turnos em paralelo, então a tela é conferida contra a
// resposta que ela mesma recebeu.
import { expect, test } from "@playwright/test";
import { auth, personas, sessao } from "./comum";

type Evento = { criado_em: string; requisicao: string | null; regra: string | null; acao: string | null; efeito: string | null };

const escapar = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

test("o turno feito agora está nos eventos com o request_id, e a aba mostra os que a API deu", async ({ page, request }) => {
  const [persona] = await personas(request);
  const token = await sessao(request, persona!.customer_id);
  const aberta = await request.post("/api/conversas", { headers: auth(token), data: { idioma: "es" } });
  expect(aberta.status()).toBe(201);
  const { conversa_id } = await aberta.json();
  const turno = await request.post(`/api/conversas/${conversa_id}/turnos`, { headers: auth(token), data: { texto: "Hola" } });
  expect(turno.status()).toBe(200);
  const requisicao = turno.headers()["x-request-id"];
  expect(requisicao).toBeTruthy();
  const { regra } = await turno.json();
  const eventos: Evento[] = await (await request.get("/api/metricas/eventos?limite=50")).json();
  expect(eventos).toContainEqual(expect.objectContaining({ requisicao, regra }));
  // Só o que o log de eventos guarda: nem o cliente nem a mensagem.
  for (const e of eventos) expect(Object.keys(e).sort()).toEqual(["acao", "criado_em", "efeito", "regra", "requisicao"]);

  const daPagina = page.waitForResponse((r) => r.url().includes("/api/metricas/eventos"));
  await page.goto("/#operacao");
  const mostrados: Evento[] = await (await daPagina).json();
  expect(mostrados.length).toBeGreaterThan(0);
  const linhas = page.getByRole("region", { name: "Last events" }).getByText(/^\d\d:\d\d:\d\d · request_id=/);
  await expect(linhas).toHaveText(
    mostrados.map((e) => new RegExp(`request_id=${escapar(e.requisicao?.slice(0, 13) ?? "—")} · ${escapar(e.regra ?? "—")} · `)),
  );
});
