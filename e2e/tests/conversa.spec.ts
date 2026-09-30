// Jornadas da conversa no navegador contra a stack real: os três caminhos em espanhol e
// português. O esperado vem do texto aprovado + fatos da API, e todo efeito mostrado na tela é
// conferido na API (pré-caso, encaminhamento, histórico da conversa).
import { expect, type Page, test } from "@playwright/test";
import { auth, dataTexto, descricao, elegivel, personas, sessao, type Transacao, transacoes, valorTexto } from "./comum";

type Idioma = "es" | "pt";

const TEXTOS = {
  es: {
    abrir: "Conversar em español",
    contestar: (t: Transacao) =>
      `No reconozco el cobro de ${valorTexto(t.amount)} del ${dataTexto(t.transaction_date)}` +
      (t.merchant_name ? ` en ${t.merchant_name}` : ""),
    proposta: (d: string) =>
      `Puedo registrar una solicitud de revisión (pre-caso) de la transacción ${d}. Esto no devuelve el dinero ni resuelve la disputa. ¿Confirmas?`,
    confirmar: "Sí, confirmo",
    recusada: "¿Por qué rechazaron mi compra?",
    comCodigo: (d: string, codigo: string, motivo: string) =>
      `La transacción ${d} fue rechazada. Motivo informado en el código ${codigo}: ${motivo} (significado genérico del estándar ISO 8583).`,
    semMotivo: (d: string) =>
      `La transacción ${d} fue rechazada y no tenemos el motivo registrado. Si quieres, te comunico con un agente.`,
    fraude: "Me robaron la tarjeta",
    qualCartao: "Por seguridad, voy a bloquear la tarjeta afectada.",
    depois: "¿y ahora?",
    comHumano: (a: string) => `Tu caso ya está con un agente (referencia ${a}); la conversación sigue con esa persona.`,
  },
  pt: {
    abrir: "Conversar em português",
    contestar: (t: Transacao) =>
      `Não reconheço a cobrança de ${valorTexto(t.amount)} do dia ${dataTexto(t.transaction_date)}` +
      (t.merchant_name ? ` na ${t.merchant_name}` : ""),
    proposta: (d: string) =>
      `Posso registrar um pedido de revisão (pré-caso) da transação ${d}. Isso não devolve o dinheiro nem resolve a contestação. Você confirma?`,
    confirmar: "Sim, confirmo",
    recusada: "Por que recusaram minha compra?",
    comCodigo: (d: string, codigo: string, motivo: string) =>
      `A transação ${d} foi recusada. Motivo informado no código ${codigo}: ${motivo} (significado genérico do padrão ISO 8583).`,
    semMotivo: (d: string) =>
      `A transação ${d} foi recusada e não temos o motivo registrado. Se quiser, eu passo você para um atendente.`,
    fraude: "Roubaram meu cartão",
    qualCartao: "Por segurança, vou bloquear o cartão afetado.",
    depois: "e agora?",
    comHumano: (a: string) => `Seu caso já está com um atendente (referência ${a}); a conversa segue com essa pessoa.`,
  },
} as const;

// Significado genérico dos códigos catalogados (texto aprovado; oráculo desta suíte).
const MOTIVO: Record<string, Record<Idioma, string>> = {
  "51": { es: "fondos insuficientes", pt: "saldo insuficiente" },
  "14": { es: "número de tarjeta inválido", pt: "número de cartão inválido" },
  "54": { es: "tarjeta vencida", pt: "cartão vencido" },
  "05": { es: "no autorizada por el emisor", pt: "não autorizada pelo emissor" },
};

async function entrarEConversar(page: Page, nome: string, idioma: Idioma) {
  await page.goto("/");
  await page.getByRole("button", { name: `Entrar como ${nome}` }).click();
  await page.getByRole("button", { name: TEXTOS[idioma].abrir }).click();
  await expect(page.getByRole("log", { name: "Mensagens" }).locator("li")).toHaveCount(1);
}

async function dizer(page: Page, mensagem: string) {
  const falas = page.getByRole("log", { name: "Mensagens" }).locator("li");
  const antes = await falas.count();
  await page.getByLabel("Mensagem").fill(mensagem);
  await page.getByRole("button", { name: "Enviar" }).click();
  await expect(falas).toHaveCount(antes + 2);
  return falas.last();
}

async function historico(page: Page, token: string) {
  const conversa = await page.evaluate(() => sessionStorage.getItem("jeje.conversa"));
  const resposta = await page.request.get(`/api/conversas/${conversa}`, { headers: auth(token) });
  expect(resposta.status()).toBe(200);
  return resposta.json() as Promise<{ turnos: { acao: string; regra: string }[] }>;
}

for (const idioma of ["es", "pt"] as const) {
  const t = TEXTOS[idioma];

  test(`caminho normal (${idioma}): contestar, confirmar e reencontrar o pré-caso sem duplicar`, async ({ page, request }, info) => {
    // Pista única (valor e dia) entre as transações do cliente: a conversa identifica sem perguntar.
    const unica = (x: Transacao, todas: Transacao[]) =>
      todas.filter((o) => o.amount === x.amount && o.transaction_date.slice(0, 10) === x.transaction_date.slice(0, 10)).length === 1;
    const { persona, transacao, token } = await elegivel(request, `conversa-${idioma}`, info, unica);
    await entrarEConversar(page, persona.nome, idioma);

    const proposta = await dizer(page, t.contestar(transacao));
    await expect(proposta).toContainText(t.proposta(descricao(transacao, idioma)));
    const doCliente = async () =>
      ((await (await request.get("/api/minhas/pre-casos", { headers: auth(token) })).json()) as { protocolo: string; transaction_id: string }[])
        .filter((p) => p.transaction_id === transacao.transaction_id);
    expect(await doCliente()).toEqual([]); // proposta não é efeito

    await page.getByRole("group", { name: "Confirmação" }).getByRole("button", { name: t.confirmar }).click();
    const recebido = page.getByRole("status").filter({ hasText: "Pré-caso recebido" });
    await expect(recebido).toContainText(/Pré-caso recebido: protocolo PC-\d+/);
    const protocolo = (await recebido.textContent())!.match(/PC-\d+/)![0];
    expect(await doCliente()).toEqual([expect.objectContaining({ protocolo })]);
    await expect(page.getByRole("region", { name: "Meus pré-casos" })).toContainText(protocolo);

    // Recarregar reabre a conversa pelo histórico: nada é reenviado nem duplicado.
    await page.reload();
    await expect(page.getByRole("log", { name: "Mensagens" })).toContainText(protocolo);
    expect(await doCliente()).toEqual([expect.objectContaining({ protocolo })]);
    const acoes = (await historico(page, token)).turnos.map((x) => x.acao);
    expect(acoes).toEqual(["propor_pre_caso", "registrar_pre_caso"]);
  });

  test(`caminho ambíguo (${idioma}): lista só as recusas do cliente e explica a escolhida`, async ({ page, request }) => {
    // Primeiro cliente com duas ou mais recusas: a pergunta sem pista não pode escolher sozinha.
    let achado: { nome: string; token: string; recusadas: Transacao[] } | null = null;
    for (const p of await personas(request)) {
      const token = await sessao(request, p.customer_id);
      const recusadas = (await transacoes(request, token)).filter((x) => x.transaction_status === "Declined");
      if (recusadas.length >= 2) {
        achado = { nome: p.nome, token, recusadas };
        break;
      }
    }
    expect(achado, "nenhuma persona com duas recusas").not.toBeNull();
    const { nome, token, recusadas } = achado!;
    await entrarEConversar(page, nome, idioma);

    await dizer(page, t.recusada);
    const opcoes = page.getByRole("group", { name: "Opções" }).getByRole("button");
    await expect(opcoes).toHaveText(recusadas.slice(0, 5).map((x, i) => `${i + 1}. ${descricao(x, idioma)}`));

    const escolhida = recusadas[0]!;
    const situacao = await (await request.get(`/api/minhas/transacoes/${escolhida.transaction_id}/situacao`, { headers: auth(token) })).json();
    await opcoes.first().click();
    const falas = page.getByRole("log", { name: "Mensagens" }).locator("li");
    const d = descricao(escolhida, idioma);
    const esperado = situacao.decisao.regra === "POL-CON-03"
      ? t.comCodigo(d, escolhida.response_code!, MOTIVO[escolhida.response_code!]![idioma])
      : t.semMotivo(d);
    await expect(falas.last()).toContainText(esperado);
    const turnos = (await historico(page, token)).turnos;
    expect(turnos.map((x) => [x.acao, x.regra])).toEqual([["esclarecer", "POL-CON-02"], ["responder", situacao.decisao.regra]]);
  });

  test(`caminho humano (${idioma}): relato de fraude encaminha e aparece na fila do atendente`, async ({ page, request }) => {
    const [primeira] = await personas(request);
    await entrarEConversar(page, primeira!.nome, idioma);
    let relato = await dizer(page, t.fraude);
    // Com vários cartões ativos, o assistente pergunta qual antes de bloquear e encaminhar (PRD-007).
    if ((await relato.textContent())!.includes(t.qualCartao)) relato = await dizer(page, "1");
    const comHumano = page.getByRole("status").filter({ hasText: "Com atendimento humano" });
    await expect(comHumano).toContainText(/AT-\d+/);
    const atendimento = (await comHumano.textContent())!.match(/AT-\d+/)![0];

    const naFila = page.getByRole("region", { name: "Fila do atendimento humano" }).getByRole("listitem", { name: `Encaminhamento ${atendimento}` });
    await expect(naFila).toContainText("POL-HUM-01");
    await expect(naFila).toContainText(`Pedido: “${t.fraude}”`);
    const fila: { id: string; regra: string; idioma: string; pedido: string }[] = await (await request.get("/api/atendimento/fila?limite=100")).json();
    expect(fila).toContainEqual(expect.objectContaining({ id: atendimento, regra: "POL-HUM-01", idioma, pedido: t.fraude }));

    // O relato bloqueia o cartão ativo (ou cita o bloqueio de uma rodada anterior), e o bloqueio
    // aparece no console; sem cartão ativo, nenhum bloqueio é citado.
    const citados = (await relato.textContent())!.match(/BL-\d{8}/g) ?? [];
    const ativos: { id: string; customer_id: string }[] = await (await request.get("/api/atendimento/bloqueios?limite=100")).json();
    const doCliente = ativos.filter((b) => b.customer_id === primeira!.customer_id).map((b) => b.id);
    expect(citados.length > 0).toBe(doCliente.length > 0);
    for (const id of citados) expect(doCliente).toContain(id);
    const painel = page.getByRole("region", { name: "Bloqueios de cartão" });
    for (const id of citados) await expect(painel.getByRole("listitem", { name: `Bloqueio ${id}` })).toBeVisible();

    // Depois do encaminhamento, a automação só lembra quem está com o caso.
    const lembrete = await dizer(page, t.depois);
    await expect(lembrete).toContainText(t.comHumano(atendimento));

    // O atendente assume: sai da fila aberta, na tela e na API (e a suíte não deixa sobra).
    await naFila.getByRole("button", { name: `Assumir ${atendimento}` }).click();
    await expect(page.getByRole("status").filter({ hasText: `Você assumiu ${atendimento}.` })).toBeVisible();
    await expect(naFila).toHaveCount(0);
    const depois: { id: string }[] = await (await request.get("/api/atendimento/fila?limite=100")).json();
    expect(depois.map((e) => e.id)).not.toContain(atendimento);
  });
}
