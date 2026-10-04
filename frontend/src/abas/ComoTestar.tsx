import { useEffect, useState } from "react";
import { listarPersonas } from "../api/cliente";
import { useLingua } from "../app/LinguaDoApp";
import { frasesDoExemplo } from "../frasesDoCliente";
import { escolherPersona } from "../personas";
import type { PropsDaArea } from "./area";
import "./console.css";

/** O guia dos jurados, #how-to-test (DEV-032b, 2.10), como no design: os três caminhos em ES e PT,
 * cada um com o "Try in ES/PT" (a casca entra, vai à conversa e manda a frase), e o que conferir.
 * O caminho normal usa a frase do exemplo da persona que a casca escolhe (DEV-073): a frase fixa do
 * design ("45,90 del 10/03") não acha transação nenhuma nos dados de verdade. */
export function AreaComoTestar({ experimentar }: PropsDaArea) {
  const { t } = useLingua();
  const [exemplo, setExemplo] = useState<[string, string] | null>(null);

  useEffect(() => {
    let ativo = true;
    listarPersonas()
      .then((lista) => {
        const persona = escolherPersona(lista);
        if (ativo && persona?.exemplo) setExemplo(frasesDoExemplo(persona.exemplo));
      })
      .catch(() => {});
    return () => {
      ativo = false;
    };
  }, []);

  const caminhos = t.guide.paths.map((p, i) => {
    const [es, pt] = i === 0 && exemplo ? exemplo : [p.es, p.pt];
    return { num: `0${i + 1}`, nome: p.n, es, pt, x: p.x };
  });

  return (
    <div className="cn-pagina cn-guia">
      <div className="cn-guia-topo">
        <p className="cn-rotulo">
          <span className="cn-ponto cn-cobalto" />
          {t.guide.kicker}
        </p>
        <h2 className="cn-titulo">{t.guide.title}</h2>
        <p>{t.guide.sub}</p>
      </div>
      <div className="cn-caminhos">
        {caminhos.map((c) => (
          <article key={c.num} className="cn-caminho" aria-label={c.nome}>
            <div className="cn-caminho-topo">
              <span className="cn-caminho-num">{c.num}</span>
              <span className="cn-caminho-nome">{c.nome}</span>
            </div>
            <div className="cn-caminho-corpo">
              <span className="cn-frase">
                <span>ES</span>“{c.es}”
              </span>
              <span className="cn-frase">
                <span>PT</span>“{c.pt}”
              </span>
              <span className="cn-mini">{t.guide.expect}</span>
              <span className="cn-texto">{c.x}</span>
            </div>
            <div className="cn-caminho-botoes">
              <button type="button" className="cn-testar-es" onClick={() => experimentar(c.es)}>
                {t.guide.tryEs} →
              </button>
              <button type="button" className="cn-testar-pt" onClick={() => experimentar(c.pt)}>
                {t.guide.tryPt} →
              </button>
            </div>
          </article>
        ))}
      </div>
      <section className="cn-conferir" aria-label={t.guide.check}>
        <span className="cn-rotulo">{t.guide.check}</span>
        <ul>
          {t.guide.checks.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
