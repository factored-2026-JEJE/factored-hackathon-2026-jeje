// As mensagens do app com o site (DEV-032b) contra janelas de verdade do jsdom: o pai é outra janela, e
// a origem é conferida dos dois lados (o design mandava para '*' e ouvia qualquer um).
import { type Ambiente, avisarRota, avisarTurno, ouvirLingua } from "./ponte";

const ORIGEM = window.location.origin;
let molduras: HTMLIFrameElement[] = [];

/** Uma janela de verdade para fazer o papel do site (o pai do app na janela dele). */
function outraJanela(): Window {
  const moldura = document.createElement("iframe");
  document.body.append(moldura);
  molduras.push(moldura);
  if (!moldura.contentWindow) throw new Error("o jsdom não criou a janela da moldura");
  return moldura.contentWindow;
}

afterEach(() => {
  molduras.forEach((m) => m.remove());
  molduras = [];
});

function mensagem(dados: unknown, origin: string, source: Window) {
  window.dispatchEvent(new MessageEvent("message", { data: dados, origin, source }));
}

test("só a língua mandada pelo pai, na própria origem, muda a língua do app", () => {
  const pai = outraJanela();
  const estranho = outraJanela();
  const ambiente: Ambiente = { proprio: window, pai, origem: ORIGEM };
  const recebidas: string[] = [];
  const parar = ouvirLingua((l) => recebidas.push(l), ambiente);
  mensagem({ type: "jeje-lang", lang: "es" }, "https://outro.example", pai);
  mensagem({ type: "jeje-lang", lang: "es" }, ORIGEM, estranho);
  mensagem({ type: "jeje-lang", lang: "fr" }, ORIGEM, pai);
  mensagem({ type: "jeje-route", lang: "pt" }, ORIGEM, pai);
  expect(recebidas).toEqual([]);
  mensagem({ type: "jeje-lang", lang: "pt" }, ORIGEM, pai);
  expect(recebidas).toEqual(["pt"]);
  parar();
  mensagem({ type: "jeje-lang", lang: "es" }, ORIGEM, pai);
  expect(recebidas).toEqual(["pt"]);
});

test("a rota vai para o pai, na própria origem, e o app aberto direto não posta nada", () => {
  const pai = outraJanela();
  const postar = vi.spyOn(pai, "postMessage");
  avisarRota("#atendente", { proprio: window, pai, origem: ORIGEM });
  expect(postar).toHaveBeenCalledExactlyOnceWith({ type: "jeje-app-route", hash: "#atendente" }, ORIGEM);
  const proprio = vi.spyOn(window, "postMessage");
  avisarRota("#atendente", { proprio: window, pai: window, origem: ORIGEM });
  expect(proprio).not.toHaveBeenCalled();
});

test("o turno vai com os nós de verdade por onde passou, inclusive o leitor, e se foi para uma pessoa", () => {
  const pai = outraJanela();
  const postar = vi.spyOn(pai, "postMessage");
  const ambiente = { proprio: window, pai, origem: ORIGEM };
  avisarTurno(
    {
      regra: "POL-HUM-01",
      acao: "humano",
      interpretacao: "leitor:e5@abc123",
      transaction_id: null,
      resolucao: null,
      opcoes: [],
      atendimento: "AT-00000001",
      estado: "com_humano",
    },
    ambiente,
  );
  const [enviada, origem] = postar.mock.calls[0] ?? [];
  expect(origem).toBe(ORIGEM);
  expect(enviada).toMatchObject({ type: "jeje-turn", human: true, rule: "POL-HUM-01", leitura: "leitor" });
  const nos = (enviada as { route: string[] }).route;
  expect(nos).toContain("leitor");
  expect(nos).toContain("acoes");
  expect(nos).not.toContain("qual");
});
