import { useCallback, useState } from "react";
import { Atendimento } from "./Atendimento";
import { BloqueiosDoAtendimento } from "./BloqueiosDoAtendimento";
import { FilaDoAtendimento } from "./FilaDoAtendimento";
import { IndicadoresDaEda } from "./IndicadoresDaEda";
import { MetricasDoAtendimento } from "./MetricasDoAtendimento";
import { QualidadeDosDados } from "./QualidadeDosDados";
import { StatusDoSistema } from "./StatusDoSistema";

export function App() {
  // Cada pré-caso, encaminhamento ou bloqueio criado na conversa atualiza o console e as métricas.
  const [versao, setVersao] = useState(0);
  const mudou = useCallback(() => setVersao((v) => v + 1), []);
  return (
    <>
      <header className="topo">
        <h1>JEJE</h1>
        <p>Atendimento de transações em espanhol e português · demonstração com os dados sintéticos do desafio</p>
      </header>
      <main className="pagina">
        <div className="colunas">
          <Atendimento aoMudar={mudou} />
          <div className="lateral">
            <FilaDoAtendimento versao={versao} />
            <BloqueiosDoAtendimento versao={versao} />
            <MetricasDoAtendimento versao={versao} />
          </div>
        </div>
        <div className="dados">
          <StatusDoSistema />
          <QualidadeDosDados />
          <IndicadoresDaEda />
        </div>
      </main>
    </>
  );
}
