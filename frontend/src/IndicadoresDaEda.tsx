import { useEffect, useState } from "react";
import { buscarEda, type IndicadorEda } from "./api/cliente";

type Estado =
  | { tipo: "carregando" }
  | { tipo: "erro"; detalhe: string }
  | { tipo: "pronto"; indicadores: IndicadorEda[] };

const inteiro = (n: number) => n.toLocaleString("pt-BR");
const percentual = (p: number | null) =>
  p === null ? "—" : p.toLocaleString("pt-BR", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });

function Indicador({ indicador }: { indicador: IndicadorEda }) {
  const comSoma = indicador.unidade_soma !== null;
  return (
    <article aria-labelledby={`eda-${indicador.id}`}>
      <h3 id={`eda-${indicador.id}`}>{indicador.pergunta}</h3>
      <table>
        <thead>
          <tr>
            <th scope="col">Grupo</th>
            <th scope="col">{indicador.tipo === "taxa" ? "Resolvidos" : "Registros"}</th>
            <th scope="col">{indicador.tipo === "taxa" ? "Taxa" : "Participação"}</th>
            {comSoma && <th scope="col">Participação em {indicador.unidade_soma}</th>}
          </tr>
        </thead>
        <tbody>
          {indicador.linhas.map((linha) => (
            <tr key={linha.grupo}>
              <th scope="row">{linha.grupo}</th>
              <td>
                {indicador.tipo === "taxa"
                  ? `${inteiro(linha.contagem)} de ${inteiro(linha.base)}`
                  : inteiro(linha.contagem)}
              </td>
              <td>{percentual(linha.proporcao)}</td>
              {comSoma && <td>{percentual(linha.proporcao_soma)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      <details>
        <summary>Consulta SQL</summary>
        <pre>{indicador.consulta}</pre>
      </details>
    </article>
  );
}

/** Por que este fluxo: indicadores da base que sustentam o foco em transações (R01). */
export function IndicadoresDaEda() {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  useEffect(() => {
    const controle = new AbortController();
    buscarEda(controle.signal)
      .then((indicadores) => setEstado({ tipo: "pronto", indicadores }))
      .catch((erro: unknown) => {
        if (!controle.signal.aborted) setEstado({ tipo: "erro", detalhe: String(erro) });
      });
    return () => controle.abort();
  }, []);

  // A seção aparece já; os números chegam quando as consultas terminam (milhões de linhas na
  // base real levam alguns segundos).
  return (
    <section aria-label="Por que este fluxo">
      <h2>Por que este fluxo</h2>
      <p>
        Números da base carregada, cada um com a consulta que o produziu. Eles descrevem o dataset,
        não o efeito do sistema.
      </p>
      {estado.tipo === "carregando" && <p role="status">Calculando indicadores…</p>}
      {estado.tipo === "erro" && <p role="alert">Indicadores indisponíveis ({estado.detalhe})</p>}
      {estado.tipo === "pronto" &&
        estado.indicadores.map((indicador) => <Indicador key={indicador.id} indicador={indicador} />)}
    </section>
  );
}
