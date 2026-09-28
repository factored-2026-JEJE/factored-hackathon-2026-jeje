import { useEffect, useState } from "react";
import { buscarQualidade, type QualidadeTabela } from "./api/cliente";

type Estado =
  | { tipo: "carregando" }
  | { tipo: "erro"; detalhe: string }
  | { tipo: "relatorio"; tabelas: QualidadeTabela[] };

const soma = (contagens: Record<string, number>) =>
  Object.values(contagens).reduce((total, n) => total + n, 0);

const numero = (n: number) => n.toLocaleString("pt-BR");

/** Invariante da curadoria: nenhum registro some entre raw e curada. */
const fecha = (t: QualidadeTabela) => t.raw === t.curado + t.quarentena + t.copias_descartadas;

export function QualidadeDosDados() {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  useEffect(() => {
    const controle = new AbortController();
    buscarQualidade(controle.signal)
      .then((tabelas) => setEstado({ tipo: "relatorio", tabelas }))
      .catch((erro: unknown) => {
        if (!controle.signal.aborted) setEstado({ tipo: "erro", detalhe: String(erro) });
      });
    return () => controle.abort();
  }, []);

  if (estado.tipo === "carregando") return <p role="status">Carregando qualidade dos dados…</p>;
  if (estado.tipo === "erro") return <p role="alert">Relatório indisponível ({estado.detalhe})</p>;
  if (estado.tabelas.length === 0) return <p>Nenhuma carga registrada ainda.</p>;

  const inconsistentes = estado.tabelas.filter((t) => !fecha(t)).map((t) => t.tabela);
  return (
    <section aria-label="Qualidade dos dados">
      <h2>Qualidade dos dados</h2>
      {inconsistentes.length > 0 && (
        <p role="alert">Contagens inconsistentes em: {inconsistentes.join(", ")}</p>
      )}
      <table>
        <thead>
          <tr>
            <th scope="col">Tabela</th>
            <th scope="col">Registros</th>
            <th scope="col">Curados</th>
            <th scope="col">Quarentena</th>
            <th scope="col">Cópias descartadas</th>
            <th scope="col">Referências anuladas</th>
            <th scope="col">Normalizados</th>
          </tr>
        </thead>
        <tbody>
          {estado.tabelas.map((t) => (
            <tr key={t.tabela}>
              <th scope="row">{t.tabela}</th>
              <td>{numero(t.raw)}</td>
              <td>{numero(t.curado)}</td>
              <td>{numero(t.quarentena)}</td>
              <td>{numero(t.copias_descartadas)}</td>
              <td>{numero(soma(t.anulacoes))}</td>
              <td>{numero(soma(t.normalizacoes))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
