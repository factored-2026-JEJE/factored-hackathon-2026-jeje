import { useEffect, useState } from "react";
import { type Encaminhamento, filaDoAtendimento } from "./api/cliente";

const quando = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

/** Console simulado do atendente: o resumo de cada encaminhamento aberto, na ordem de chegada. */
export function FilaDoAtendimento({ versao }: { versao: number }) {
  const [fila, setFila] = useState<Encaminhamento[] | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    filaDoAtendimento()
      .then((lista) => {
        if (!ativo) return;
        setFila(lista);
        setErro(false);
      })
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
    };
  }, [versao]);

  return (
    <section aria-label="Fila do atendimento humano" className="cartao">
      <h2>Fila do atendimento humano</h2>
      <p className="nota">Console simulado do atendente (modo demo): o que ele recebe para continuar sem ler a conversa.</p>
      {erro && <p role="alert">Fila indisponível.</p>}
      {!erro && fila === null && <p role="status">Carregando fila…</p>}
      {fila?.length === 0 && <p>Nenhum encaminhamento aberto.</p>}
      <ol className="fila">
        {fila?.map((e) => (
          <li key={e.id} aria-label={`Encaminhamento ${e.id}`}>
            <p>
              <strong>{e.id}</strong> · {e.regra} · {e.idioma.toUpperCase()} · cliente {e.customer_id} · {quando(e.criado_em)}
            </p>
            <p>Pedido: “{e.pedido}”</p>
            {e.transacao && (
              <p>
                Transação {e.transacao.transaction_id}: {e.transacao.comercio ?? "sem comércio"}, {e.transacao.moeda}{" "}
                {e.transacao.valor}, {e.transacao.status}, {quando(e.transacao.data)}
              </p>
            )}
            {e.acoes.length > 0 && (
              <ul aria-label="Ações tentadas">
                {e.acoes.map((a, i) => (
                  <li key={i}>
                    {a.acao}: {a.resultado}
                  </li>
                ))}
              </ul>
            )}
            <ul aria-label="Pendências">
              {e.pendencias.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}
