// O mapa do site (DEV-032a): o caminho de uma mensagem passa por cada componente na ordem, com a
// posição de cada um tirada das coordenadas dos componentes (oráculo independente da conta do caminho).
import { CONTEUDO } from "./conteudo";
import { CONTEUDO_DO_MAIN, MAPA_DO_MAIN } from "./fatos";
import { DADOS, MAPA_DO_DESIGN, MENSAGEM, NOS, QUADROS, caminho, construirLigacoes, nosDaRota, pontoNoCaminho, quadro } from "./mapa";

const ligacoes = construirLigacoes(MAPA_DO_DESIGN);
const msg = caminho(ligacoes, MENSAGEM);
const dados = caminho(ligacoes, DADOS);

describe("caminho de uma mensagem", () => {
  it("vai do navegador (0) ao banco (1), passando por cada componente em ordem crescente", () => {
    const posicoes = MENSAGEM.map((id) => msg.par[id]);
    expect(posicoes[0]).toBe(0);
    expect(posicoes.at(-1)).toBeCloseTo(1, 12);
    for (let i = 1; i < posicoes.length; i++) expect(posicoes[i]).toBeGreaterThan(posicoes[i - 1] ?? 0);
  });

  it("na posição de cada componente, o ponto do caminho está sobre ele (a 0,3 do chão)", () => {
    for (const id of [...MENSAGEM, ...DADOS]) {
      const R = MENSAGEM.includes(id) ? msg : dados;
      const { p } = pontoNoCaminho(R, R.par[id] ?? -1);
      expect(p[0]).toBeCloseTo(NOS[id].x, 9);
      expect(p[1]).toBeCloseTo(0.3, 9);
      expect(p[2]).toBeCloseTo(NOS[id].y, 9);
    }
  });

  it("fora de 0 a 1, fica nas pontas", () => {
    expect(pontoNoCaminho(msg, -2).p).toEqual(pontoNoCaminho(msg, 0).p);
    expect(pontoNoCaminho(msg, 7).p).toEqual(pontoNoCaminho(msg, 1).p);
  });

  it("o caminho principal arqueia (até 0,52 no meio de cada ligação), a cascata fica rente (0,3)", () => {
    const alturas = (a: string, b: string) => ligacoes.find((l) => l.a === a && l.b === b)?.pts.map((p) => p[1]) ?? [];
    expect(Math.max(...alturas("caddy", "portao"))).toBeCloseTo(0.52, 9);
    expect(new Set(alturas("regras", "leitor"))).toEqual(new Set([0.3]));
  });
});

describe("quadros da câmera", () => {
  it("há um quadro por bloco da rolagem: o topo, o problema, a introdução, 8 paradas, 5 dos dados e o mapa", () => {
    expect(QUADROS).toHaveLength(1 + 1 + 1 + 8 + 5 + 1);
  });

  it("no celular, o primeiro quadro fica 1,5 vez mais longe e centrado; no computador, deslocado", () => {
    const celular = quadro(0, 390, 844, msg, dados);
    const computador = quadro(0, 1440, 900, msg, dados);
    expect(celular.r).toBeCloseTo(27 * 1.5, 12);
    expect(celular.ox).toBe(0);
    expect(computador.r).toBe(27);
    expect(computador.oy).toBe(-0.26);
  });

  it("o mapa inteiro (último quadro) olha de cima, de frente no computador e girado na tela em pé", () => {
    expect(quadro(16, 1440, 900, msg, dados).th).toBe(0);
    expect(quadro(16, 390, 844, msg, dados).th).toBe(90);
    expect(quadro(16, 1440, 900, msg, dados).ph).toBe(58);
  });

  it("cada parada da viagem foca o seu componente", () => {
    expect(quadro(3, 1440, 900, msg, dados).node).toBe("portao");
    expect(quadro(5, 1440, 900, msg, dados).node).toBe("regras");
    expect(quadro(10, 1440, 900, msg, dados).tg).toEqual([NOS.banco.x, 0.35, NOS.banco.y]);
  });
  it("o mapa inteiro fica no meio do retângulo livre (design de 03/10), e em pé quando ele é estreito", () => {
    // Livre à direita do cartão do mapa: o centro do mapa desloca para a direita (ox negativo).
    const livre = { l: 440, t: 70, r: 1416, b: 884 };
    const deitado = quadro(16, 1440, 900, msg, dados, NOS, { livre });
    expect(deitado.ox).toBeCloseTo((720 - (440 + (1416 - 440) / 2)) / 1440, 12);
    expect(deitado.oy).toBeCloseTo((450 - (70 + (884 - 70) / 2)) / 900, 12);
    expect(deitado.th).toBe(0);
    // Um retângulo livre estreito e alto vira o mapa em pé, mesmo na tela deitada.
    expect(quadro(16, 1440, 900, msg, dados, NOS, { livre: { l: 1000, t: 70, r: 1416, b: 884 } }).th).toBe(90);
  });

  it("no computador, cada parada foca entre o conteúdo do bloco e a borda direita livre", () => {
    const bordaDoBloco = [0, 0, 0, 600];
    const q = quadro(3, 1440, 900, msg, dados, NOS, { bordaDoBloco, direita: 1000 });
    expect(q.ox).toBeCloseTo((720 - (624 + 1000) / 2) / 1440, 12);
    // No celular, a parada fica centrada, sem as medidas.
    expect(quadro(3, 390, 844, msg, dados, NOS, { bordaDoBloco, direita: 300 }).ox).toBe(0);
  });
});

describe("rotas das jornadas do design", () => {
  it("perguntar não acende a Ação; agir sem transação não acende o Qual; o desbloqueio só pede o sim", () => {
    expect(nosDaRota("ask", "ambiguo")).not.toContain("acoes");
    expect(nosDaRota("act", "fraude")).not.toContain("qual");
    expect(nosDaRota("act", "desbloq")).toEqual(nosDaRota("noact", "x"));
    expect(nosDaRota("reader", "ajuda")).toContain("leitor");
  });
});

describe("o mapa do main (fatos.ts)", () => {
  it("as ligações até o LLM deixam de ser planejadas e viram a cascata dele", () => {
    expect(MAPA_DO_MAIN.ligacoes.filter(([, , , tipo]) => tipo === "p")).toEqual([]);
    expect(MAPA_DO_MAIN.ligacoes.filter(([, , , tipo]) => tipo === "l").map(([a, b]) => a + "→" + b)).toEqual(["leitor→llm", "llm→etapas"]);
  });

  it("o componente do LLM fica onde o design o pôs, com a mesma forma, sem a marca de planejado", () => {
    const { plan, ...doDesign } = MAPA_DO_DESIGN.nos.llm;
    expect(plan).toBe(1);
    expect(MAPA_DO_MAIN.nos.llm).toEqual(doDesign);
  });
});

describe("os fatos do main no texto do site (fatos.ts)", () => {
  it("a entrada diz o cabeçalho que o Caddy manda de verdade: só a própria origem embute o app", () => {
    const entrada = (c: typeof CONTEUDO) => c.stops.find((x) => x.id === "entrada")?.protects?.[0];
    expect(entrada(CONTEUDO)?.pt).toContain("X-Frame-Options DENY");
    for (const idioma of ["pt", "es", "en"] as const) {
      expect(entrada(CONTEUDO_DO_MAIN)?.[idioma]).toContain("X-Frame-Options SAMEORIGIN");
      expect(entrada(CONTEUDO_DO_MAIN)?.[idioma]).not.toContain("DENY");
    }
  });
});
