import { useState } from "react";
import {
  type AvaliacaoDeContestacao,
  confirmarProposta,
  type PreCaso,
  proporContestacao,
  Recusado,
  SessaoExpirada,
  type Transacao,
} from "./api/cliente";

type Estado =
  | { tipo: "avaliando" }
  | { tipo: "proposta"; propostaId: string }
  | { tipo: "confirmando"; propostaId: string }
  | { tipo: "registrado"; preCaso: PreCaso; novo: boolean }
  | { tipo: "encaminhado"; mensagem: string }
  | { tipo: "erro"; mensagem: string };

// Texto para cada regra que não abre pré-caso (matriz de autonomia, DEV-006).
function explicar(avaliacao: AvaliacaoDeContestacao): string {
  const { regra, detalhe } = avaliacao.decisao;
  if (regra === "POL-DISP-03") return `Já existe o pré-caso ${detalhe} para esta transação.`;
  if (regra === "POL-DISP-02")
    return "Esta transação não pode ser contestada automaticamente pela situação dela. Vamos encaminhar você a um atendente.";
  if (regra === "POL-HUM-02")
    return "Esta contestação precisa de um atendente (valor acima do limite ou sem conversão confiável).";
  return "Vamos encaminhar você a um atendente.";
}

/** Contestação de uma transação: a política decide; o pré-caso só existe depois de confirmado. */
export function Contestacao({
  token,
  transacao,
  aoRegistrar,
  aoExpirar,
}: {
  token: string;
  transacao: Transacao;
  aoRegistrar: () => void;
  aoExpirar: () => void;
}) {
  const [estado, setEstado] = useState<Estado | null>(null);

  function falhou(e: unknown, mensagem: string) {
    if (e instanceof SessaoExpirada) aoExpirar();
    else if (e instanceof Recusado) setEstado({ tipo: "erro", mensagem: e.message });
    else setEstado({ tipo: "erro", mensagem });
  }

  async function avaliar() {
    setEstado({ tipo: "avaliando" });
    try {
      const avaliacao = await proporContestacao(token, transacao.transaction_id);
      if (avaliacao.proposta) setEstado({ tipo: "proposta", propostaId: avaliacao.proposta.id });
      else setEstado({ tipo: "encaminhado", mensagem: explicar(avaliacao) });
    } catch (e) {
      falhou(e, "Não foi possível avaliar a contestação agora.");
    }
  }

  async function confirmar(propostaId: string) {
    setEstado({ tipo: "confirmando", propostaId });
    try {
      const preCaso = await confirmarProposta(token, propostaId);
      setEstado({ tipo: "registrado", preCaso, novo: true });
      aoRegistrar();
    } catch (e) {
      falhou(e, "O pré-caso não foi registrado; nada foi criado. Tente de novo.");
    }
  }

  if (estado === null)
    return (
      <button type="button" onClick={() => void avaliar()}>
        Contestar
      </button>
    );
  if (estado.tipo === "avaliando") return <span role="status">Avaliando…</span>;
  if (estado.tipo === "proposta" || estado.tipo === "confirmando")
    return (
      <div role="group" aria-label={`Confirmar contestação de ${transacao.transaction_id}`}>
        <p>Abrir um pré-caso de contestação para esta transação? Isso não estorna o valor.</p>
        <button
          type="button"
          disabled={estado.tipo === "confirmando"}
          onClick={() => void confirmar(estado.propostaId)}
        >
          Confirmar contestação
        </button>
        <button type="button" disabled={estado.tipo === "confirmando"} onClick={() => setEstado(null)}>
          Cancelar
        </button>
      </div>
    );
  if (estado.tipo === "registrado")
    return <p role="status">Pré-caso recebido: protocolo {estado.preCaso.protocolo}</p>;
  if (estado.tipo === "encaminhado") return <p role="status">{estado.mensagem}</p>;
  return <p role="alert">{estado.mensagem}</p>;
}
