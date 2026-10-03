import { BloqueiosDoAtendimento } from "../BloqueiosDoAtendimento";
import { FilaDoAtendimento } from "../FilaDoAtendimento";
import type { PropsDaArea } from "./area";

/** A aba do atendente: a fila e os bloqueios (Agente 2, 2.10). */
export function AreaDoAtendente({ versao }: PropsDaArea) {
  return (
    <div className="pagina colunas">
      <FilaDoAtendimento versao={versao} />
      <BloqueiosDoAtendimento versao={versao} />
    </div>
  );
}
