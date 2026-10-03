// Os números ao vivo (DEV-032a): tirados das linhas certas da EDA e da carga, e trocados no texto só
// onde o design tem o número. Com a API dando o mesmo que as evidências, a tela não muda.
import type { IndicadorEda, QualidadeTabela } from "../api/cliente";
import { CONTEUDO_DO_MAIN } from "./fatos";
import { SEM_NUMEROS, VALORES_DO_DESIGN, comNumerosAoVivo, daEda, daQualidade, porcento } from "./aoVivo";
import { resolver } from "./conteudo";

const linha = (grupo: string, contagem: number, base: number, soma: number | null = null): IndicadorEda["linhas"][number] => ({
  grupo,
  contagem,
  base,
  proporcao: contagem / base,
  soma,
  proporcao_soma: soma,
});
const indicador = (id: string, linhas: IndicadorEda["linhas"]): IndicadorEda => ({
  id,
  pergunta: "",
  tipo: "distribuicao",
  consulta: "SELECT 1",
  unidade_soma: null,
  linhas,
});

// Uma EDA pequena, com a ordem das linhas trocada: a escolha é pelo grupo, não pela posição.
const EDA: IndicadorEda[] = [
  indicador("motivos-de-contato", [linha("Producto", 300, 1000, 0.3), linha("Transaccional", 412, 1000, 0.25)]),
  indicador("resolucao-por-motivo", [linha("Queja", 1, 10), linha("Transaccional", 9, 10)]),
  indicador("reclamacoes-de-transacao", [linha("(vazio)", 1, 4), linha("Cargo no reconocido", 3, 4)]),
];

describe("da EDA", () => {
  it("pega a linha do motivo transacional, o primeiro contato e o cargo não reconhecido", () => {
    const n = daEda(EDA);
    expect(n.contatos).toEqual({ proporcao: 0.412, base: 1000, tempo: 0.25 });
    expect(n.primeiroContato).toBe(0.9);
    expect(n.cargoNaoReconhecido).toBe(0.75);
  });

  it("sem o indicador, fica sem número (e o site mostra o do design)", () => {
    expect(daEda([])).toEqual({ contatos: null, primeiroContato: null, cargoNaoReconhecido: null });
  });
});

describe("da carga", () => {
  const tabela = (t: string, curado: number): QualidadeTabela => ({ tabela: t, raw: curado, curado, quarentena: 0, copias_descartadas: 0, motivos: {}, anulacoes: {}, normalizacoes: {} });
  it("conta o curado de transações, clientes e reclamações", () => {
    expect(daQualidade([tabela("customers", 3), tabela("transactions", 5), tabela("complaints", 7)])).toEqual({ transacoes: 5, clientes: 3, reclamacoes: 7 });
  });
  it("faltando uma tabela, nada", () => {
    expect(daQualidade([tabela("customers", 3)])).toBeNull();
  });
});

describe("no texto do site", () => {
  it("com os valores das evidências, o conteúdo fica igual ao do design, nos três idiomas", () => {
    const iguais = { ...VALORES_DO_DESIGN, contatos: { ...VALORES_DO_DESIGN.contatos }, carga: { ...VALORES_DO_DESIGN.carga }, tfidf: { ...VALORES_DO_DESIGN.tfidf } };
    for (const idioma of ["pt", "es", "en"] as const) {
      const t = resolver(CONTEUDO_DO_MAIN, idioma);
      expect(comNumerosAoVivo(t, iguais, idioma)).toEqual(t);
      expect(comNumerosAoVivo(t, SEM_NUMEROS, idioma)).toEqual(t);
    }
  });

  it("com outros valores, troca o número e a base no lugar certo, no formato de cada idioma", () => {
    const n = { ...SEM_NUMEROS, contatos: { proporcao: 0.4123, base: 700000, tempo: 0.2 }, carga: { transacoes: 12, clientes: 3, reclamacoes: 4 } };
    const pt = comNumerosAoVivo(resolver(CONTEUDO_DO_MAIN, "pt"), n, "pt");
    expect(pt.problem.stats[0]?.v).toBe("41,2%");
    expect(pt.problem.stats[0]?.l).toBe("dos 700.000 atendimentos têm motivo transacional");
    expect(pt.problem.stats[1]?.v).toBe("20,0%");
    expect(pt.problem.stats[2]?.v).toBe("91,5%");
    const versao = pt.dataStops.find((s) => s.id === "versao")?.stat;
    expect(versao).toEqual({ v: "12", l: "transações · 3 clientes · 4 reclamações", s: "QUALIDADE" });
    const en = comNumerosAoVivo(resolver(CONTEUDO_DO_MAIN, "en"), n, "en");
    expect(en.problem.stats[0]?.v).toBe("41.2%");
    expect(en.problem.stats[0]?.l).toBe("of 700,000 contacts have a transactional reason");
  });

  it("as barras do portão TF-IDF levam a acurácia com três casas e a largura em décimos", () => {
    const n = { ...SEM_NUMEROS, tfidf: { es: 0.8734, pt: 0.9 } };
    const m = comNumerosAoVivo(resolver(CONTEUDO_DO_MAIN, "en"), n, "en").models.list.find((x) => x.barsSrc === "TFIDF");
    expect(m?.bars).toEqual([
      { l: "ES", v: "0,873", w: 87.3 },
      { l: "PT", v: "0,900", w: 90 },
    ]);
  });

  it("o porcento arredonda a uma casa", () => {
    expect(porcento(0.34978493244897246, "pt")).toBe("35,0%");
    expect(porcento(0.9150823141267038, "es")).toBe("91,5%");
    expect(porcento(0.9055228276877761, "en")).toBe("90.6%");
  });
});
