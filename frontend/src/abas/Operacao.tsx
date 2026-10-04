import { IndicadoresDaEda } from "../IndicadoresDaEda";
import { MetricasDoAtendimento } from "../MetricasDoAtendimento";
import { QualidadeDosDados } from "../QualidadeDosDados";
import { StatusDoSistema } from "../StatusDoSistema";
import type { PropsDaArea } from "./area";

/** A aba da operação: métricas, prontidão, qualidade dos dados e a EDA (Agente 2, 2.10). */
export function AreaDaOperacao({ versao }: PropsDaArea) {
  return (
    <div className="pagina dados">
      <MetricasDoAtendimento versao={versao} />
      <StatusDoSistema />
      <QualidadeDosDados />
      <IndicadoresDaEda />
    </div>
  );
}
