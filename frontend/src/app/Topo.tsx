import { useEffect, useState } from "react";
import { filaDoAtendimento } from "../api/cliente";
import { type Aba, ABAS } from "./abas";
import { useLingua } from "./LinguaDoApp";
import { LINGUAS } from "./lingua";
import { useSessao } from "./sessao";

/** Quantos casos esperam um atendente: relido a cada efeito da conversa (`versao`). */
function useCasosNaFila(versao: number): number {
  const [quantos, setQuantos] = useState(0);
  useEffect(() => {
    let ativo = true;
    filaDoAtendimento()
      .then((fila) => ativo && setQuantos(fila.length))
      .catch(() => ativo && setQuantos(0));
    return () => {
      ativo = false;
    };
  }, [versao]);
  return quantos;
}

/** A barra do topo do design: a marca, as quatro áreas (com os casos na fila na do atendente), quem
 * está na sessão de teste, o "Leave" e a língua da interface. */
export function Topo({ aba, versao, aoEscolher }: { aba: Aba; versao: number; aoEscolher: (aba: Aba) => void }) {
  const { lingua, t, mudarLingua } = useLingua();
  const { sessao, sair } = useSessao();
  const naFila = useCasosNaFila(versao);
  return (
    <header className="app-topo">
      <div className="app-marca">
        <span className="app-jeje">JEJE</span>
        <span className="app-demo">{t.top.demo}</span>
      </div>
      <nav className="app-abas" role="tablist" aria-label="JEJE">
        {ABAS.map(([id, chave]) => (
          <a
            key={id}
            href={`#${id}`}
            role="tab"
            id={`aba-${id}`}
            aria-selected={aba === id}
            aria-current={aba === id ? "page" : undefined}
            aria-controls={`painel-${id}`}
            className="app-aba"
            onClick={() => aoEscolher(id)}
          >
            {t.tabs[chave]}
            {id === "atendente" && naFila > 0 && <span className="app-na-fila">{naFila}</span>}
          </a>
        ))}
      </nav>
      <div className="app-direita">
        {sessao && (
          <div className="app-sessao">
            <span className="app-sessao-quem">
              <span className="app-quadrado" />
              <span>
                {sessao.cliente.customer_id} · {sessao.cliente.nome} ·{" "}
                {t.top.device[sessao.dispositivo === "cadastrado" ? "reg" : "new"]}
              </span>
            </span>
            <button type="button" className="app-sair" onClick={() => sair()}>
              {t.top.leave}
            </button>
          </div>
        )}
        <div role="group" aria-label="Language" className="app-linguas">
          {LINGUAS.map((l) => (
            <button key={l} type="button" aria-pressed={lingua === l} onClick={() => mudarLingua(l)}>
              {l.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
