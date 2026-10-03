// As mensagens do app com o site (DEV-032b): o site abre o app numa janela (iframe) e mostra na barra o
// endereço da aba aberta; a cada turno da conversa, acende no mapa o caminho que ele fez. O app e o site
// estão na mesma origem (/ e /site/): o app só posta para o pai, na própria origem, e só ouve o pai, na
// própria origem. O design usava '*' e não conferia quem mandou.
import type { ResultadoDoTurno } from "../api/cliente";
import { caminhoDoTurno } from "../site/turnoNoMapa";
import type { Lingua } from "./conteudo";
import { ehLingua } from "./lingua";

/** Quem é o app e quem é o pai (o site, quando o app está na janela dele). */
export interface Ambiente {
  readonly proprio: Window;
  readonly pai: Window;
  readonly origem: string;
}

export function ambienteAtual(): Ambiente {
  return { proprio: window, pai: window.parent, origem: window.location.origin };
}

function postar(mensagem: object, ambiente: Ambiente) {
  // Fora de uma janela (o app aberto direto), o pai é o próprio app: não há ninguém para avisar.
  if (ambiente.pai === ambiente.proprio) return;
  ambiente.pai.postMessage(mensagem, ambiente.origem);
}

/** A aba mudou: o site mostra o endereço dela na barra da janela. */
export function avisarRota(hash: string, ambiente: Ambiente = ambienteAtual()) {
  postar({ type: "jeje-app-route", hash }, ambiente);
}

type Turno = Pick<
  ResultadoDoTurno,
  "regra" | "acao" | "interpretacao" | "transaction_id" | "resolucao" | "opcoes" | "atendimento" | "estado"
>;

/** Um turno terminou: o site acende os nós por onde ele passou (inclusive o leitor e o LLM). */
export function avisarTurno(turno: Turno, ambiente: Ambiente = ambienteAtual()) {
  const caminho = caminhoDoTurno(turno);
  postar(
    { type: "jeje-turn", route: caminho.nos, human: caminho.humano, rule: turno.regra, leitura: caminho.leitura },
    ambiente,
  );
}

/** A língua escolhida no site chega ao app aberto na janela. Devolve a função que para de ouvir. */
export function ouvirLingua(aoMudar: (lingua: Lingua) => void, ambiente: Ambiente = ambienteAtual()): () => void {
  const ouvir = (evento: MessageEvent) => {
    if (ambiente.pai === ambiente.proprio) return;
    if (evento.origin !== ambiente.origem || evento.source !== ambiente.pai) return;
    const dados = evento.data as { type?: unknown; lang?: unknown } | null;
    if (dados && dados.type === "jeje-lang" && ehLingua(dados.lang)) aoMudar(dados.lang);
  };
  ambiente.proprio.addEventListener("message", ouvir);
  return () => ambiente.proprio.removeEventListener("message", ouvir);
}
