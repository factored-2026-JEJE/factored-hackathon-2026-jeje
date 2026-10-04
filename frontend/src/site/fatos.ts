// O que o main (80eae5f) mudou desde o design, que foi feito com o produto no d9dfad0 (DEV-032a). O
// site mostra só o que existe, com o planejado marcado como planejado; cada troca abaixo tem a
// evidência ao lado, e o resto é o conteúdo do designer, sem mudança. Com VITE_SO_DESIGN=1 o site
// mostra só o design: é assim que a réplica é comparada com o HTML do designer.
import { CONTEUDO, T, type Conteudo, type Traducao } from "./conteudo";
import { LIGACOES, NOS, type Mapa } from "./mapa";

// DEV-042 (PR #60, PRD-010): o LLM do "não entendi" está ligado na demonstração e na publicação
// (INTERPRETADOR=leitor_modelo no serviço api do compose.yaml). No mapa, ele e a cascata até ele
// deixam de ser planejados.
export const MAPA_DO_MAIN: Mapa = {
  nos: { ...NOS, llm: { x: NOS.llm.x, y: NOS.llm.y, k: NOS.llm.k, h: NOS.llm.h, w: NOS.llm.w } },
  ligacoes: LIGACOES.map(([a, b, curva, tipo]) => [a, b, curva, tipo === "p" ? "l" : tipo] as const),
};

const c = CONTEUDO;

// O pilar de confiabilidade com as medidas do congelado 3cf8c3f (VAL-021 da validação, 04/10): cada prova do
// design trocada, pela fonte dela, pela medida do congelado, com a fonte nova.
const CONFIABILIDADE_DO_CONGELADO: Readonly<Record<string, readonly [Traducao, string]>> = {
  "EV-182": [
    T(
      "No congelado, 1.031 de 1.035 mutantes do backend se comportaram como esperado.",
      "En el congelado, 1.031 de 1.035 mutantes del backend se comportaron como se esperaba.",
      "On the frozen commit, 1,031 of 1,035 backend mutants behaved as expected.",
    ),
    "ACH-188",
  ],
  "EV-250": [
    T(
      "No navegador, 22 jornadas pegaram 30 de 30 defeitos plantados, no congelado.",
      "En el navegador, 22 recorridos atraparon 30 de 30 defectos plantados, en el congelado.",
      "In the browser, 22 journeys caught 30 of 30 planted defects on the frozen commit.",
    ),
    "NAV-01",
  ],
  "CON-01": [
    T(
      "Contrato da API testado com entradas geradas: nenhuma falha em 31 operações, no congelado.",
      "Contrato de la API probado con entradas generadas: ninguna falla en 31 operaciones, en el congelado.",
      "API contract tested with generated inputs: zero failures across 31 operations on the frozen commit.",
    ),
    "CON-01",
  ],
  "EXP-008": [
    T(
      "Com 1 processo e 8 clientes ao mesmo tempo, p95 de 83 ms nas regras e de 139 ms com o leitor, no congelado.",
      "Con 1 proceso y 8 clientes a la vez, p95 de 83 ms en las reglas y de 139 ms con el lector, en el congelado.",
      "With 1 worker and 8 concurrent clients, p95 of 83 ms on the rules and 139 ms with the reader, on the frozen commit.",
    ),
    "EXP-008",
  ],
};

export const CONTEUDO_DO_MAIN: Conteudo = {
  ...c,
  sources: {
    ...c.sources,
    // A medida do LLM é a do conjunto de validação do VAL-003 (EV-221); a garantia de fraude está no
    // main desde o PR #76 (GARANTIA_DE_FRAUDE=true), medida no REG-22 e, sem bloqueio a mais, no REG-22b.
    "DEV-042": ["evid", "evidencias/EV-221 · VAL-003"],
    "DEV-046": ["evid", "evidencias/REG-22 · REG-22b"],
    // O teste final rodou uma vez no congelado 3cf8c3f (EV-276), e a tabela 2 também (EV-277).
    "VAL-019": ["evid", "evidencias/VAL-019 · EV-276"],
    "VAL-019a": ["evid", "evidencias/VAL-019a · EV-277"],
    // O tempo das regras medido no congelado, nas mensagens dos conjuntos da validação (o README do 2.14).
    LAT: ["team", "README · 14.124 msgs · p50/p95"],
    // O portão de release (make atacar) no congelado, rodado pela validação no V6
    // (NOV-13a-20261004T132513-1da3): 1 inseguro em 128, o ACH-160.
    "NOV-13a": ["evid", "evidencias/NOV-13a · ACH-160"],
    // As medidas do congelado no pilar de confiabilidade e no ranking (VAL-021 da validação, 04/10).
    "ACH-188": ["evid", "evidencias/V6 · ACH-188"],
    "NAV-01": ["evid", "evidencias/NAV-01 · EV-274"],
    "CON-01": ["evid", "evidencias/CON-01 · 20261004T071739"],
    "EXP-008": ["evid", "evidencias/EXP-008 · 04/10"],
    "QT-01": ["evid", "evidencias/QT-01"],
  },
  ui: {
    ...c.ui,
    kindNotes: {
      ...c.ui.kindNotes,
      live: T(
        "Da API do produto, ao vivo. Sem a API (site público), o último valor lido.",
        "De la API del producto, en vivo. Sin la API (sitio público), el último valor leído.",
        "From the product API, live. Without the API (public site), the last value read.",
      ),
      evid: T(
        "Da base de evidências da validação (jeje-validation-v1/evidencias).",
        "De la base de evidencias de la validación (jeje-validation-v1/evidencias).",
        "From the validation evidence base (jeje-validation-v1/evidencias).",
      ),
      code: T(
        "Do código ou da configuração do main (80eae5f).",
        "Del código o la configuración del main (80eae5f).",
        "From the main branch code or config (80eae5f).",
      ),
    },
  },
  stops: c.stops.map((s) => {
    // O tempo das regras: o do congelado 3cf8c3f (p50 de 2,07 ms e p95 de 5,24 ms), não o da medida do design.
    if (s.id === "leitura" && s.cascade)
      return {
        ...s,
        cascade: s.cascade.map((x) => (x.st === "plan" ? { ...x, st: "off" as const } : x)),
        stat: {
          v: T("2,1 ms", "2,1 ms", "2.1 ms"),
          l: T(
            "p50 de CPU por mensagem nas regras (p95 5,2 ms)",
            "p50 de CPU por mensaje en las reglas (p95 5,2 ms)",
            "p50 CPU per message in the rules (p95 5.2 ms)",
          ),
          s: "LAT",
        },
      };
    // O ranking com o teste independente da validação (QT-01), o mesmo que o README e o deck citam.
    if (s.id === "qual")
      return {
        ...s,
        stat: {
          v: "72%",
          l: T(
            "dos pedidos com pista resolvidos direto, contra 38% do filtro exato; 0% de proposta errada",
            "de los pedidos con pista resueltos directo, contra 38% del filtro exacto; 0% de propuesta errada",
            "of requests with a clue solved directly, vs 38% for the exact filter; 0% wrong proposals",
          ),
          s: "QT-01",
        },
      };
    // A janela do app no site (design de 03/10): o Caddy deixa só a própria origem embutir a página
    // (frontend/Caddyfile, conferido no seguranca.spec.ts e no scripts/conferir-publicacao.sh).
    if (s.id === "entrada")
      return {
        ...s,
        protects: s.protects?.map((p, i) =>
          i !== 0
            ? p
            : T(
                "Cabeçalhos nosniff, X-Frame-Options SAMEORIGIN, frame-ancestors self e no-referrer: só o próprio site embute o app.",
                "Cabeceras nosniff, X-Frame-Options SAMEORIGIN, frame-ancestors self y no-referrer: solo el propio sitio incrusta la app.",
                "nosniff, X-Frame-Options SAMEORIGIN, frame-ancestors self and no-referrer headers: only the site itself can frame the app.",
              ),
        ),
      };
    return s;
  }),
  nodes: { ...c.nodes, llm: { n: c.nodes.llm.n, s: "qwen3:4b", stop: c.nodes.llm.stop, model: c.nodes.llm.model } },
  models: {
    ...c.models,
    list: c.models.list.map((m) => {
      // O par do LLM é o do VAL-003 de validação (EV-221), medido no fd24539 (0d811eb antes da limpeza do
      // histórico), de 01/10: o commit fica dito, porque o do congelado é a tabela 2.
      if (m.planned)
        return {
          ...m,
          planned: false,
          role: T("só no “não entendi”", "solo en el “no entendí”", "only on “didn’t get it”"),
          barsNote: T(
            "acerto na primeira fala dos cenários de validação, no fd24539 de 01/10, antes do congelado; chamado em 9% a 23% das mensagens, ~0,5 s cada",
            "acierto en la primera frase de los escenarios de validación, en el fd24539 del 01/10, antes del congelado; llamado en 9% a 23% de los mensajes, ~0,5 s cada uno",
            "first-turn accuracy on validation scenarios, at fd24539 (Oct 1), before the frozen commit; called on 9%–23% of messages, ~0.5 s each",
          ),
        };
      // O ranking com o QT-01, como o README e o deck.
      if (m.pairs?.[0]?.s === "REG-07")
        return {
          ...m,
          pairs: [
            { ...m.pairs[0], l: T("validação · QT-01", "validación · QT-01", "validation · QT-01"), a: 72, s: "QT-01" },
            ...m.pairs.slice(1),
          ],
          barsNote: T(
            "resolvidos direto; 0% de proposta errada no teste da validação",
            "resueltos directo; 0% de propuesta errada en el test de la validación",
            "solved directly; 0% wrong proposals in the validation test",
          ),
        };
      return m;
    }),
  },
  // O placar do atacante: o do portão de release no congelado (128 episódios), não o do NOV-13 de antes do
  // congelamento (1 em 112), e o caso inseguro dito como saiu.
  pillars: {
    ...c.pillars,
    list: c.pillars.list.map((p) =>
      p.id !== "conf" ? p : { ...p, proofs: p.proofs.map((prova) => CONFIABILIDADE_DO_CONGELADO[prova[1]] ?? prova) },
    ),
    seg: {
      ...c.pillars.seg,
      honest: {
        v: "1/128",
        l: T(
          "resultado inseguro em 128 conversas com um cliente adversário simulado por LLM, no portão de release do commit congelado: um relato de fraude dentro de uma contestação ficou sem atendente (ACH-160). Mostramos.",
          "resultado inseguro en 128 conversaciones con un cliente adversario simulado por LLM, en el gate de release del commit congelado: un reporte de fraude dentro de una impugnación quedó sin agente (ACH-160). Lo mostramos.",
          "unsafe outcome in 128 conversations with an LLM-simulated adversarial customer, at the frozen commit’s release gate: a fraud report inside a dispute went without an agent (ACH-160). We show it.",
        ),
        s: "NOV-13a",
      },
    },
  },
  results: {
    ...c.results,
    out: c.results.out.map((o) =>
      o[0] !== "DEV-046"
        ? o
        : ([
            "DEV-046",
            T(
              "Garantia de que a fraude chega ao atendente: entrou. No REG-22, de 65,1% para 89,9% (ES) e de 59,6% para 87,7% (PT), sem bloqueio a mais. No portão do atacante, no congelado, 1 relato de fraude em 128 conversas ficou sem atendente (ACH-160).",
              "Garantía de que el fraude llega al agente: entró. En el REG-22, de 65,1% a 89,9% (ES) y de 59,6% a 87,7% (PT), sin bloqueos de más. En el gate del atacante, en el congelado, 1 reporte de fraude en 128 conversaciones quedó sin agente (ACH-160).",
              "Guarantee that fraud reaches an agent: shipped. In REG-22, from 65.1% to 89.9% (ES) and 59.6% to 87.7% (PT), with no extra blocks. At the attacker gate, on the frozen commit, 1 fraud report in 128 conversations went without an agent (ACH-160).",
            ),
            T("entrou", "entró", "in"),
          ] as const),
    ),
    // A tabela 2 (VAL-019a, EXP-002a-20261004T124023-3dfd, EV-277) como saiu: negativa, pelo critério escrito
    // antes do teste; e o ponto de operação da curva do leitor (VAL-019b, NOV-40-20261004T124038-3623),
    // descritivo. Os números vêm de resultados/tabela-2-3cf8c3f.json e evidencias/medicoes.csv da validação.
    t2: T(
      "Tabela 2 · o componente aprendido, uma vez no congelado, num conjunto novo e selado antes do teste: em PT, com 237 mensagens, o acerto na primeira fala vai de 71,3% só com as regras a 79,3% com o sistema (+8,0 p.p. [+4,2; +12,2]). A ação indevida sobe +0,5 p.p. [+0,0; +1,6], e o limite passa de 1 ponto: o critério escrito antes do teste não foi cumprido, e o resultado fica como saiu. O ES não foi medido (menos de 20 mensagens em alguma intenção).",
      "Tabla 2 · el componente aprendido, una vez en el congelado, en un conjunto nuevo y sellado antes de la prueba: en PT, con 237 mensajes, el acierto en la primera frase va de 71,3% solo con las reglas a 79,3% con el sistema (+8,0 p.p. [+4,2; +12,2]). La acción indebida sube +0,5 p.p. [+0,0; +1,6], y el límite pasa de 1 punto: el criterio escrito antes de la prueba no se cumplió, y el resultado queda como salió. El ES no se midió (menos de 20 mensajes en alguna intención).",
      "Table 2 · the learned component, run once on the frozen commit, on a new set sealed before the test: in PT, over 237 messages, first-turn accuracy goes from 71.3% with rules only to 79.3% with the system (+8.0 pp [+4.2; +12.2]). Undue actions rise +0.5 pp [+0.0; +1.6], and the bound exceeds 1 point: the criterion written before the test was not met, and the result stands as it came out. ES was not measured (fewer than 20 messages in some intent).",
    ),
    curva: T(
      "O limiar do leitor, descritivo: no limiar entregue, 0,80, o sistema automatiza 81,6% das primeiras falas em ES e 78,9% em PT; das automatizadas, erra 3 de 31 (ES) e 2 de 30 (PT); a ação indevida é 1 de 21 nas duas línguas.",
      "El umbral del lector, descriptivo: en el umbral entregado, 0,80, el sistema automatiza el 81,6% de las primeras frases en ES y el 78,9% en PT; de las automatizadas, falla 3 de 31 (ES) y 2 de 30 (PT); la acción indebida es 1 de 21 en las dos lenguas.",
      "The reader threshold, descriptive: at the delivered threshold, 0.80, the system automates 81.6% of first messages in ES and 78.9% in PT; of those automated, it gets 3 of 31 wrong (ES) and 2 of 30 (PT); undue actions are 1 of 21 in both languages.",
    ),
  },
  // O turno de exemplo da contestação diz o tempo das regras do congelado, como a parada da leitura.
  journeys: {
    ...c.journeys,
    contestar: {
      ...c.journeys.contestar,
      turn: { ...c.journeys.contestar.turn, reader: T("regras · 2,1 ms", "reglas · 2,1 ms", "rules · 2.1 ms") },
    },
  },
  footer: {
    ...c.footer,
    proto: T(
      "Cada número leva à sua fonte: a API ao vivo, o código, as evidências da validação ou a medida do time.",
      "Cada número lleva a su fuente: la API en vivo, el código, las evidencias de la validación o la medida del equipo.",
      "Every number links to its source: the live API, the code, the validation evidence or a team measurement.",
    ),
  },
  dock: {
    ...c.dock,
    note: T(
      "Turnos de exemplo, na fixture sintética. Com o acesso dos jurados, a conversa é com a API de verdade.",
      "Turnos de ejemplo, en la fixture sintética. Con el acceso del jurado, la conversación es con la API real.",
      "Sample turns on the synthetic fixture. With the judges’ access, the chat talks to the real API.",
    ),
    noteLive: T(
      "Ao vivo: POST /conversas na API, como um cliente de demonstração.",
      "En vivo: POST /conversas en la API, como un cliente de demostración.",
      "Live: POST /conversas on the API, as a demo customer.",
    ),
  },
};
