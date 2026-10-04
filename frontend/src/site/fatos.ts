// O que o main (80eae5f) mudou desde o design, que foi feito com o produto no d9dfad0 (DEV-032a). O
// site mostra só o que existe, com o planejado marcado como planejado; cada troca abaixo tem a
// evidência ao lado, e o resto é o conteúdo do designer, sem mudança. Com VITE_SO_DESIGN=1 o site
// mostra só o design: é assim que a réplica é comparada com o HTML do designer.
import { CONTEUDO, T, type Conteudo } from "./conteudo";
import { LIGACOES, NOS, type Mapa } from "./mapa";

// DEV-042 (PR #60, PRD-010): o LLM do "não entendi" está ligado na demonstração e na publicação
// (INTERPRETADOR=leitor_modelo no serviço api do compose.yaml). No mapa, ele e a cascata até ele
// deixam de ser planejados.
export const MAPA_DO_MAIN: Mapa = {
  nos: { ...NOS, llm: { x: NOS.llm.x, y: NOS.llm.y, k: NOS.llm.k, h: NOS.llm.h, w: NOS.llm.w } },
  ligacoes: LIGACOES.map(([a, b, curva, tipo]) => [a, b, curva, tipo === "p" ? "l" : tipo] as const),
};

const c = CONTEUDO;

export const CONTEUDO_DO_MAIN: Conteudo = {
  ...c,
  sources: {
    ...c.sources,
    // A medida do LLM é a do conjunto de validação do VAL-003 (EV-221); a garantia de fraude está no
    // main desde o PR #76 (GARANTIA_DE_FRAUDE=true), medida no REG-22 e, sem bloqueio a mais, no REG-22b.
    "DEV-042": ["evid", "evidencias/EV-221 · VAL-003"],
    "DEV-046": ["evid", "evidencias/REG-22 · REG-22b"],
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
    if (s.id === "leitura" && s.cascade)
      return { ...s, cascade: s.cascade.map((x) => (x.st === "plan" ? { ...x, st: "off" as const } : x)) };
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
    list: c.models.list.map((m) =>
      m.planned ? { ...m, planned: false, role: T("só no “não entendi”", "solo en el “no entendí”", "only on “didn’t get it”") } : m,
    ),
  },
  results: {
    ...c.results,
    out: c.results.out.map((o) =>
      o[0] !== "DEV-046"
        ? o
        : ([
            "DEV-046",
            T(
              "Garantia de que a fraude chega ao atendente: entrou. No REG-22, de 65,1% para 89,9% (ES) e de 59,6% para 87,7% (PT), sem bloqueio a mais.",
              "Garantía de que el fraude llega al agente: entró. En el REG-22, de 65,1% a 89,9% (ES) y de 59,6% a 87,7% (PT), sin bloqueos de más.",
              "Guarantee that fraud reaches an agent: shipped. In REG-22, from 65.1% to 89.9% (ES) and 59.6% to 87.7% (PT), with no extra blocks.",
            ),
            T("entrou", "entró", "in"),
          ] as const),
    ),
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
