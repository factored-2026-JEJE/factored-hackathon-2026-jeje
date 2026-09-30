// Conversa contra um servidor mínimo na fronteira de rede: a regra é decidida pela API real
// (testada no backend e no E2E). Aqui: a tela só mostra o que a API respondeu, envia o texto
// certo, não envia duas vezes, reenvia a mesma mensagem e reabre a conversa sem repetir nada.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ResultadoDoTurno } from "./api/cliente";
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
      const r = (status: number, corpo: unknown) => new Response(JSON.stringify(corpo), { status });
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
});

function montar(aoMudar = vi.fn()) {
  render(<Conversa token="tok" aoExpirar={vi.fn()} aoMudar={aoMudar} />);
  return aoMudar;
}

async function abrirEPedir(pedido = "No reconozco el cobro de Uber") {
  await userEvent.click(await screen.findByRole("button", { name: "Conversar em español" }));
  expect(await screen.findByText("Hola. ¿En qué te ayudo?")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Mensagem"), pedido);
  await userEvent.click(screen.getByRole("button", { name: "Enviar" }));
}

test("protocolo só aparece depois que a API registra, e a fila é avisada", async () => {
  const { enviados, liberar } = servidor([{ status: 200, corpo: turno({}) }, "pendente"]);
  const aoMudar = montar();
  await abrirEPedir();
  const confirmar = await screen.findByRole("button", { name: "Sí, confirmo" });
  await userEvent.click(confirmar);
  expect(await screen.findByText("Enviando…")).toBeInTheDocument();
  expect(screen.queryByText(/Pré-caso recebido/)).not.toBeInTheDocument();
  expect(aoMudar).not.toHaveBeenCalled();
  liberar();
  expect(await screen.findByText("Pré-caso recebido: protocolo PC-00000009")).toBeInTheDocument();
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo"]);
  expect(aoMudar).toHaveBeenCalledTimes(1);
});

test("pré-caso já existente não vira 'recebido' de novo", async () => {
  const existente = turno({ regra: "POL-DISP-03", acao: "responder", estado: "livre", proposta: null, protocolo: "PC-00000003" });
  servidor([{ status: 200, corpo: existente }]);
  montar();
  await abrirEPedir();
  expect(await screen.findByText(existente.resposta)).toBeInTheDocument();
  expect(screen.queryByText(/Pré-caso recebido/)).not.toBeInTheDocument();
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
  await userEvent.click(await screen.findByRole("button", { name: "2. en Streaming Plus de USD 45,90 (10/03/2025)" }));
  await screen.findByRole("button", { name: "Sí, confirmo" });
  expect(enviados).toEqual(["No reconozco un cobro de 45,90", "2"]);
});

test("não envia duas vezes enquanto espera a resposta", async () => {
  const { enviados, liberar } = servidor([{ status: 200, corpo: turno({}) }, "pendente"]);
  montar();
  await abrirEPedir();
  const confirmar = await screen.findByRole("button", { name: "Sí, confirmo" });
  await userEvent.click(confirmar);
  await userEvent.click(confirmar);
  liberar();
  await screen.findByText("Pré-caso recebido: protocolo PC-00000009");
  expect(enviados.filter((t) => t === "Sí, confirmo")).toHaveLength(1);
});

test("503 diz que nada foi criado e reenviar manda a mesma mensagem", async () => {
  const naoRegistrado = { status: 503, corpo: { detail: "Turno não registrado; nada foi criado. Tente de novo." } };
  const { enviados } = servidor([{ status: 200, corpo: turno({}) }, naoRegistrado, { status: 200, corpo: REGISTRADO }]);
  montar();
  await abrirEPedir();
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("nada foi criado");
  expect(screen.queryByText(/Pré-caso recebido/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Reenviar" }));
  expect(await screen.findByText("Pré-caso recebido: protocolo PC-00000009")).toBeInTheDocument();
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo", "Sí, confirmo"]);
});

test("resposta perdida depois do sim: a tela relê a conversa, mostra o protocolo e não reenvia", async () => {
  const { enviados } = servidor([{ status: 200, corpo: turno({}) }, "perdida"]);
  const aoMudar = montar();
  await abrirEPedir();
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByText("Registré la solicitud con el protocolo PC-00000009.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Reenviar" })).not.toBeInTheDocument();
  expect(aoMudar).toHaveBeenCalledTimes(1);
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo"]);
});

test("mensagem que não chegou ao servidor continua com Reenviar, e o reenvio registra", async () => {
  const { enviados } = servidor([{ status: 200, corpo: turno({}) }, "rede", { status: 200, corpo: REGISTRADO }]);
  montar();
  await abrirEPedir();
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Sem resposta do servidor");
  await userEvent.click(screen.getByRole("button", { name: "Reenviar" }));
  expect(await screen.findByText("Pré-caso recebido: protocolo PC-00000009")).toBeInTheDocument();
  expect(enviados).toEqual(["No reconozco el cobro de Uber", "Sí, confirmo", "Sí, confirmo"]);
});

test("reenviar relê a conversa antes: se o servidor já processou, não manda de novo", async () => {
  const { enviados } = servidor([{ status: 200, corpo: turno({}) }, "perdida"], undefined, 1);
  const aoMudar = montar();
  await abrirEPedir();
  await userEvent.click(await screen.findByRole("button", { name: "Sí, confirmo" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Sem resposta do servidor");
  await userEvent.click(screen.getByRole("button", { name: "Reenviar" }));
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
  expect(await screen.findByText("Com atendimento humano (AT-00000001).")).toBeInTheDocument();
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
  expect(await screen.findByText("Conversa encerrada: os dados foram atualizados. Abra uma nova conversa.")).toBeInTheDocument();
  expect(screen.getByLabelText("Mensagem")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Nova conversa" })).toBeEnabled();
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

test("por que esta resposta: regra e o que ela quer dizer, efeito, fontes e quem leu", async () => {
  const proposta = turno({
    descricao: "Contestação dentro dos limites simulados.",
    interpretacao: "leitor:e5@429a8eaca51b",
    efeito: "P1",
    fontes: ["curated.transactions", "app.propostas_pre_caso"],
  });
  servidor([{ status: 200, corpo: proposta }]);
  montar();
  await abrirEPedir();
  const resposta = (await screen.findByText(/Puedo registrar una solicitud/)).closest("li");
  if (!resposta) throw new Error("resposta fora da lista");
  await userEvent.click(within(resposta).getByText("Por que esta resposta?"));
  const motivo = within(resposta);
  expect(motivo.getByText("POL-DISP-01: Contestação dentro dos limites simulados.")).toBeVisible();
  expect(motivo.getByText("propor_pre_caso")).toBeVisible();
  expect(motivo.getByText("P1")).toBeVisible();
  expect(motivo.getByText("curated.transactions, app.propostas_pre_caso")).toBeVisible();
  expect(motivo.getByText("leitor:e5@429a8eaca51b")).toBeVisible();
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
  const resposta = (await screen.findByText(/Puedo registrar una solicitud/)).closest("li");
  if (!resposta) throw new Error("resposta fora da lista");
  await userEvent.click(within(resposta).getByText("Por que esta resposta?"));
  expect(within(resposta).getByText("POL-DISP-01")).toBeVisible();
  expect(within(resposta).getByText("propor_pre_caso")).toBeVisible();
  expect(within(resposta).queryByText("Efeito")).not.toBeInTheDocument();
});
