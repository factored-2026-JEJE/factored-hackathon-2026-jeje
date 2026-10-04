import { useEffect, useState } from "react";
import { AVALIACAO } from "./abas/cliente/textos";
import { avaliarConversa, listarTestadores, type ReviewRegistrada, SessaoExpirada } from "./api/cliente";
import type { Traducao } from "./app/conteudo";
import { useLingua } from "./app/LinguaDoApp";
import { traduzir } from "./app/textos";

const CHAVE_TESTADOR = "jeje.testador";
const NOTAS = [1, 2, 3, 4, 5] as const;
const RESOLVEU = [
  { valor: "sim", rotulo: AVALIACAO.sim },
  { valor: "parcial", rotulo: AVALIACAO.parcial },
  { valor: "nao", rotulo: AVALIACAO.nao },
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
 * no banco ligada à conversa e, com o GitHub configurado, vira uma Issue com a transcrição. O design
 * não a tem: ela segue a língua da interface e a linguagem dele (cliente.css). */
export function AvaliarConversa({
  token,
  conversaId,
  aoExpirar,
}: {
  token: string;
  conversaId: string;
  aoExpirar: () => void;
}) {
  const { lingua } = useLingua();
  const tr = (texto: Traducao) => traduzir(texto, lingua);
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
      <p role="status" className="cli-avaliacao-ok">
        {tr(AVALIACAO.enviada)}{" "}
        {enviada.issue_url && (
          <a href={enviada.issue_url} target="_blank" rel="noreferrer">
            {tr(AVALIACAO.issue)}
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
      aria-label={tr(AVALIACAO.titulo)}
      className="cli-avaliacao"
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <h4>{tr(AVALIACAO.titulo)}</h4>
      <label>
        {tr(AVALIACAO.quem)}
        <select value={avaliador} onChange={(e) => setAvaliador(e.target.value)}>
          <option value="">{tr(AVALIACAO.escolha)}</option>
          {testadores.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <div role="group" aria-label={tr(AVALIACAO.nota)} className="cli-avaliacao-opcoes">
        {NOTAS.map((n) => (
          <button key={n} type="button" aria-pressed={nota === n} onClick={() => setNota(n)}>
            {n}
          </button>
        ))}
      </div>
      <div role="group" aria-label={tr(AVALIACAO.resolveu)} className="cli-avaliacao-opcoes">
        {RESOLVEU.map((r) => (
          <button key={r.valor} type="button" aria-pressed={resolveu === r.valor} onClick={() => setResolveu(r.valor)}>
            {tr(r.rotulo)}
          </button>
        ))}
      </div>
      <label>
        {tr(AVALIACAO.comentario)}
        <textarea value={comentario} maxLength={2000} rows={3} onChange={(e) => setComentario(e.target.value)} />
      </label>
      <button type="submit" disabled={!pronta || enviando}>
        {tr(AVALIACAO.registrar)}
      </button>
      {falha && <p role="alert">{tr(AVALIACAO.falhou)}</p>}
    </form>
  );
}
