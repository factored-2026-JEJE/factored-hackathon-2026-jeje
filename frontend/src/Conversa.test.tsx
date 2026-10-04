// Conversa contra um servidor mínimo na fronteira de rede: a regra é decidida pela API real
// (testada no backend e no E2E). Aqui: a tela (a do design de 03/10, em inglês por padrão) só mostra
// o que a API respondeu, envia o texto certo, não envia duas vezes, reenvia a mesma mensagem e reabre
// a conversa sem repetir nada.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ResultadoDoTurno } from "./api/cliente";
import { LinguaDoAppProvider } from "./app/LinguaDoApp";
import { Conversa } from "./Conversa";

// "perdida": a API processa o turno e a conexão cai na volta; "rede": cai antes de chegar à API.
type Resposta = { status: number; corpo: unknown } | "pendente" | "perdida" | "rede";

const ABERTA = { conversa_id: "C1", idioma: "es", estado: "livre", resposta: "Hola. ¿En qué te ayudo?" };

function turno(parcial: Partial<ResultadoDoTurno>): ResultadoDoTurno {
  return {
    conversa_id: "C1",
    numero: 1,
    idioma: "es",
    intencao: "contestar",
    regra: "POL-DISP-01",
    acao: "propor_pre_caso",
    estado: "confirmando",
    resposta: "Puedo registrar una solicitud de revisión (pre-caso) de la transacción en Uber. ¿Confirmas?",
    transaction_id: "TRX-1",
    opcoes: [],
    proposta: { id: "P1", transaction_id: "TRX-1", expira_em: "2099-01-01T00:00:00Z" },
    protocolo: null,
    atendimento: null,
    bloqueio: null,
    descricao: null,
    interpretacao: "regras",
    efeito: null,
    fontes: [],
    resolucao: null,
    recibo: null,
    ...parcial,
  };
}

const REGISTRADO = turno({
  numero: 2,
  intencao: "desconhecida",
  acao: "registrar_pre_caso",
  estado: "livre",
  resposta: "Registré la solicitud con el protocolo PC-00000009.",
  proposta: null,
  protocolo: "PC-00000009",
});

/** Servidor na fronteira de rede: responde os turnos na ordem, registra os corpos enviados e
 * guarda o histórico do que processou. `historicoFalha`: quantas leituras do histórico falham. */
function servidor(turnos: Resposta[], historico?: unknown, historicoFalha = 0) {
  const enviados: string[] = [];
  const processados: Record<string, unknown>[] = [];
  let liberar: (() => void) | null = null;
  const processar = (mensagem: string, t: ResultadoDoTurno) =>
    processados.push({ numero: processados.length + 1, mensagem, resposta: t.resposta, regra: t.regra, acao: t.acao, estado: t.estado, criado_em: "2026-09-29T10:00:00Z" });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const r = (status: number, corpo: unknown) =>
        new Response(JSON.stringify(corpo), { status, headers: { "X-Request-ID": `req-${enviados.length}` } });
      if (url === "/api/conversas" && init?.method === "POST") return r(201, ABERTA);
      if (url === "/api/conversas/C1/turnos" && init?.method === "POST") {
        const mensagem = JSON.parse(String(init.body)).texto;
        enviados.push(mensagem);
        const proxima = turnos.shift() ?? { status: 500, corpo: {} };
        if (proxima === "rede") throw new TypeError("Failed to fetch");
        if (proxima === "perdida") {
          processar(mensagem, REGISTRADO);
          throw new TypeError("Failed to fetch");
        }
        if (proxima === "pendente") {
          await new Promise<void>((ok) => (liberar = ok));
          processar(mensagem, REGISTRADO);
          return r(200, REGISTRADO);
        }
        if (proxima.status === 200) processar(mensagem, proxima.corpo as ResultadoDoTurno);
        return r(proxima.status, proxima.corpo);
      }
      if (url === "/api/conversas/C1") {
        if (historico) return r(200, historico);
        if (historicoFalha-- > 0) throw new TypeError("Failed to fetch");
        const estado = (processados.at(-1)?.estado as string | undefined) ?? "livre";
        return r(200, { conversa_id: "C1", idioma: "es", estado, turnos: processados });
      }
      return r(404, { detail: "Not Found" });
    }),
  );
  return { enviados, liberar: () => liberar?.() };
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
});

const CAIXA = "Write as the customer, in Spanish or Portuguese";

function montar(aoMudar = vi.fn()) {
  render(<Conversa token="tok" aoExpirar={vi.fn()} aoMudar={aoMudar} />);
  return aoMudar;
}

// Sem conversa aberta, a primeira mensagem abre uma na língua da frase (a saudação da API não aparece).
async function abrirEPedir(pedido = "No reconozco el cobro de Uber") {
  await userEvent.type(await screen.findByLabelText(CAIXA), pedido);
  await userEvent.click(screen.getByRole("button", { name: "Send" }));
}

/** O "Why this answer?" da resposta: as linhas do design (rótulo e valor). */
async function porQue(texto: RegExp | string) {
  const resposta = (await screen.findByText(texto)).closest("li");
  if (!resposta) throw new Error("resposta fora da lista");
  await userEvent.click(within(resposta).getByRole("button", { name: /Why this answer/ }));
  const linhas = Array.from(resposta.querySelectorAll("dt")).map((dt) => [dt.textContent, dt.nextElementSibling?.textContent]);
  return Object.fromEntries(linhas) as Record<string, string>;
}

test("protocolo só aparece depois que a API registra, e a fila é avisada", async () => {
  const { enviados, liberar } = servidor([{ status: 200, corpo: turno({}) }, "pendente"]);
  const aoMudar = montar();
  await abrirEPedir();
  const confirmar = await screen.findByRole("button", { name: "Sí, confirmo" });
  await userEvent.click(confirmar);
  expect(await screen.findByText("reading · rules …")).toBeInTheDocument();
  expect(screen.queryByText(/pre-case received/)).not.toBeInTheDocument();
  expect(aoMudar).not.toHaveBeenCalled();
  liberar();
  expect(await screen.findByText("PC-00000009 · pre-case received")).toBeInTheDocument();
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo"]);
  expect(aoMudar).toHaveBeenCalledTimes(1);
});

test("pré-caso já existente não vira 'recebido' de novo", async () => {
  const existente = turno({ regra: "POL-DISP-03", acao: "responder", estado: "livre", proposta: null, protocolo: "PC-00000003" });
  servidor([{ status: 200, corpo: existente }]);
  montar();
  await abrirEPedir();
  expect(await screen.findByText(existente.resposta)).toBeInTheDocument();
  expect(screen.queryByText(/pre-case received/)).not.toBeInTheDocument();
});

test("opções da API viram botões que enviam o número escolhido", async () => {
  const opcoes = [
    { numero: 1, transaction_id: "TRX-2", descricao: "en Cine Premium de USD 45,90 (11/03/2025)" },
    { numero: 2, transaction_id: "TRX-1", descricao: "en Streaming Plus de USD 45,90 (10/03/2025)" },
  ];
  const { enviados } = servidor([
    { status: 200, corpo: turno({ regra: "POL-CON-02", acao: "esclarecer", estado: "esclarecendo", opcoes, proposta: null }) },
    { status: 200, corpo: turno({ numero: 2 }) },
  ]);
  montar();
  await abrirEPedir("No reconozco un cobro de 45,90");
  // O passo 2 (a transação) enquanto a API pergunta qual.
  expect(await screen.findByText("2 · Transaction")).toHaveAttribute("aria-current", "step");
  await userEvent.click(await screen.findByRole("button", { name: "en Streaming Plus de USD 45,90 (10/03/2025)" }));
  await screen.findByRole("button", { name: "Sí, confirmo" });
  expect(screen.getByText("3 · Confirmation")).toHaveAttribute("aria-current", "step");
  expect(enviados).toEqual(["No reconozco un cobro de 45,90", "2"]);
});

test("não envia duas vezes enquanto espera a resposta", async () => {
  const { enviados, liberar } = servidor([{ status: 200, corpo: turno({}) }, "pendente"]);
  montar();
  await abrirEPedir();
  const confirmar = await screen.findByRole("button", { name: "Sí, confirmo" });
  await userEvent.click(confirmar);
  // Enquanto espera, nada de enviar de novo: nem pelo botão, nem pela caixa.
  await userEvent.click(confirmar);
  await userEvent.type(screen.getByLabelText(CAIXA), "Sí, confirmo{Enter}");
  liberar();
  await screen.findByText("PC-00000009 · pre-case received");
  expect(enviados.filter((t) => t === "Sí, confirmo")).toHaveLength(1);
});

test("503 diz que nada foi criado e reenviar manda a mesma mensagem", async () => {
  const naoRegistrado = { status: 503, corpo: { detail: "Turno não registrado; nada foi criado. Tente de novo." } };
  const { enviados } = servidor([{ status: 200, corpo: turno({}) }, naoRegistrado, { status: 200, corpo: REGISTRADO }]);
  montar();
  await abrirEPedir();
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("nada foi criado");
  expect(screen.queryByText(/pre-case received/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Send again" }));
  expect(await screen.findByText("PC-00000009 · pre-case received")).toBeInTheDocument();
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo", "Sí, confirmo"]);
});

test("resposta perdida depois do sim: a tela relê a conversa, mostra o protocolo e não reenvia", async () => {
  const { enviados } = servidor([{ status: 200, corpo: turno({}) }, "perdida"]);
  const aoMudar = montar();
  await abrirEPedir();
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByText("Registré la solicitud con el protocolo PC-00000009.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Send again" })).not.toBeInTheDocument();
  expect(aoMudar).toHaveBeenCalledTimes(1);
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo"]);
});

test("mensagem que não chegou ao servidor continua com Reenviar, e o reenvio registra", async () => {
  const { enviados } = servidor([{ status: 200, corpo: turno({}) }, "rede", { status: 200, corpo: REGISTRADO }]);
  montar();
  await abrirEPedir();
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("No answer from the server");
  await userEvent.click(screen.getByRole("button", { name: "Send again" }));
  expect(await screen.findByText("PC-00000009 · pre-case received")).toBeInTheDocument();
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo", "Sí, confirmo"]);
});

test("reenviar relê a conversa antes: se o servidor já processou, não manda de novo", async () => {
  const { enviados } = servidor([{ status: 200, corpo: turno({}) }, "perdida"], undefined, 1);
  const aoMudar = montar();
  await abrirEPedir();
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("No answer from the server");
  await userEvent.click(screen.getByRole("button", { name: "Send again" }));
  expect(await screen.findByText("Registré la solicitud con el protocolo PC-00000009.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(aoMudar).toHaveBeenCalledTimes(1);
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo"]);
});

test("recarregar reabre a conversa guardada pelo histórico, sem enviar nada", async () => {
  sessionStorage.setItem("jeje.conversa", "C1");
  const historico = {
    conversa_id: "C1",
    idioma: "pt",
    estado: "confirmando",
    turnos: [
      { numero: 1, mensagem: "Não reconheço a cobrança da Uber", resposta: "Posso registrar… Você confirma?", regra: "POL-DISP-01", acao: "propor_pre_caso", estado: "confirmando", criado_em: "2026-09-28T10:00:00Z" },
    ],
  };
  const { enviados } = servidor([], historico);
  montar();
  expect(await screen.findByText("Não reconheço a cobrança da Uber")).toBeInTheDocument();
  expect(screen.getByText("Posso registrar… Você confirma?")).toBeInTheDocument();
  // Reaberta em português, com a confirmação pendente oferecida de novo (sem ter sido enviada).
  expect(screen.getByRole("button", { name: "Sim, confirmo" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Não" })).toBeInTheDocument();
  expect(enviados).toEqual([]);
});

test("encaminhamento mostra o atendimento humano e avisa a fila", async () => {
  const encaminhado = turno({
    intencao: "fraude",
    regra: "POL-HUM-01",
    acao: "humano",
    estado: "com_humano",
    resposta: "Por seguridad, un agente va a atender este caso.",
    proposta: null,
    atendimento: "AT-00000001",
  });
  servidor([{ status: 200, corpo: encaminhado }]);
  const aoMudar = montar();
  await abrirEPedir("Me robaron la tarjeta");
  expect(await screen.findByText("Handed to a person")).toBeInTheDocument();
  expect(aoMudar).toHaveBeenCalledTimes(1);
});

test("conversa encerrada pela recarga avisa, trava o envio e deixa só a nova conversa", async () => {
  const encerrada = turno({
    intencao: "desconhecida",
    regra: "ENCERRADA",
    acao: "encerrada",
    estado: "encerrada",
    resposta: "Esta conversación se cerró porque los datos se actualizaron.",
    transaction_id: null,
    proposta: null,
  });
  servidor([{ status: 200, corpo: encerrada }]);
  montar();
  await abrirEPedir("sí");
  expect(await screen.findByText("Conversation closed: the data was reloaded. Start a new conversation.")).toBeInTheDocument();
  expect(screen.getByLabelText(CAIXA)).toBeDisabled();
  expect(screen.getByRole("button", { name: "New conversation" })).toBeEnabled();
});

test("bloqueio feito na conversa avisa o console do atendente", async () => {
  const bloqueado = turno({
    intencao: "bloquear",
    regra: "POL-BLQ-02",
    acao: "bloquear_cartao",
    estado: "livre",
    resposta: "Bloqueé tu tarjeta de crédito terminada en 9241 (bloqueo completo simulado, referencia BL-00000001).",
    transaction_id: null,
    proposta: null,
    bloqueio: "BL-00000001",
  });
  servidor([{ status: 200, corpo: bloqueado }]);
  const aoMudar = montar();
  await abrirEPedir("quiero bloquear mi tarjeta");
  expect(await screen.findByText(/referencia BL-00000001/)).toBeInTheDocument();
  expect(aoMudar).toHaveBeenCalledTimes(1);
});

test("por que esta resposta: as linhas do design, com o X-Request-ID, quem leu, a regra e o que ela quer dizer, a ação e o efeito", async () => {
  const proposta = turno({
    descricao: "Contestação dentro dos limites simulados.",
    interpretacao: "leitor:e5@429a8eaca51b",
    efeito: "P1",
    fontes: ["curated.transactions", "app.propostas_pre_caso"],
  });
  servidor([{ status: 200, corpo: proposta }]);
  montar();
  await abrirEPedir();
  const linhas = await porQue(/Puedo registrar una solicitud/);
  expect(linhas).toMatchObject({
    "X-Request-ID": "req-1",
    language: "es",
    "read by": "leitor:e5@429a8eaca51b",
    intent: "dispute",
    rule: "POL-DISP-01",
    // O que a regra quer dizer, na língua da interface (a lista de regras do site).
    meaning: "Dispute within limits: proposes the pre-case, records only on an explicit yes.",
    action: "propose pre-case",
    effect: "proposal · waiting for yes · P1",
  });
  expect(linhas).not.toHaveProperty("protocol");
});

const pelo = (resolucao: ResultadoDoTurno["resolucao"], transaction_id: string | null = "TRX-1") =>
  turno({ resolucao, transaction_id });

// Testes nomeados, sem `test.each`: o meta-check dos mutantes coleta o nome pelo `vitest list`, que
// não expande o "%s" do nome.
const comoFoiAchada = async (corpo: ResultadoDoTurno, esperado: string) => {
  servidor([{ status: 200, corpo }]);
  montar();
  await abrirEPedir();
  expect((await porQue(/Puedo registrar una solicitud/)).transaction).toBe(esperado);
};

test("por que esta resposta diz como a transação foi achada (DEV-071): o ranking escolheu", () =>
  comoFoiAchada(
    pelo({ resolvedor: "ranking", calibracao: "764ce683d347", probabilidade: 0.987, possiveis: 2 }),
    "ranking with a guarantee (α = 5%) · probability 0.99 · 2 candidates · calibration 764ce683d347",
  ));

test("por que esta resposta diz como a transação foi achada (DEV-071): o ranking só ordenou as opções", () =>
  comoFoiAchada(
    pelo({ resolvedor: "ranking", calibracao: "764ce683d347", probabilidade: 0.6, possiveis: 3 }, null),
    "ranking without a guarantee: shows candidates · probability 0.60 · 3 candidates · calibration 764ce683d347",
  ));

test("por que esta resposta diz como a transação foi achada (DEV-071): o filtro exato achou", () =>
  comoFoiAchada(
    pelo({ resolvedor: "filtro", calibracao: null, probabilidade: null, possiveis: null }),
    "exact filter",
  ));

test("por que esta resposta mostra de onde veio o fato: arquivo, linha e versão dos dados (DEV-044)", async () => {
  const recibo = { transaction_id: "TRX-1", arquivo: "transactions/day=10/part-0.csv", linha: 7, versao_dos_dados: "abc123def456789" };
  servidor([{ status: 200, corpo: turno({ recibo }) }]);
  montar();
  await abrirEPedir();
  expect(await porQue(/Puedo registrar una solicitud/)).toMatchObject({
    file: "transactions/day=10/part-0.csv",
    line: "7",
    "data version": "abc123def456",
  });
});

test("turno reaberto pelo histórico mostra só a regra e a ação", async () => {
  sessionStorage.setItem("jeje.conversa", "C1");
  const historico = {
    conversa_id: "C1",
    idioma: "es",
    estado: "confirmando",
    turnos: [
      {
        numero: 1,
        mensagem: "No reconozco el cobro de Uber",
        resposta: "Puedo registrar una solicitud de revisión (pre-caso) de la transacción en Uber. ¿Confirmas?",
        regra: "POL-DISP-01",
        acao: "propor_pre_caso",
        estado: "confirmando",
        criado_em: "2026-09-29T10:00:00Z",
      },
    ],
  };
  servidor([], historico);
  montar();
  const linhas = await porQue(/Puedo registrar una solicitud/);
  expect(linhas).toMatchObject({ rule: "POL-DISP-01", action: "propose pre-case" });
  expect(linhas).not.toHaveProperty("effect");
});

async function atalhoDeBloqueio(idioma: "es" | "pt", rotulo: string) {
  const enviados: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const r = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
      if (url === "/api/conversas" && init?.method === "POST") return r(201, { ...ABERTA, idioma });
      if (url === "/api/conversas/C1/turnos") {
        enviados.push(JSON.parse(String(init?.body)).texto);
        return r(200, turno({ idioma, resposta: "recebido", estado: "livre", proposta: null }));
      }
      return r(404, {});
    }),
  );
  // A língua dos atalhos é a da conversa; antes dela, a da interface (português, ou espanhol).
  window.history.replaceState(null, "", `/?lang=${idioma === "pt" ? "pt" : "en"}`);
  render(
    <LinguaDoAppProvider>
      <Conversa token="tok" aoExpirar={vi.fn()} aoMudar={vi.fn()} />
    </LinguaDoAppProvider>,
  );
  const atalhos = await screen.findByRole("group", { name: idioma === "pt" ? "Atalhos" : "Shortcuts" });
  await userEvent.click(within(atalhos).getByRole("button", { name: rotulo }));
  expect(await screen.findByText("recebido")).toBeInTheDocument();
  return enviados;
}

test("atalho manda a frase pronta em espanhol na conversa em espanhol", async () => {
  expect(await atalhoDeBloqueio("es", "Bloquear tarjeta")).toEqual(["Quiero bloquear mi tarjeta"]);
});

test("atalho manda a frase pronta em português na conversa em português", async () => {
  expect(await atalhoDeBloqueio("pt", "Bloquear cartão")).toEqual(["Quero bloquear meu cartão"]);
});

test("o atalho do pedido em português segue o rótulo do design e manda a frase que as regras entendem", async () => {
  expect(await atalhoDeBloqueio("pt", "Meu pedido")).toEqual(["Como está meu pedido de revisão?"]);
});

test("a oferta do atendente tem rótulos claros e continua mandando sí e no", async () => {
  const oferta = turno({
    regra: "RESUMO",
    acao: "oferecer_humano",
    estado: "oferecendo_humano",
    resposta: "Si no es eso, ¿quieres que te comunique con un agente?",
    proposta: null,
  });
  const { enviados } = servidor([{ status: 200, corpo: oferta }, { status: 200, corpo: oferta }]);
  montar();
  await abrirEPedir("algo");
  // Os rótulos do design na língua da conversa; o que vai é o sí e o no.
  const grupo = within(await screen.findByRole("group", { name: "Options" }));
  await userEvent.click(grupo.getByRole("button", { name: "Seguir aquí" }));
  // O atalho "Hablar con un agente" também existe: o da oferta é o do grupo das opções.
  await userEvent.click(within(await screen.findByRole("group", { name: "Options" })).getByRole("button", { name: "Hablar con un agente" }));
  expect(enviados).toEqual(["algo", "No", "Sí"]);
});

test("pergunta antes de bloquear (POL-BLQ-07) mostra os mesmos botões do sim", async () => {
  const pergunta = turno({
    intencao: "bloquear",
    regra: "POL-BLQ-07",
    acao: "esclarecer",
    estado: "confirmando_bloqueio",
    resposta: "Puedo bloquear tu tarjeta ahora mismo por aquí. ¿Quieres que la bloquee ahora? Responde sí o no.",
    transaction_id: null,
    proposta: null,
  });
  const feito = turno({
    intencao: "desconhecida",
    regra: "POL-BLQ-02",
    acao: "bloquear_cartao",
    estado: "livre",
    resposta: "Bloqueé tu tarjeta de crédito terminada en 1111.",
    transaction_id: null,
    proposta: null,
    bloqueio: "BL-00000002",
  });
  const { enviados } = servidor([{ status: 200, corpo: pergunta }, { status: 200, corpo: feito }]);
  montar();
  await abrirEPedir("¿cómo bloqueo la tarjeta si la pierdo?");
  const confirmar = await screen.findByRole("button", { name: "Sí, confirmo" });
  // A pergunta antes de bloquear é o passo 3 do design (a confirmação), como a do pré-caso.
  expect(screen.getByText("3 · Confirmation")).toHaveAttribute("aria-current", "step");
  await userEvent.click(confirmar);
  expect(await screen.findByText(/Bloqueé tu tarjeta/)).toBeInTheDocument();
  expect(enviados).toEqual(["¿cómo bloqueo la tarjeta si la pierdo?", "Sí, confirmo"]);
});

test("desbloqueio proposto pede o sim com os mesmos botões e, feito, avisa o console", async () => {
  const proposta = turno({
    intencao: "desbloquear",
    regra: "POL-BLQ-04",
    acao: "propor_desbloqueio",
    estado: "confirmando_desbloqueio",
    resposta: "¿Confirmas que quieres deshacer el bloqueo de tu tarjeta de crédito (referencia BL-00000001)? Responde sí o no.",
    transaction_id: null,
    proposta: null,
  });
  const desfeito = turno({
    intencao: "desconhecida",
    regra: "POL-BLQ-04",
    acao: "desbloquear_cartao",
    estado: "livre",
    resposta: "Listo: deshice el bloqueo de tu tarjeta de crédito (referencia BL-00000001).",
    transaction_id: null,
    proposta: null,
    bloqueio: "BL-00000001",
  });
  const { enviados } = servidor([{ status: 200, corpo: proposta }, { status: 200, corpo: desfeito }]);
  const aoMudar = montar();
  await abrirEPedir("quiero desbloquear mi tarjeta");
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByText(/deshice el bloqueo/)).toBeInTheDocument();
  expect(enviados).toEqual(["quiero desbloquear mi tarjeta", "Sí, confirmo"]);
  expect(aoMudar).toHaveBeenCalledTimes(1);
});

test("relato de fraude com vários cartões: o caso já está com o atendente enquanto a conversa pergunta o cartão", async () => {
  const perguntando = turno({
    intencao: "fraude",
    regra: "POL-HUM-01",
    acao: "humano",
    estado: "escolhendo_cartao",
    resposta: "Por seguridad, un agente va a atender este caso. Mientras tanto, puedo bloquear ahora la tarjeta afectada.",
    transaction_id: null,
    proposta: null,
    atendimento: "AT-00000002",
  });
  servidor([{ status: 200, corpo: perguntando }]);
  const aoIdioma = vi.fn();
  render(<Conversa token="tok" aoExpirar={vi.fn()} aoMudar={vi.fn()} aoIdioma={aoIdioma} />);
  await abrirEPedir("Me clonaron una tarjeta");
  expect(await screen.findByText("Handed to a person")).toBeInTheDocument();
  // A resposta (o cartão a bloquear) segue livre, mas sem atalhos nem "Perguntar sobre esta".
  expect(screen.getByLabelText(CAIXA)).toBeEnabled();
  expect(screen.queryByRole("group", { name: "Shortcuts" })).not.toBeInTheDocument();
  expect(aoIdioma).toHaveBeenLastCalledWith(null);
});

test("reabrir a conversa mostra o caso que está com o atendente", async () => {
  sessionStorage.setItem("jeje.conversa", "C1");
  const historico = {
    conversa_id: "C1",
    idioma: "es",
    // O caso já está com o atendente enquanto a conversa pergunta o cartão a bloquear: só o atendimento
    // relido diz que ele está com uma pessoa.
    estado: "escolhendo_cartao",
    atendimento: "AT-00000003",
    turnos: [
      { numero: 1, mensagem: "Me robaron la tarjeta", resposta: "Por seguridad, un agente va a atender este caso.", regra: "POL-HUM-01", acao: "humano", estado: "escolhendo_cartao", criado_em: "2026-10-01T10:00:00Z" },
    ],
  };
  servidor([], historico);
  montar();
  expect(await screen.findByText("Handed to a person")).toBeInTheDocument();
  expect(screen.queryByRole("group", { name: "Shortcuts" })).not.toBeInTheDocument();
});

test("a fala nova rola até ficar à vista, pelo mínimo (ACH-209)", async () => {
  const rolar = vi.fn();
  const original = Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView = rolar;
  try {
    servidor([{ status: 200, corpo: turno({}) }]);
    montar();
    await abrirEPedir();
    const resposta = (await screen.findByText(/Puedo registrar una solicitud/)).closest("li");
    expect(rolar.mock.contexts.at(-1)).toBe(resposta);
    expect(rolar).toHaveBeenLastCalledWith({ block: "nearest" });
  } finally {
    Element.prototype.scrollIntoView = original;
  }
});

test("por que esta resposta na língua da interface: em português, os rótulos do design e a probabilidade com vírgula", async () => {
  window.history.replaceState(null, "", "/?lang=pt");
  servidor([{ status: 200, corpo: pelo({ resolvedor: "ranking", calibracao: "764ce683d347", probabilidade: 0.987, possiveis: 2 }) }]);
  render(
    <LinguaDoAppProvider>
      <Conversa token="tok" aoExpirar={vi.fn()} aoMudar={vi.fn()} />
    </LinguaDoAppProvider>,
  );
  await userEvent.type(await screen.findByLabelText("Escreva como cliente, em espanhol ou português"), "No reconozco el cobro de Uber");
  await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
  const resposta = (await screen.findByText(/Puedo registrar una solicitud/)).closest("li");
  if (!resposta) throw new Error("resposta fora da lista");
  await userEvent.click(within(resposta).getByRole("button", { name: /Por que esta resposta/ }));
  const linhas = Object.fromEntries(Array.from(resposta.querySelectorAll("dt")).map((dt) => [dt.textContent, dt.nextElementSibling?.textContent]));
  expect(linhas).toMatchObject({
    transação: "ranking com garantia (α = 5%) · probabilidade 0,99 · 2 possíveis · calibração 764ce683d347",
    ação: "propor pré-caso",
    intenção: "contestar",
  });
});

test("a confirmação vai na língua da conversa: em português, o sim que vai é o 'Sim, confirmo'", async () => {
  const pt = turno({ idioma: "pt", resposta: "Posso registrar um pedido de revisão (pré-caso) da transação na Uber. Você confirma?" });
  const { enviados } = servidor([{ status: 200, corpo: pt }, { status: 200, corpo: REGISTRADO }]);
  montar();
  await abrirEPedir("Não reconheço a cobrança da Uber");
  await userEvent.click(await screen.findByRole("button", { name: "Sim, confirmo" }));
  await screen.findByText("PC-00000009 · pre-case received");
  expect(enviados).toEqual(["Não reconheço a cobrança da Uber", "Sim, confirmo"]);
});
