import { useEffect, useState } from "react";
import { type BloqueioDeCartao, bloqueiosDoAtendimento, desbloquearCartao, Recusado } from "./api/cliente";

const quando = (iso: string) => new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
const cartao = (b: BloqueioDeCartao) => (b.ultimos4 ? `${b.produto} final ${b.ultimos4}` : b.produto);
const MOTIVO: Record<string, string> = { pedido: "pedido do cliente", roubo_perda: "relato de roubo ou perda" };

/** Console simulado do atendente: os bloqueios de cartão ativos (PRD-007) e o desbloqueio. */
export function BloqueiosDoAtendimento({ versao }: { versao: number }) {
  const [bloqueios, setBloqueios] = useState<BloqueioDeCartao[] | null>(null);
  const [erro, setErro] = useState(false);
  const [desfeitos, setDesfeitos] = useState(0);
  const [aviso, setAviso] = useState<string | null>(null);

  // Só sai da lista quando a API confirma o desbloqueio (sem remoção otimista).
  async function desbloquear(id: string) {
    try {
      const desfeito = await desbloquearCartao(id);
      setAviso(`Você desbloqueou ${desfeito.id}.`);
    } catch (e) {
      setAviso(e instanceof Recusado ? `${id}: ${e.message}.` : `Não foi possível desbloquear ${id}.`);
    }
    setDesfeitos((n) => n + 1);
  }

  useEffect(() => {
    let ativo = true;
    bloqueiosDoAtendimento()
      .then((lista) => {
        if (!ativo) return;
        setBloqueios(lista);
        setErro(false);
      })
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
    };
  }, [versao, desfeitos]);

  return (
    <section aria-label="Bloqueios de cartão" className="cartao">
      <h2>Bloqueios de cartão</h2>
      <p className="nota">
        Bloqueio simulado (modo demo). Com dispositivo cadastrado, o aviso ao atendente é o bloqueio aparecer aqui.
      </p>
      {erro && <p role="alert">Bloqueios indisponíveis.</p>}
      {aviso && <p role="status">{aviso}</p>}
      {!erro && bloqueios === null && <p role="status">Carregando bloqueios…</p>}
      {bloqueios?.length === 0 && <p>Nenhum bloqueio ativo.</p>}
      <ol className="fila">
        {bloqueios?.map((b) => (
          <li key={b.id} aria-label={`Bloqueio ${b.id}`}>
            <p>
              <strong>{b.id}</strong> · {cartao(b)} · bloqueio {b.tipo} · cliente {b.customer_id}
            </p>
            <p>
              Motivo: {MOTIVO[b.motivo] ?? b.motivo} · dispositivo {b.dispositivo} · desde {quando(b.criado_em)} · prazo
              de reversão até {quando(b.reversivel_ate)}
            </p>
            <button type="button" onClick={() => void desbloquear(b.id)}>
              Desbloquear {b.id}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
