import { type RefObject, useEffect, useRef, useState } from "react";
import {
  buscarEda,
  buscarMetricas,
  buscarProntidao,
  buscarQualidade,
  type EventoRecente,
  type IndicadorEda,
  type Metricas,
  type Prontidao,
  type QualidadeTabela,
  ultimosEventos,
} from "../api/cliente";
import type { Lingua } from "../app/conteudo";
import { useLingua } from "../app/LinguaDoApp";
import type { PropsDaArea } from "./area";
import { hora, numero, percentual } from "./formato";
import { acaoDoTurno, CONSOLE, efeitoDoTurno, OPERACAO, traduzir } from "./textos";
import "./console.css";

const COBALTO = "#2B35F0";
const TINTA = "#16150F";
const VERMELHAO = "#FF5520";

interface Dados {
  readonly prontidao: Prontidao | null;
  readonly metricas: Metricas | null;
  readonly eventos: readonly EventoRecente[];
  readonly qualidade: readonly QualidadeTabela[] | null;
}

type Eda =
  | { readonly tipo: "carregando" }
  | { readonly tipo: "erro" }
  | { readonly tipo: "pronta"; readonly indicadores: readonly IndicadorEda[] };

const soma = (contagens: Record<string, number>) => Object.values(contagens).reduce((total, n) => total + n, 0);
/** Invariante da curadoria: nenhum registro some entre raw e curada. */
const fecha = (q: QualidadeTabela) => q.raw === q.curado + q.quarentena + q.copias_descartadas;
const curta = (versao: string) => (versao.length > 12 ? `${versao.slice(0, 4)}…${versao.slice(-4)}` : versao);
const ms = (n: number | null | undefined) => (n == null ? null : Math.round(n));

/** Conta as voltas da aba à tela: a casca esconde as áreas com o `hidden` do painel, sem desmontar.
 * Relendo a cada volta, o turno sem efeito (uma consulta) também aparece nos números. */
function useVoltas(raiz: RefObject<HTMLElement | null>): number {
  const [voltas, setVoltas] = useState(0);
  useEffect(() => {
    const painel = raiz.current?.closest("[role=tabpanel]");
    if (!painel) return;
    const observador = new MutationObserver(() => {
      if (!painel.hasAttribute("hidden")) setVoltas((n) => n + 1);
    });
    observador.observe(painel, { attributes: true, attributeFilter: ["hidden"] });
    return () => observador.disconnect();
  }, [raiz]);
  return voltas;
}

/** A aba da operação (DEV-032b, 2.10), como no design: a prontidão, as métricas recalculadas dos
 * eventos, as regras usadas, os últimos turnos, a qualidade dos dados e, depois, a EDA. Os números
 * vêm da API, relidos a cada efeito da conversa e a cada volta à aba; a EDA, que descreve a base, é
 * lida uma vez. */
export function AreaDaOperacao({ versao }: PropsDaArea) {
  const { lingua, t } = useLingua();
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState(false);
  const [eda, setEda] = useState<Eda>({ tipo: "carregando" });
  const raiz = useRef<HTMLDivElement>(null);
  const voltas = useVoltas(raiz);

  useEffect(() => {
    let ativo = true;
    // Cada parte falha sozinha: sem a qualidade, a prontidão e as métricas continuam na tela.
    const ou = <T,>(p: Promise<T>, padrao: T) => p.catch(() => padrao);
    Promise.all([
      ou(buscarProntidao(), null),
      ou(buscarMetricas(), null),
      ou(ultimosEventos(8), [] as EventoRecente[]),
      ou(buscarQualidade(), null),
    ])
      .then(([prontidao, metricas, eventos, qualidade]) => {
        if (!ativo) return;
        setDados({ prontidao, metricas, eventos, qualidade });
        setErro(prontidao === null && metricas === null);
      })
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
    };
  }, [versao, voltas]);

  useEffect(() => {
    // Na base real as consultas da EDA levam segundos: elas não seguram o resto da aba.
    const controle = new AbortController();
    buscarEda(controle.signal)
      .then((indicadores) => setEda({ tipo: "pronta", indicadores }))
      .catch(() => {
        if (!controle.signal.aborted) setEda({ tipo: "erro" });
      });
    return () => controle.abort();
  }, []);

  const p = dados?.prontidao;
  const m = dados?.metricas;
  const fresca = (m?.turnos ?? 0) === 0;
  const estado = p ? OPERACAO.banco[p.database] : undefined;
  const banco = !p ? "—" : p.database === "ok" ? t.ops.ok : estado ? traduzir(estado, lingua) : p.database;
  const dataset = p?.dataset ?? null;
  const recusada = dataset?.recusada ?? null;
  const semDados = p ? traduzir(OPERACAO.semDados, lingua) : "—";
  const prontidao: [string, string, string][] = [
    [t.ops.db, banco, p?.database === "ok" ? COBALTO : VERMELHAO],
    [t.ops.version, dataset ? `${dataset.source} · ${curta(dataset.version)}` : semDados, dataset ? COBALTO : VERMELHAO],
    [t.ops.loaded, dataset ? hora(dataset.loaded_at) : "—", TINTA],
    [t.ops.rejected, recusada ? curta(recusada.version) : t.ops.none, recusada ? VERMELHAO : TINTA],
  ];
  const p50 = ms(m?.latencia_ms.p50);
  const p95 = ms(m?.latencia_ms.p95);
  const metricas: [string, string][] = m
    ? [
        [t.ops.m.turns, String(m.turnos)],
        [t.ops.m.errors, String(m.erros)],
        [t.ops.m.convs, String(m.conversas)],
        [t.ops.m.handoffs, String(m.conversas_encaminhadas)],
        [t.ops.m.precases, String(m.pre_casos_registrados)],
        [`${t.ops.m.lat} · ms`, p50 === null || p95 === null ? "—" : `${p50}/${p95}`],
        [t.ops.m.model, String(m.modelo.chamadas)],
      ]
    : [];
  const regras = Object.entries(m?.regras ?? {}).sort((a, b) => b[1] - a[1]);
  const maior = Math.max(1, ...regras.map(([, n]) => n));
  const qualidade = dados?.qualidade ?? null;
  const naoFecham = (qualidade ?? []).filter((q) => !fecha(q)).map((q) => q.tabela);
  const tituloDaQualidade = dataset?.source === "fixture" ? t.ops.quality : traduzir(OPERACAO.qualidadeDaBase, lingua);
  const tituloDaEda = traduzir(OPERACAO.eda, lingua);

  return (
    <div className="cn-pagina" ref={raiz}>
      <div className="cn-bloco">
        <p className="cn-rotulo">
          <span className="cn-ponto cn-cobalto" />
          {t.ops.kicker}
        </p>
        <h2 className="cn-titulo">{t.ops.title}</h2>
      </div>
      {dados === null && !erro && <p role="status">{traduzir(CONSOLE.carregando, lingua)}</p>}
      {erro && <p role="alert">{traduzir(CONSOLE.indisponivel, lingua)}</p>}
      <div className="cn-prontidao" role="group" aria-label={t.ops.ready}>
        {prontidao.map(([k, v, cor]) => (
          <div key={k}>
            <span className="cn-mini">{k}</span>
            <span className="cn-valor">
              <span className="cn-ponto" style={{ background: cor }} />
              {v}
            </span>
          </div>
        ))}
      </div>
      {recusada && dataset && (
        <p className="cn-conferencia cn-errada" role="alert">
          {t.ops.rejected} {curta(recusada.version)} · {hora(recusada.em)}: {recusada.motivo}.{" "}
          {traduzir(OPERACAO.segue, lingua)} {curta(dataset.version)}.
        </p>
      )}
      <section className="cn-bloco" aria-label={t.ops.metrics}>
        <span className="cn-rotulo">{t.ops.metrics}</span>
        {m && fresca && <p className="cn-nova">{t.ops.fresh}</p>}
        <div className="cn-metricas">
          {metricas.map(([l, v]) => (
            <div key={l}>
              <span className="cn-numero">{v}</span>
              <span className="cn-mini">{l}</span>
            </div>
          ))}
        </div>
      </section>
      <div className="cn-duas">
        <section className="cn-regras-col" aria-label={t.ops.rules}>
          <span className="cn-rotulo">{t.ops.rules}</span>
          <div className="cn-regras">
            {regras.length === 0 && <span className="cn-aviso">{t.ops.rulesNone}</span>}
            {regras.map(([regra, n]) => (
              <div key={regra} className="cn-barra-linha">
                <span>{regra}</span>
                <span className="cn-barra">
                  <span style={{ width: `${(n / maior) * 100}%` }} />
                </span>
                <span>{n}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="cn-eventos-col" aria-label={t.ops.events}>
          <span className="cn-rotulo">{t.ops.events}</span>
          <div className="cn-terminal">
            {(dados?.eventos.length ?? 0) === 0 && <span className="cn-apagado">$ tail -f eventos · —</span>}
            {dados?.eventos.map((e, i) => {
              const acao = acaoDoTurno(e.acao, e.regra);
              return (
                <span key={`${e.requisicao}-${i}`}>
                  {hora(e.criado_em)} · request_id={e.requisicao ? e.requisicao.slice(0, 13) : "—"} ·{" "}
                  <span className="cn-regra-evento">{e.regra ?? "—"}</span> · {acao ? t.act[acao] : (e.acao ?? "—")} ·{" "}
                  {t.eff[efeitoDoTurno(e.acao, e.efeito)]}
                  {e.efeito ? ` ${e.efeito}` : ""}
                </span>
              );
            })}
          </div>
        </section>
      </div>
      <section className="cn-bloco" aria-label={tituloDaQualidade}>
        <span className="cn-rotulo">{tituloDaQualidade}</span>
        {dados !== null && qualidade === null && <p className="cn-aviso">{traduzir(CONSOLE.indisponivel, lingua)}</p>}
        {qualidade !== null && qualidade.length === 0 && (
          <p className="cn-aviso">{traduzir(OPERACAO.semCarga, lingua)}</p>
        )}
        {qualidade !== null && qualidade.length > 0 && (
          <>
            <div className="cn-rolavel">
              <div className="cn-tabela" role="table" aria-label={tituloDaQualidade}>
                <div className="cn-linha" role="row">
                  {t.ops.qcols.map((h) => (
                    <span key={h} className="cn-cabeca" role="columnheader">
                      {h}
                    </span>
                  ))}
                </div>
                {qualidade.map((q) => (
                  <div key={q.tabela} className="cn-linha" role="row">
                    <span role="rowheader">{q.tabela}</span>
                    {[q.raw, q.curado, q.quarentena, q.copias_descartadas, soma(q.anulacoes)].map((n, i) => (
                      <span key={i} role="cell">
                        {numero(n, lingua)}
                      </span>
                    ))}
                  </div>
                ))}
              </div>
            </div>
            {naoFecham.length === 0 ? (
              <span className="cn-conferencia">✓ {t.ops.check}</span>
            ) : (
              <span className="cn-conferencia cn-errada" role="alert">
                {traduzir(OPERACAO.naoFecha, lingua)}: {naoFecham.join(", ")}
              </span>
            )}
          </>
        )}
      </section>
      <section className="cn-bloco" aria-label={tituloDaEda}>
        <span className="cn-rotulo">{tituloDaEda}</span>
        <p className="cn-nota">{traduzir(OPERACAO.edaNota, lingua)}</p>
        {eda.tipo === "carregando" && <p role="status">{traduzir(OPERACAO.edaCalculando, lingua)}</p>}
        {eda.tipo === "erro" && <p className="cn-aviso">{traduzir(CONSOLE.indisponivel, lingua)}</p>}
        {eda.tipo === "pronta" &&
          eda.indicadores.map((indicador) => <Indicador key={indicador.id} indicador={indicador} lingua={lingua} />)}
      </section>
    </div>
  );
}

/** Um indicador da EDA (R01), no estilo da qualidade dos dados: a pergunta, as linhas e a consulta. */
function Indicador({ indicador, lingua }: { readonly indicador: IndicadorEda; readonly lingua: Lingua }) {
  const taxa = indicador.tipo === "taxa";
  const comSoma = indicador.unidade_soma !== null;
  const colunas = [
    traduzir(OPERACAO.edaGrupo, lingua),
    traduzir(taxa ? OPERACAO.edaResolvidos : OPERACAO.edaRegistros, lingua),
    traduzir(taxa ? OPERACAO.edaTaxa : OPERACAO.edaParticipacao, lingua),
    ...(comSoma ? [`${traduzir(OPERACAO.edaParticipacaoEm, lingua)} ${indicador.unidade_soma}`] : []),
  ];
  const de = traduzir(OPERACAO.edaDe, lingua);
  return (
    <article className="cn-indicador" aria-label={indicador.pergunta}>
      <h3 className="cn-pergunta">{indicador.pergunta}</h3>
      <div className="cn-rolavel">
        <div
          className={comSoma ? "cn-tabela cn-tabela-eda" : "cn-tabela cn-tabela-eda cn-sem-soma"}
          role="table"
          aria-label={indicador.pergunta}
        >
          <div className="cn-linha" role="row">
            {colunas.map((c) => (
              <span key={c} className="cn-cabeca" role="columnheader">
                {c}
              </span>
            ))}
          </div>
          {indicador.linhas.map((linha) => (
            <div key={linha.grupo} className="cn-linha" role="row">
              <span role="rowheader">{linha.grupo}</span>
              <span role="cell">
                {taxa
                  ? `${numero(linha.contagem, lingua)} ${de} ${numero(linha.base, lingua)}`
                  : numero(linha.contagem, lingua)}
              </span>
              <span role="cell">{percentual(linha.proporcao, lingua)}</span>
              {comSoma && <span role="cell">{percentual(linha.proporcao_soma, lingua)}</span>}
            </div>
          ))}
        </div>
      </div>
      <details className="cn-consulta">
        <summary className="cn-mini">{traduzir(OPERACAO.consulta, lingua)}</summary>
        <pre>{indicador.consulta}</pre>
      </details>
    </article>
  );
}
