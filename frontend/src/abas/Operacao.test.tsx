// A aba da operação (DEV-032b, 2.10) contra um servidor mínimo na fronteira de rede: a prontidão,
// as métricas recalculadas dos eventos, as regras usadas, os últimos turnos, a qualidade dos dados
// com a conferência do invariante e a EDA, como no design, com os números da API. A EDA é lida uma
// vez e não segura o resto; a qualidade e a EDA fora da API não viram alarme.
import { render, screen, waitFor, within } from "@testing-library/react";
import type { EventoRecente, IndicadorEda, Metricas, Prontidao, QualidadeTabela } from "../api/cliente";
import { AreaDaOperacao } from "./Operacao";

const DATASET: NonNullable<Prontidao["dataset"]> = {
  version: "0123456789abcdefwxyz",
  source: "s3",
  loaded_at: "2026-10-03T08:00:12Z",
  recusada: null,
};

const PRONTA: Prontidao = { status: "ready", database: "ok", dataset: DATASET };

const METRICAS: Metricas = {
  turnos: 3,
  erros: 0,
  taxa_de_erro: 0,
  conversas: 1,
  conversas_encaminhadas: 1,
  taxa_de_encaminhamento: 1,
  pre_casos_registrados: 1,
  latencia_ms: { p50: 25.4, p95: 38.6, max: 40 },
  acoes: { registrar_pre_caso: 1 },
  regras: { "POL-HUM-03": 1, "POL-DISP-01": 2 },
  modelo: { chamadas: 2, fallbacks: 0, tokens_entrada: 0, tokens_saida: 0, chamadas_sem_contagem_de_tokens: 0 },
};

const EVENTOS: EventoRecente[] = [
  { criado_em: "2026-10-03T14:01:01Z", requisicao: "36c1f968-e657-4f0e-9d3a", regra: "POL-DISP-01", acao: "registrar_pre_caso", efeito: "PC-00000417" },
  { criado_em: "2026-10-03T14:00:58Z", requisicao: null, regra: "POL-NOVA", acao: "acao_nova", efeito: null },
  { criado_em: "2026-10-03T14:00:40Z", requisicao: "5d0c", regra: "POL-BLQ-04", acao: "desbloquear_cartao", efeito: "BL-00000007" },
  { criado_em: "2026-10-03T14:00:30Z", requisicao: "4c1b", regra: "POL-BLQ-01", acao: "bloquear_cartao", efeito: "BL-00000007" },
  { criado_em: "2026-10-03T14:00:20Z", requisicao: "3b0a", regra: "POL-BLQ-02", acao: "bloquear_cartao", efeito: "BL-00000006" },
];

const QUALIDADE: QualidadeTabela[] = [
  { tabela: "transacoes", raw: 4120, curado: 4080, quarentena: 30, copias_descartadas: 10, motivos: {}, anulacoes: { a: 1, b: 2 }, normalizacoes: {} },
];

const EDA: IndicadorEda[] = [
  {
    id: "transacional",
    pergunta: "Qual o peso do motivo transacional?",
    tipo: "distribuicao",
    consulta: "SELECT motivo, count(*) FROM curated.contacts GROUP BY 1",
    unidade_soma: null,
    linhas: [{ grupo: "Transaccional", contagem: 1200, base: 3000, proporcao: 0.4, soma: null, proporcao_soma: null }],
  },
  {
    id: "resolucao",
    pergunta: "Quanto se resolve por motivo?",
    tipo: "taxa",
    consulta: "SELECT motivo, avg(resolvido) FROM curated.contacts GROUP BY 1",
    unidade_soma: "USD",
    linhas: [{ grupo: "Transaccional", contagem: 915, base: 1000, proporcao: 0.915, soma: 10, proporcao_soma: 0.24 }],
  },
];

interface Respostas {
  prontidao?: unknown;
  metricas?: unknown;
  eventos?: unknown;
  qualidade?: unknown;
  eda?: unknown;
}

/** Servidor na fronteira de rede; `null` numa resposta vira erro 500 daquela rota. */
function servidor(r: Respostas) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const corpo = url.startsWith("/api/health/ready")
        ? r.prontidao
        : url.startsWith("/api/metricas/eventos")
          ? r.eventos
          : url.startsWith("/api/metricas")
            ? r.metricas
            : url.startsWith("/api/dados/qualidade")
              ? r.qualidade
              : url.startsWith("/api/dados/eda")
                ? r.eda
                : undefined;
      if (corpo === null || corpo === undefined) return new Response("{}", { status: 500 });
      return new Response(JSON.stringify(corpo), { status: 200 });
    }),
  );
}

const area = { versao: 0, aoMudar: () => {}, experimentar: () => {} };

afterEach(() => vi.unstubAllGlobals());

test("a prontidão, as métricas e as regras usadas, do mais usado para o menos", async () => {
  servidor({ prontidao: PRONTA, metricas: METRICAS, eventos: EVENTOS, qualidade: QUALIDADE, eda: EDA });
  render(<AreaDaOperacao {...area} />);
  const prontidao = within(await screen.findByRole("group", { name: "Readiness" }));
  expect(await prontidao.findByText("ready")).toBeInTheDocument();
  expect(prontidao.getByText("s3 · 0123…wxyz")).toBeInTheDocument();
  expect(prontidao.getByText(/^\d\d:\d\d:\d\d$/)).toBeInTheDocument();
  expect(prontidao.getByText("none")).toBeInTheDocument();
  const metricas = within(screen.getByRole("region", { name: "Metrics · recomputed from events" }));
  const esperadas: [string, string][] = [["3", "turns"], ["0", "errors"], ["25/39", "latency p50 / p95 · ms"], ["2", "model calls"]];
  for (const [valor, rotulo] of esperadas) {
    expect(metricas.getByText(rotulo).previousSibling).toHaveTextContent(valor);
  }
  expect(screen.queryByText(/Fresh instance/)).not.toBeInTheDocument();
  const regras = within(screen.getByRole("region", { name: "Rules used" }));
  const linhas = regras.getAllByText(/^POL-/).map((r) => r.textContent);
  expect(linhas).toEqual(["POL-DISP-01", "POL-HUM-03"]);
  const barra = regras.getByText("POL-HUM-03").nextSibling?.firstChild as HTMLElement;
  expect(barra.style.width).toBe("50%");
});

test("os últimos turnos com a ação e o efeito nos rótulos do design, sem o cliente", async () => {
  servidor({ prontidao: PRONTA, metricas: METRICAS, eventos: EVENTOS, qualidade: QUALIDADE, eda: EDA });
  render(<AreaDaOperacao {...area} />);
  const eventos = within(await screen.findByRole("region", { name: "Last events" }));
  const primeiro = await eventos.findByText(/request_id=36c1f968-e657 ·/);
  expect(primeiro).toHaveTextContent("POL-DISP-01 · record pre-case · written · re-read from the database PC-00000417");
  expect(eventos.getByText(/request_id=— ·/)).toHaveTextContent("POL-NOVA · acao_nova · none · read only");
  expect(eventos.getByText(/request_id=5d0c ·/)).toHaveTextContent(
    "POL-BLQ-04 · unblock (simulated) · card active · re-read BL-00000007",
  );
  expect(eventos.getByText(/request_id=4c1b ·/)).toHaveTextContent(
    "POL-BLQ-01 · preventive block (simulated) · card blocked · re-read BL-00000007",
  );
  expect(eventos.getByText(/request_id=3b0a ·/)).toHaveTextContent(
    "POL-BLQ-02 · full block (simulated) · card blocked · re-read BL-00000006",
  );
});

test("a instância nova avisa que os contadores começam em zero", async () => {
  servidor({ prontidao: PRONTA, metricas: { ...METRICAS, turnos: 0, regras: {} }, eventos: [], qualidade: QUALIDADE, eda: EDA });
  render(<AreaDaOperacao {...area} />);
  expect(await screen.findByText(/Fresh instance: every counter starts at zero/)).toBeInTheDocument();
  expect(screen.getByText("No turns yet.")).toBeInTheDocument();
  expect(screen.getByText("$ tail -f eventos · —")).toBeInTheDocument();
});

test("a qualidade dos dados com o título pela origem e a conferência do invariante", async () => {
  servidor({ prontidao: PRONTA, metricas: METRICAS, eventos: EVENTOS, qualidade: QUALIDADE, eda: EDA });
  const { unmount } = render(<AreaDaOperacao {...area} />);
  const tabela = within(await screen.findByRole("table", { name: "Data quality · challenge dataset" }));
  const linha = within(tabela.getByRole("row", { name: /^transacoes/ }));
  expect(linha.getAllByRole("cell").map((c) => c.textContent)).toEqual(["4,120", "4,080", "30", "10", "3"]);
  expect(tabela.getAllByRole("columnheader")).toHaveLength(6);
  expect(screen.getByText("✓ raw = curated + quarantine + copies")).toBeInTheDocument();
  unmount();
  const fixture = { ...PRONTA, dataset: { ...DATASET, source: "fixture" } };
  servidor({ prontidao: fixture, metricas: METRICAS, eventos: EVENTOS, qualidade: [{ ...QUALIDADE[0], curado: 4000 }], eda: EDA });
  render(<AreaDaOperacao {...area} />);
  expect(await screen.findByRole("table", { name: "Data quality · synthetic fixture" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("raw ≠ curated + quarantine + copies in: transacoes");
});

test("a EDA com a pergunta, as linhas e a consulta de cada número", async () => {
  servidor({ prontidao: PRONTA, metricas: METRICAS, eventos: EVENTOS, qualidade: QUALIDADE, eda: EDA });
  render(<AreaDaOperacao {...area} />);
  expect(screen.getByText("Computing the indicators…")).toBeInTheDocument();
  const distribuicao = within(await screen.findByRole("article", { name: "Qual o peso do motivo transacional?" }));
  expect(distribuicao.getAllByRole("columnheader").map((c) => c.textContent)).toEqual(["group", "records", "share"]);
  expect(distribuicao.getAllByRole("cell").map((c) => c.textContent)).toEqual(["1,200", "40.0%"]);
  expect(distribuicao.getByText("SELECT motivo, count(*) FROM curated.contacts GROUP BY 1")).toBeInTheDocument();
  const taxa = within(screen.getByRole("article", { name: "Quanto se resolve por motivo?" }));
  expect(taxa.getAllByRole("columnheader").map((c) => c.textContent)).toEqual(["group", "solved", "rate", "share of USD"]);
  const linha = within(taxa.getByRole("row", { name: /^Transaccional/ }));
  expect(linha.getAllByRole("cell").map((c) => c.textContent)).toEqual(["915 of 1,000", "91.5%", "24.0%"]);
  expect(screen.getByText(/They describe the data, not the effect of the system/)).toBeInTheDocument();
});

test("a EDA é lida uma vez: os efeitos da conversa releem só o resto", async () => {
  servidor({ prontidao: PRONTA, metricas: METRICAS, eventos: EVENTOS, qualidade: QUALIDADE, eda: EDA });
  const chamadas = vi.mocked(fetch);
  const { rerender } = render(<AreaDaOperacao {...area} />);
  await screen.findByRole("article", { name: "Qual o peso do motivo transacional?" });
  rerender(<AreaDaOperacao {...area} versao={1} />);
  await waitFor(() => expect(chamadas.mock.calls.filter(([u]) => u === "/api/metricas")).toHaveLength(2));
  expect(chamadas.mock.calls.filter(([u]) => String(u).startsWith("/api/dados/eda"))).toHaveLength(1);
});

test("a versão recusada com o motivo, a base sem carga e a sem dados", async () => {
  const recusada = { version: "fedcba9876543210abcd", motivo: "manifesto sem a tabela customers", em: "2026-10-03T09:00:00Z" };
  servidor({
    prontidao: { ...PRONTA, dataset: { ...DATASET, recusada } },
    metricas: METRICAS,
    eventos: EVENTOS,
    qualidade: [],
    eda: EDA,
  });
  const primeiro = render(<AreaDaOperacao {...area} />);
  const alerta = await screen.findByRole("alert");
  expect(alerta).toHaveTextContent(/^rejected version fedc…abcd · \d\d:\d\d:\d\d: manifesto sem a tabela customers\. still serving 0123…wxyz\.$/);
  expect(within(screen.getByRole("group", { name: "Readiness" })).getByText("fedc…abcd")).toBeInTheDocument();
  expect(screen.getByText("No load recorded yet.")).toBeInTheDocument();
  expect(screen.queryByText(/raw = curated/)).not.toBeInTheDocument();
  primeiro.unmount();
  servidor({ prontidao: { ...PRONTA, status: "unavailable", dataset: null }, metricas: METRICAS, eventos: [], qualidade: [], eda: [] });
  render(<AreaDaOperacao {...area} />);
  expect(await screen.findByText("no data loaded")).toBeInTheDocument();
});

test("uma parte fora não derruba as outras; tudo fora avisa", async () => {
  servidor({ prontidao: PRONTA, metricas: null, eventos: null, qualidade: null, eda: null });
  const primeiro = render(<AreaDaOperacao {...area} />);
  expect(await screen.findByText("ready")).toBeInTheDocument();
  // A qualidade e a EDA fora dizem que estão indisponíveis, sem alarme e sem a conferência vazia.
  const qualidade = within(screen.getByRole("region", { name: "Data quality · challenge dataset" }));
  expect(qualidade.getByText("Unavailable.")).toBeInTheDocument();
  expect(qualidade.queryByText(/raw = curated/)).not.toBeInTheDocument();
  const eda = within(screen.getByRole("region", { name: "Why this flow · from the data" }));
  expect(await eda.findByText("Unavailable.")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  primeiro.unmount();
  servidor({ prontidao: { ...PRONTA, database: "unreachable", dataset: null }, metricas: METRICAS });
  const segundo = render(<AreaDaOperacao {...area} />);
  expect(await screen.findByText("unreachable")).toBeInTheDocument();
  segundo.unmount();
  servidor({});
  render(<AreaDaOperacao {...area} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable.");
});
