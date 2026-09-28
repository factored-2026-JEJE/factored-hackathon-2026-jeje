import { useEffect, useState } from "react";
import { buscarProntidao, type Prontidao } from "./api/cliente";

type Estado =
  | { tipo: "carregando" }
  | { tipo: "erro"; detalhe: string }
  | { tipo: "resposta"; prontidao: Prontidao };

const ROTULO_BANCO: Record<Prontidao["database"], string> = {
  ok: "conectado",
  unreachable: "inacessível",
  not_migrated: "sem migrations aplicadas",
  reloading: "recarregando os dados",
};

export function StatusDoSistema() {
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });

  useEffect(() => {
    const controle = new AbortController();
    buscarProntidao(controle.signal)
      .then((prontidao) => setEstado({ tipo: "resposta", prontidao }))
      .catch((erro: unknown) => {
        if (!controle.signal.aborted) setEstado({ tipo: "erro", detalhe: String(erro) });
      });
    return () => controle.abort();
  }, []);

  if (estado.tipo === "carregando") return <p role="status">Verificando o sistema…</p>;
  if (estado.tipo === "erro") {
    return (
      <p role="alert">
        API inacessível ({estado.detalhe})
      </p>
    );
  }

  const { status, database, dataset } = estado.prontidao;
  return (
    <section aria-label="Status do sistema">
      <h2>{status === "ready" ? "Pronto para atender" : "Indisponível"}</h2>
      <dl>
        <dt>Banco</dt>
        <dd>{ROTULO_BANCO[database]}</dd>
        <dt>Dados</dt>
        <dd>
          {dataset
            ? `versão ${dataset.version.slice(0, 12)} (${dataset.source}), carregada em ${new Date(dataset.loaded_at).toLocaleString("pt-BR")}`
            : "nenhum dataset carregado"}
        </dd>
      </dl>
    </section>
  );
}
