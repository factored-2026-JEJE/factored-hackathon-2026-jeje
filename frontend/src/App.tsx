import { Atendimento } from "./Atendimento";
import { IndicadoresDaEda } from "./IndicadoresDaEda";
import { QualidadeDosDados } from "./QualidadeDosDados";
import { StatusDoSistema } from "./StatusDoSistema";

export function App() {
  return (
    <main>
      <h1>JEJE</h1>
      <Atendimento />
      <StatusDoSistema />
      <QualidadeDosDados />
      <IndicadoresDaEda />
    </main>
  );
}
