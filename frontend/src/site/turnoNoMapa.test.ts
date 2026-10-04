// O turno de verdade no mapa (DEV-032a): o caminho que acende tem de ser o mesmo das rotas que o
// designer escreveu para cada tipo de turno (as jornadas de exemplo), que servem de oráculo.
import type { ResultadoDoTurno } from "../api/cliente";
import { nosDaRota } from "./mapa";
import { caminhoDoTurno, caminhoRecebido, leituraDe } from "./turnoNoMapa";

type Turno = Parameters<typeof caminhoDoTurno>[0];
const turno = (t: Partial<Turno>): Turno => ({
  acao: "responder",
  interpretacao: "regras",
  transaction_id: null,
  resolucao: null,
  opcoes: [],
  atendimento: null,
  estado: "aguardando_pedido",
  ...t,
});
const opcao = (numero: number): ResultadoDoTurno["opcoes"][number] => ({ numero, transaction_id: `TX-${numero}`, descricao: `compra ${numero}` });

describe("quem leu a mensagem", () => {
  it("o campo interpretacao: as regras, o leitor (decidindo ou abaixo do limite) e o LLM", () => {
    expect(leituraDe("regras")).toBe("regras");
    expect(leituraDe("leitor:e5@0123456789ab")).toBe("leitor");
    expect(leituraDe("regras (leitor abaixo do limite)")).toBe("leitor");
    expect(leituraDe("ollama:qwen3:4b")).toBe("llm");
  });
});

describe("o caminho do turno é o da rota do design", () => {
  it("proposta de pré-caso com a transação achada: o caminho inteiro (full)", () => {
    const c = caminhoDoTurno(turno({ acao: "propor_pre_caso", transaction_id: "TX-1", resolucao: { resolvedor: "filtro", calibracao: null, probabilidade: null, possiveis: null } }));
    expect(c.nos).toEqual(nosDaRota("full", "contestar"));
    expect(c.humano).toBe(false);
  });

  it("várias transações possíveis: pergunta qual, sem a Ação (ask)", () => {
    const c = caminhoDoTurno(turno({ acao: "esclarecer", opcoes: [opcao(1), opcao(2)] }));
    expect(c.nos).toEqual(nosDaRota("ask", "ambiguo"));
  });

  it("fraude: atendente e bloqueio sem transação (act), passando para uma pessoa", () => {
    const c = caminhoDoTurno(turno({ acao: "humano", atendimento: "AT-1", estado: "com_humano" }));
    expect(c.nos).toEqual(nosDaRota("act", "fraude"));
    expect(c.humano).toBe(true);
  });

  it("fora do escopo, só oferecendo o atendente: nem Qual nem Ação (noact)", () => {
    expect(caminhoDoTurno(turno({ acao: "oferecer_humano", estado: "oferecendo_humano" })).nos).toEqual(nosDaRota("noact", "escopo"));
  });

  it("pedir o sim do desbloqueio não age (como a jornada desbloq do design)", () => {
    expect(caminhoDoTurno(turno({ acao: "propor_desbloqueio" })).nos).toEqual(nosDaRota("act", "desbloq"));
  });

  it("não entendido com o leitor abaixo do limite: acende o leitor (reader)", () => {
    const c = caminhoDoTurno(turno({ acao: "esclarecer", interpretacao: "regras (leitor abaixo do limite)" }));
    expect(new Set(c.nos)).toEqual(new Set(nosDaRota("reader", "ajuda")));
    expect(c.leitura).toBe("leitor");
  });

  it("lido pelo LLM: acende o leitor e o LLM, que o design não tinha no produto", () => {
    const c = caminhoDoTurno(turno({ acao: "responder", interpretacao: "ollama:qwen3:4b", transaction_id: "TX-9" }));
    expect(c.nos).toContain("leitor");
    expect(c.nos).toContain("llm");
    expect(c.leitura).toBe("llm");
  });
});

describe("o caminho que chega do app aberto na janela (jeje-turn)", () => {
  it("a lista dos nós de verdade vale como veio; um tipo de rota do design vale como a jornada", () => {
    expect(caminhoRecebido(["navegador", "regras", "leitor"], true, "leitor")).toEqual({
      nos: ["navegador", "regras", "leitor"],
      humano: true,
      leitura: "leitor",
    });
    expect(caminhoRecebido("ask", false, undefined)?.nos).toEqual(nosDaRota("ask", ""));
  });

  it("nó que não existe, rota desconhecida ou lista vazia não acendem nada", () => {
    expect(caminhoRecebido(["navegador", "invasor"], false, "regras")).toBeNull();
    expect(caminhoRecebido([], false, "regras")).toBeNull();
    expect(caminhoRecebido("tudo", false, "regras")).toBeNull();
    expect(caminhoRecebido(undefined, false, "regras")).toBeNull();
    // Uma leitura desconhecida vira "regras" (não acende o leitor nem o LLM).
    expect(caminhoRecebido(["navegador"], false, "outra")?.leitura).toBe("regras");
  });
});
