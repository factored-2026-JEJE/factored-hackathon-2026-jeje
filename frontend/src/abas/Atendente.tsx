import { useEffect, useState } from "react";
import {
  assumirEncaminhamento,
  type BloqueioDeCartao,
  bloqueiosDoAtendimento,
  desbloquearCartao,
  type Encaminhamento,
  filaDoAtendimento,
  listarPersonas,
} from "../api/cliente";
import type { Lingua, Textos } from "../app/conteudo";
import { useLingua } from "../app/LinguaDoApp";
import type { PropsDaArea } from "./area";
import { diaMes, dinheiro, hora } from "./formato";
import {
  ACAO_DO_CASO,
  ACOES_FORA_DO_DESIGN,
  CASOS_FORA_DO_DESIGN,
  CONSOLE,
  DESFEITO,
  DESFEITO_POR,
  TIPO_DA_REGRA,
  traduzir,
} from "./textos";
import "./console.css";

// O "In Customer, try one of these" da fila vazia, as mesmas frases do design.
const TENTATIVAS = ["Me robaron la tarjeta", "Quero falar com um atendente", "Quiero pedir un préstamo"];

type Fato = { readonly k: string; readonly v: string };

/** A aba do atendente (DEV-032b, 2.10), como no design: a fila com o caso pronto e os bloqueios de
 * cartão. Tudo vem da API, e nada sai da tela antes de a API confirmar (sem remoção otimista). */
export function AreaDoAtendente({ versao, aoMudar, experimentar }: PropsDaArea) {
  const { lingua, t } = useLingua();
  const [fila, setFila] = useState<Encaminhamento[] | null>(null);
  const [bloqueios, setBloqueios] = useState<BloqueioDeCartao[] | null>(null);
  const [nomes, setNomes] = useState<Record<string, string>>({});
  // Os casos assumidos aqui saem da fila aberta da API, mas ficam na tela como "Taken by you".
  const [assumidos, setAssumidos] = useState<Encaminhamento[]>([]);
  const [erro, setErro] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [recarga, setRecarga] = useState(0);

  useEffect(() => {
    let ativo = true;
    listarPersonas()
      .then((lista) => ativo && setNomes(Object.fromEntries(lista.map((p) => [p.customer_id, p.nome]))))
      .catch(() => {});
    return () => {
      ativo = false;
    };
  }, []);

  useEffect(() => {
    let ativo = true;
    Promise.all([filaDoAtendimento(), bloqueiosDoAtendimento()])
      .then(([casos, ativos]) => {
        if (!ativo) return;
        setFila(casos);
        setBloqueios(ativos);
        setErro(false);
      })
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
    };
  }, [versao, recarga]);

  async function assumir(id: string) {
    try {
      const assumido = await assumirEncaminhamento(id);
      setAssumidos((atuais) => [...atuais.filter((c) => c.id !== id), assumido]);
      setAviso(null);
      aoMudar();
    } catch {
      setAviso(traduzir(CONSOLE.naoAssumido, lingua));
    }
    setRecarga((n) => n + 1);
  }

  async function desbloquear(id: string) {
    try {
      await desbloquearCartao(id);
      setAviso(null);
      aoMudar();
    } catch {
      setAviso(traduzir(CONSOLE.naoDesbloqueado, lingua));
    }
    setRecarga((n) => n + 1);
  }

  const cliente = (id: string) => (nomes[id] ? `${id} · ${nomes[id]}` : id);
  const abertos = fila ?? [];
  const tomados = assumidos.filter((c) => !abertos.some((a) => a.id === c.id));
  const casos = [...abertos, ...tomados];
  const ativos = bloqueios ?? [];

  return (
    <div className="cn-pagina">
      <div className="cn-cabecalho">
        <div>
          <p className="cn-rotulo">
            <span className="cn-ponto cn-vermelhao" />
            {t.ag.kicker}
          </p>
          <h2 className="cn-titulo">{t.ag.title}</h2>
        </div>
        <p className="cn-sub">{t.ag.sub}</p>
      </div>
      {erro && <p role="alert">{traduzir(CONSOLE.indisponivel, lingua)}</p>}
      {aviso && <p role="status">{aviso}</p>}
      <div className="cn-duas">
        <section className="cn-fila" aria-label={t.ag.queue}>
          <span className="cn-rotulo">
            {t.ag.queue} · {abertos.length}
          </span>
          {fila === null && !erro && <p role="status">{traduzir(CONSOLE.carregando, lingua)}</p>}
          {fila !== null && casos.length === 0 && (
            <div className="cn-vazia">
              <span className="cn-vazia-titulo">{t.ag.empty}</span>
              <span>{t.ag.emptyTry}</span>
              <div className="cn-tentativas">
                {TENTATIVAS.map((frase) => (
                  <button key={frase} type="button" className="cn-tentar" onClick={() => experimentar(frase)}>
                    “{frase}”
                  </button>
                ))}
              </div>
            </div>
          )}
          {casos.map((caso) => (
            <Caso
              key={caso.id}
              caso={caso}
              tomado={tomados.includes(caso)}
              cliente={cliente(caso.customer_id)}
              cartao={ativos.find((b) => b.atendimento === caso.id)}
              aoAssumir={() => void assumir(caso.id)}
              t={t}
              lingua={lingua}
            />
          ))}
        </section>
        <section className="cn-lateral" aria-label={t.ag.blocks}>
          <span className="cn-rotulo">
            {t.ag.blocks} · {ativos.length}
          </span>
          <div className="cn-caixa">
            {bloqueios !== null && ativos.length === 0 && <p className="cn-aviso">{t.ag.blocksNone}</p>}
            {ativos.map((b) => (
              <div key={b.id} className="cn-bloqueio" aria-label={b.id}>
                <span className="cn-final">•••• {b.ultimos4 ?? "····"}</span>
                <span className="cn-cliente">{cliente(b.customer_id)}</span>
                <span className="cn-bloqueio-linha">
                  <span className={b.tipo === "preventivo" ? "cn-etiqueta cn-preventivo" : "cn-etiqueta"}>
                    {b.tipo === "preventivo" ? t.side.blockedPrev : t.side.blockedFull} · {t.ag.since}{" "}
                    {hora(b.criado_em)}
                  </span>
                  <button
                    type="button"
                    className="cn-desbloquear"
                    aria-label={`${t.ag.unblock} ${b.id}`}
                    onClick={() => void desbloquear(b.id)}
                  >
                    {t.ag.unblock}
                  </button>
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

/** Um caso da fila, como no design: o topo, os quatro campos, as falas e o "Take case". */
function Caso({
  caso,
  tomado,
  cliente: nomeDoCliente,
  cartao,
  aoAssumir,
  t,
  lingua,
}: {
  readonly caso: Encaminhamento;
  readonly tomado: boolean;
  readonly cliente: string;
  readonly cartao: BloqueioDeCartao | undefined;
  readonly aoAssumir: () => void;
  readonly t: Textos;
  readonly lingua: Lingua;
}) {
  const { pedido, pendencia } = rotulos(caso, t, lingua);
  const fatos: Fato[] = [{ k: t.fk.cust, v: nomeDoCliente }];
  // O dispositivo da sessão (2.1c), como no design; os casos de antes não o guardaram.
  if (caso.dispositivo) {
    fatos.push({ k: t.fk.device, v: t.top.device[caso.dispositivo === "cadastrado" ? "reg" : "new"] });
  }
  if (caso.transacao) {
    const tr = caso.transacao;
    fatos.push({
      k: t.fk.txn,
      v: `${tr.comercio ?? "—"} · ${tr.moeda} ${dinheiro(tr.valor, lingua)} · ${diaMes(tr.data)}`,
    });
  }
  if (cartao) {
    const tipo = cartao.tipo === "preventivo" ? t.side.blockedPrev : t.side.blockedFull;
    fatos.push({ k: t.fk.card, v: `•••• ${cartao.ultimos4 ?? "····"} · ${tipo}` });
  }
  const acoes = caso.acoes.map((a) => {
    const chave = ACAO_DO_CASO[a.acao];
    const fora = ACOES_FORA_DO_DESIGN[a.acao];
    const rotulo = chave ? t.act[chave] : fora ? traduzir(fora, lingua) : a.acao;
    const desfeito = a.acao === "desbloquear_cartao" ? DESFEITO.exec(a.resultado) : null;
    const por = desfeito?.[2] ? DESFEITO_POR[desfeito[2]] : undefined;
    return desfeito && por ? `${rotulo} · ${desfeito[1]} · ${traduzir(por, lingua)}` : rotulo;
  });
  const rotulo = tomado ? t.ag.taken : t.ag.take;
  return (
    <article className="cn-caso" aria-label={caso.id}>
      <div className="cn-caso-topo">
        <span className="cn-quadrado" />
        <span className="cn-id">{caso.id}</span>
        <span className="cn-regra">{caso.regra}</span>
        <span>{nomeDoCliente}</span>
        <span className="cn-hora">{hora(caso.criado_em)}</span>
      </div>
      <div className="cn-caso-corpo">
        <div className="cn-campo">
          <span className="cn-mini">{t.ag.req}</span>
          <span className="cn-pedido">{pedido}</span>
        </div>
        <div className="cn-campo">
          <span className="cn-mini">{t.ag.facts}</span>
          {fatos.map((f) => (
            <span key={f.k} className="cn-fato">
              <span>{f.k}</span>
              <span>{f.v}</span>
            </span>
          ))}
        </div>
        <div className="cn-campo">
          <span className="cn-mini">{t.ag.actions}</span>
          {acoes.map((a, i) => (
            <span key={i} className="cn-texto">
              {a} ✓
            </span>
          ))}
        </div>
        <div className="cn-campo">
          <span className="cn-mini">{t.ag.pending}</span>
          <span className="cn-texto">{pendencia}</span>
        </div>
      </div>
      <div className="cn-falas">
        <span className="cn-mini">
          <span>{t.ag.lines}</span>
          <span>{caso.pedido.length}/280</span>
        </span>
        <p>“{caso.pedido}”</p>
      </div>
      <div className="cn-caso-pe">
        <button
          type="button"
          className="cn-assumir"
          aria-pressed={tomado}
          aria-label={`${rotulo} ${caso.id}`}
          disabled={tomado}
          onClick={aoAssumir}
        >
          {rotulo}
        </button>
      </div>
    </article>
  );
}

/** O pedido e a pendência do caso: os do design pelo tipo da regra; sem tipo no design, os daqui; sem
 * nenhum, a regra e as pendências que a API registrou. */
export function rotulos(caso: Encaminhamento, t: Textos, lingua: Lingua) {
  const tipo = TIPO_DA_REGRA[caso.regra];
  if (tipo) return { pedido: t.cases[tipo].req, pendencia: t.cases[tipo].pend };
  const fora = CASOS_FORA_DO_DESIGN[caso.regra];
  if (fora) return { pedido: traduzir(fora.req, lingua), pendencia: traduzir(fora.pend, lingua) };
  return { pedido: caso.regra, pendencia: caso.pendencias.join("; ") };
}
