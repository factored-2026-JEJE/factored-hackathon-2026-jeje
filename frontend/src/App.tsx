import { useCallback, useEffect, useState } from "react";
import { Atendimento } from "./Atendimento";
import { BloqueiosDoAtendimento } from "./BloqueiosDoAtendimento";
import { FilaDoAtendimento } from "./FilaDoAtendimento";
import { IndicadoresDaEda } from "./IndicadoresDaEda";
import { MetricasDoAtendimento } from "./MetricasDoAtendimento";
import { QualidadeDosDados } from "./QualidadeDosDados";
import { StatusDoSistema } from "./StatusDoSistema";

// Três áreas da demonstração, cada uma com endereço próprio: #cliente, #atendente e #operacao.
const ABAS = [
  ["cliente", "Cliente"],
  ["atendente", "Atendente"],
  ["operacao", "Operação"],
] as const;
type Aba = (typeof ABAS)[number][0];

function abaDoEndereco(): Aba {
  const pedida = window.location.hash.slice(1);
  return ABAS.find(([id]) => id === pedida)?.[0] ?? "cliente";
}

export function App() {
  // Cada pré-caso, encaminhamento ou bloqueio criado na conversa atualiza o console e as métricas.
  const [versao, setVersao] = useState(0);
  const mudou = useCallback(() => setVersao((v) => v + 1), []);
  const [aba, setAba] = useState<Aba>(abaDoEndereco);
  useEffect(() => {
    const seguir = () => setAba(abaDoEndereco());
    window.addEventListener("hashchange", seguir);
    return () => window.removeEventListener("hashchange", seguir);
  }, []);
  // As abas escondidas continuam montadas: a conversa não se perde, e a fila, os bloqueios e as
  // métricas seguem sendo atualizados enquanto o cliente conversa.
  return (
    <>
      <header className="topo">
        <h1>JEJE</h1>
        <p>Atendimento de transações em espanhol e português · demonstração com os dados sintéticos do desafio</p>
      </header>
      <nav className="abas" role="tablist" aria-label="Áreas da demonstração">
        {ABAS.map(([id, rotulo]) => (
          <a
            key={id}
            href={`#${id}`}
            role="tab"
            id={`aba-${id}`}
            aria-selected={aba === id}
            aria-controls={`painel-${id}`}
            onClick={() => setAba(id)}
          >
            {rotulo}
          </a>
        ))}
      </nav>
      <main className="pagina">
        <div role="tabpanel" id="painel-cliente" aria-labelledby="aba-cliente" hidden={aba !== "cliente"}>
          <Atendimento aoMudar={mudou} />
        </div>
        <div
          role="tabpanel"
          id="painel-atendente"
          aria-labelledby="aba-atendente"
          hidden={aba !== "atendente"}
          className="colunas"
        >
          <FilaDoAtendimento versao={versao} />
          <BloqueiosDoAtendimento versao={versao} />
        </div>
        <div role="tabpanel" id="painel-operacao" aria-labelledby="aba-operacao" hidden={aba !== "operacao"} className="dados">
          <MetricasDoAtendimento versao={versao} />
          <StatusDoSistema />
          <QualidadeDosDados />
          <IndicadoresDaEda />
        </div>
      </main>
    </>
  );
}
