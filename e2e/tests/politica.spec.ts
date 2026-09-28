import { expect, test } from "@playwright/test";

type Transacao = { transaction_id: string; transaction_status: string; response_code: string | null };

// Matriz de autonomia (DEV-006) reescrita aqui como oráculo, independente do código da política.
const CATALOGADOS = new Set(["05", "14", "51", "54"]);
function regraEsperada(t: Transacao): string {
  if (t.transaction_status === "Approved") return "POL-CON-01";
  if (t.transaction_status === "Declined") return CATALOGADOS.has(t.response_code ?? "") ? "POL-CON-03" : "POL-CON-04";
  if (t.transaction_status === "Pending" || t.transaction_status === "Reversed") return "POL-CON-05";
  return "POL-CON-04";
}

test("situação de cada transação das personas segue a matriz e contestação só avança para Approved", async ({ request }) => {
  const personas: { customer_id: string }[] = await (await request.get("/api/personas")).json();
  let avaliadas = 0;
  for (const persona of personas.slice(0, 3)) {
    const { token } = await (await request.post("/api/sessoes", { data: { customer_id: persona.customer_id } })).json();
    const auth = { Authorization: `Bearer ${token}` };
    const transacoes: Transacao[] = await (await request.get("/api/minhas/transacoes?limite=20", { headers: auth })).json();
    for (const t of transacoes) {
      const situacao = await (await request.get(`/api/minhas/transacoes/${t.transaction_id}/situacao`, { headers: auth })).json();
      expect(situacao.decisao.regra, t.transaction_id).toBe(regraEsperada(t));
      const contestacao = await (await request.get(`/api/minhas/transacoes/${t.transaction_id}/contestacao`, { headers: auth })).json();
      if (t.transaction_status !== "Approved") expect(contestacao).toMatchObject({ regra: "POL-DISP-02", acao: "humano" });
      else expect(["POL-DISP-01", "POL-HUM-02"]).toContain(contestacao.regra);
      avaliadas += 1;
    }
  }
  expect(avaliadas).toBeGreaterThan(0);
});
