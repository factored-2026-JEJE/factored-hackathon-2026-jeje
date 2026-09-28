// Métricas contra um servidor mínimo na fronteira de rede: a tela mostra os números da API
// (recomputados dos eventos no backend), sem inventar valor quando ainda não há dado.
import { render, screen } from "@testing-library/react";
import type { Metricas } from "./api/cliente";
import { MetricasDoAtendimento } from "./MetricasDoAtendimento";

const METRICAS: Metricas = {
  turnos: 12,
  erros: 2,
  taxa_de_erro: 2 / 14,
  conversas: 4,
  conversas_encaminhadas: 1,
  taxa_de_encaminhamento: 0.25,
  pre_casos_registrados: 3,
  latencia_ms: { p50: 41.25, p95: 187.5, max: 240 },
  acoes: {},
  regras: {},
};

function servidor(corpo: Metricas) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(corpo), { status: 200 })));
}

afterEach(() => vi.unstubAllGlobals());

const valorDe = (nome: string) => screen.getByRole("rowheader", { name: nome }).nextElementSibling?.textContent;

test("mostra os números da API com taxas em porcentagem e latências em ms", async () => {
  servidor(METRICAS);
  render(<MetricasDoAtendimento versao={0} />);
  await screen.findByRole("table", { name: "Métricas" });
  expect(valorDe("Turnos")).toBe("12");
  expect(valorDe("Erros (turno desfeito)")).toBe("2 (14,3%)");
  expect(valorDe("Encaminhadas para humano")).toBe("1 (25%)");
  expect(valorDe("Pré-casos registrados")).toBe("3");
  expect(valorDe("Latência p50")).toBe("41,3 ms");
  expect(valorDe("Latência p95")).toBe("187,5 ms");
});

test("sem eventos não inventa taxa nem latência", async () => {
  servidor({
    ...METRICAS,
    turnos: 0, erros: 0, taxa_de_erro: null, conversas: 0, conversas_encaminhadas: 0,
    taxa_de_encaminhamento: null, pre_casos_registrados: 0, latencia_ms: { p50: null, p95: null, max: null },
  });
  render(<MetricasDoAtendimento versao={0} />);
  await screen.findByRole("table", { name: "Métricas" });
  expect(valorDe("Encaminhadas para humano")).toBe("0 (—)");
  expect(valorDe("Latência p95")).toBe("—");
});
