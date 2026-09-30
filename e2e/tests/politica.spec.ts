import { expect, test } from "@playwright/test";
import { diasEntre, LIMITES, noturnaDigital, type Transacao } from "./comum";

// Matriz de autonomia (DEV-006, limites PRD-001) reescrita aqui como oráculo, independente do
// código da política. O valor em USD só é conhecido aqui quando a moeda é USD; nenhuma transação
// da base real passa de USD 10.000, então transferência atípica só existe em USD na fixture.
const CATALOGADOS = new Set(["05", "14", "51", "54"]);
const atipica = (t: Transacao) =>
  t.transaction_type === "Transfer" && t.currency === "USD" && Number(t.amount) > LIMITES.seguranca;

function regraEsperada(t: Transacao): string {
  if (atipica(t)) return "POL-SEG-01";
  if (t.transaction_status === "Approved") return "POL-CON-01";
  if (t.transaction_status === "Declined") return CATALOGADOS.has(t.response_code ?? "") ? "POL-CON-03" : "POL-CON-04";
  if (t.transaction_status === "Pending" || t.transaction_status === "Reversed") return "POL-CON-05";
  return "POL-CON-04";
}

test("situação de cada transação das personas segue a matriz e contestação só avança para Approved", async ({ request }) => {
  const personas: { customer_id: string }[] = await (await request.get("/api/personas")).json();
  const vistas: { auth: { Authorization: string }; transacoes: Transacao[] }[] = [];
  for (const persona of personas.slice(0, 3)) {
    const { token } = await (await request.post("/api/sessoes", { data: { customer_id: persona.customer_id } })).json();
    const auth = { Authorization: `Bearer ${token}` };
    const transacoes: Transacao[] = await (await request.get("/api/minhas/transacoes?limite=20", { headers: auth })).json();
    vistas.push({ auth, transacoes });
  }
  // Janela (PRD-008): contada do último dia dos dados. A compra mais recente vista nas personas é um
  // limite inferior desse dia (na fixture, é ele mesmo): mais velha que a janela em relação a ela,
  // a compra está fora com certeza; mais nova, pode estar fora se a base for mais recente.
  const maisRecente = vistas.flatMap((v) => v.transacoes.map((t) => t.transaction_date)).sort().at(-1) ?? "";
  let avaliadas = 0;
  for (const { auth, transacoes } of vistas) {
    // POL-DISP-03 precisa apontar o protocolo existente da transação. A lista é relida na hora:
    // outros testes em paralelo podem abrir pré-casos durante este.
    const protocoloAberto = async (transacaoId: string) => {
      const abertos: { protocolo: string; transaction_id: string }[] = await (
        await request.get("/api/minhas/pre-casos", { headers: auth })
      ).json();
      return abertos.find((p) => p.transaction_id === transacaoId)?.protocolo;
    };
    const recentes = async () => {
      const abertos: { criado_em: string }[] = await (await request.get("/api/minhas/pre-casos", { headers: auth })).json();
      const hoje = new Date().toISOString();
      return abertos.filter((p) => diasEntre(p.criado_em, hoje) < LIMITES.reincidenciaDias).length;
    };
    for (const t of transacoes) {
      const situacao = await (await request.get(`/api/minhas/transacoes/${t.transaction_id}/situacao`, { headers: auth })).json();
      expect(situacao.decisao.regra, t.transaction_id).toBe(regraEsperada(t));
      const contestacao = await (await request.get(`/api/minhas/transacoes/${t.transaction_id}/contestacao`, { headers: auth })).json();
      if (atipica(t)) expect(contestacao).toMatchObject({ regra: "POL-SEG-01", acao: "humano" });
      else if (t.transaction_status !== "Approved") expect(contestacao).toMatchObject({ regra: "POL-DISP-02", acao: "humano" });
      else if (contestacao.regra === "POL-DISP-03") expect(await protocoloAberto(t.transaction_id)).toBe(contestacao.detalhe);
      else if (diasEntre(t.transaction_date, maisRecente) > LIMITES.janelaDias) expect(contestacao).toMatchObject({ regra: "POL-HUM-05", acao: "humano" });
      else if (contestacao.regra === "POL-HUM-05") expect(diasEntre(t.transaction_date, maisRecente)).toBeGreaterThanOrEqual(0);
      // Reincidência (PRD-008): só com pré-casos recentes suficientes, relidos depois da resposta.
      else if (contestacao.regra === "POL-HUM-06") expect(await recentes()).toBeGreaterThanOrEqual(LIMITES.reincidencia);
      else if (t.currency !== "USD") expect(["POL-DISP-01", "POL-HUM-02", "POL-HUM-04"]).toContain(contestacao.regra);
      else if (noturnaDigital(t) && Number(t.amount) > LIMITES.noturno) expect(contestacao.regra).toBe("POL-HUM-04");
      // Noturna digital dentro do limite: o que já foi registrado hoje decide (limite do dia).
      else if (noturnaDigital(t)) expect(["POL-DISP-01", "POL-HUM-04"]).toContain(contestacao.regra);
      else expect(contestacao.regra).toBe(Number(t.amount) > LIMITES.padrao ? "POL-HUM-02" : "POL-DISP-01");
      avaliadas += 1;
    }
  }
  expect(avaliadas).toBeGreaterThan(0);
});
