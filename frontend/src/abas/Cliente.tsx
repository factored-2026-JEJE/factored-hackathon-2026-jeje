import { Atendimento } from "../Atendimento";
import type { PropsDaArea } from "./area";

/** A aba do cliente: o acesso por persona e, com a sessão, a conversa e o painel (Agente 1, 1.3). */
export function AreaDoCliente({
  versao,
  aoMudar,
  pergunta,
  aoPerguntar,
  aoPerguntado,
}: PropsDaArea & {
  /** A frase que vai para a conversa: a do "Perguntar sobre esta" ou a do `experimentar`. */
  readonly pergunta: string | null;
  readonly aoPerguntar: (pergunta: string) => void;
  readonly aoPerguntado: () => void;
}) {
  return <Atendimento versao={versao} aoMudar={aoMudar} pergunta={pergunta} aoPerguntar={aoPerguntar} aoPerguntado={aoPerguntado} />;
}
