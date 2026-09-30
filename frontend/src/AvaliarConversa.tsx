import { useEffect, useState } from "react";
import { avaliarConversa, listarTestadores, type ReviewRegistrada, SessaoExpirada } from "./api/cliente";

const CHAVE_TESTADOR = "jeje.testador";
const NOTAS = [1, 2, 3, 4, 5] as const;
const RESOLVEU = [
  { valor: "sim", rotulo: "Resolveu" },
  { valor: "parcial", rotulo: "Em parte" },
  { valor: "nao", rotulo: "Não resolveu" },
] as const;

function lerTestador(): string {
  try {
    return localStorage.getItem(CHAVE_TESTADOR) ?? "";
  } catch {
    return "";
  }
}

function guardarTestador(testador: string) {
  try {
    localStorage.setItem(CHAVE_TESTADOR, testador);
  } catch {
    // Sem armazenamento: escolhe de novo na próxima conversa.
  }
}

/** Avaliação da conversa por alguém do time de teste (só no modo de demonstração): a review fica
 * no banco ligada à conversa e, com o GitHub configurado, vira uma Issue com a transcrição. */
export function AvaliarConversa({
  token,
  conversaId,
  aoExpirar,
}: {
  token: string;
  conversaId: string;
  aoExpirar: () => void;
}) {
  const [testadores, setTestadores] = useState<string[]>([]);
  const [avaliador, setAvaliador] = useState(lerTestador);
  const [nota, setNota] = useState<number | null>(null);
  const [resolveu, setResolveu] = useState<(typeof RESOLVEU)[number]["valor"] | null>(null);
  const [comentario, setComentario] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [enviada, setEnviada] = useState<ReviewRegistrada | null>(null);
  const [falha, setFalha] = useState(false);

  useEffect(() => {
    let ativo = true;
    listarTestadores()
      .then((lista) => ativo && setTestadores(lista))
      .catch(() => ativo && setTestadores([]));
    return () => {
      ativo = false;
    };
  }, []);

  if (testadores.length === 0) return null;

  if (enviada) {
    return (
      <p role="status" className="sucesso">
        Review enviada, obrigado.{" "}
        {enviada.issue_url && (
          <a href={enviada.issue_url} target="_blank" rel="noreferrer">
            Ver a Issue
          </a>
        )}
      </p>
    );
  }

  const pronta = testadores.includes(avaliador) && nota !== null && resolveu !== null;

  async function enviar() {
    if (!pronta || enviando || nota === null || resolveu === null) return;
    setEnviando(true);
    setFalha(false);
    try {
      guardarTestador(avaliador);
      setEnviada(await avaliarConversa(token, conversaId, { avaliador, nota, resolveu, comentario }));
    } catch (e) {
      if (e instanceof SessaoExpirada) aoExpirar();
      else setFalha(true);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form
      aria-label="Avaliar esta conversa"
      className="avaliacao"
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <h4>Avaliar esta conversa</h4>
      <label>
        Quem está testando
        <select value={avaliador} onChange={(e) => setAvaliador(e.target.value)}>
          <option value="">Escolha</option>
          {testadores.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <div role="group" aria-label="Nota" className="acoes">
        {NOTAS.map((n) => (
          <button key={n} type="button" aria-pressed={nota === n} onClick={() => setNota(n)}>
            {n}
          </button>
        ))}
      </div>
      <div role="group" aria-label="O assistente resolveu?" className="acoes">
        {RESOLVEU.map((r) => (
          <button key={r.valor} type="button" aria-pressed={resolveu === r.valor} onClick={() => setResolveu(r.valor)}>
            {r.rotulo}
          </button>
        ))}
      </div>
      <label>
        O que deu errado ou como deveria ter sido
        <textarea value={comentario} maxLength={2000} rows={3} onChange={(e) => setComentario(e.target.value)} />
      </label>
      <button type="submit" disabled={!pronta || enviando}>
        Registrar avaliação
      </button>
      {falha && <p role="alert">Não foi possível enviar a review. Tente de novo.</p>}
    </form>
  );
}
