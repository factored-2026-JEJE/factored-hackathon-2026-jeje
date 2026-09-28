import { useEffect, useState } from "react";
import { buscarMetricas, type Metricas } from "./api/cliente";

const porcento = (taxa: number | null) =>
  taxa === null ? "—" : taxa.toLocaleString("pt-BR", { style: "percent", maximumFractionDigits: 1 });
const ms = (valor: number | null) => (valor === null ? "—" : `${valor.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} ms`);

/** Métricas recomputadas dos eventos de cada turno (nada fixo na tela nem na API). */
export function MetricasDoAtendimento({ versao }: { versao: number }) {
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    buscarMetricas()
      .then((m) => {
        if (!ativo) return;
        setMetricas(m);
        setErro(false);
      })
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
    };
  }, [versao]);

  if (erro) return <p role="alert">Métricas indisponíveis.</p>;
  if (!metricas) return <p role="status">Carregando métricas…</p>;
  const linhas: [string, string][] = [
    ["Turnos", String(metricas.turnos)],
    ["Erros (turno desfeito)", `${metricas.erros} (${porcento(metricas.taxa_de_erro)})`],
    ["Conversas", String(metricas.conversas)],
    ["Encaminhadas para humano", `${metricas.conversas_encaminhadas} (${porcento(metricas.taxa_de_encaminhamento)})`],
    ["Pré-casos registrados", String(metricas.pre_casos_registrados)],
    ["Latência p50", ms(metricas.latencia_ms.p50)],
    ["Latência p95", ms(metricas.latencia_ms.p95)],
  ];
  return (
    <section aria-label="Métricas do atendimento" className="cartao">
      <h2>Métricas do atendimento</h2>
      <table aria-label="Métricas">
        <tbody>
          {linhas.map(([nome, valor]) => (
            <tr key={nome}>
              <th scope="row">{nome}</th>
              <td>{valor}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
