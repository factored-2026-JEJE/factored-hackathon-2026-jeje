import { useCallback, useEffect, useState } from "react";
import { CLIENTE } from "./abas/cliente/textos";
import {
  type CartaoDoCliente,
  type Dispositivo,
  type Idioma,
  listarPersonas,
  meusCartoes,
  meusPreCasos,
  minhasTransacoes,
  type Persona,
  type PersonaDaDemo,
  type PreCaso,
  SessaoExpirada,
  type Transacao,
} from "./api/cliente";
import type { Lingua, Textos } from "./app/conteudo";
import { useLingua } from "./app/LinguaDoApp";
import { useSessao } from "./app/sessao";
import { traduzir } from "./app/textos";
import { Conversa } from "./Conversa";
import { frasesDoExemplo, quantiaDoCliente } from "./frasesDoCliente";
import "./abas/cliente/cliente.css";

// A situação da transação na API e a chave do design (ui.side.st), com o estilo da etiqueta.
const STATUS: Record<string, keyof Textos["side"]["st"]> = {
  Approved: "aprovada",
  Declined: "recusada",
  Pending: "pendente",
  Reversed: "estornada",
};

// O valor com a moeda de verdade da transação e sempre com centavos (o ICU omite as casas do COP, o
// que arredondaria valores reais): 1,234.56 em inglês e 1.234,56 em espanhol e português, como no design.
const valor = (t: Transacao, lingua: Lingua) =>
  `${t.currency} ${Number(t.amount).toLocaleString(lingua === "en" ? "en-US" : "pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

/** dd/mm, como o cliente escreve e como o design mostra. */
const diaEMes = (iso: string) => {
  const [, mes, dia] = iso.slice(0, 10).split("-");
  return `${dia}/${mes}`;
};

// "Ask about this one" (PRD-006): as pistas da linha como o cliente escreveria (valor, dd/mm e o
// comércio), na frase do design, na língua da conversa. Nunca o identificador da transação: as regras
// procuram pelas pistas (POL-ID-02). Sem a moeda fixa do design ("USD"): o valor é o da transação.
function perguntaSobre(t: Transacao, idioma: Idioma): string {
  const quantia = quantiaDoCliente(t.amount);
  const data = diaEMes(t.transaction_date);
  if (idioma === "es") {
    return `¿Qué pasó con el cobro de ${quantia} del ${data}${t.merchant_name ? ` en ${t.merchant_name}` : ""}?`;
  }
  return `O que houve com a cobrança de ${quantia} do dia ${data}${t.merchant_name ? ` em ${t.merchant_name}` : ""}?`;
}

/** O acesso do design (a aba do cliente sem sessão): a persona, o dispositivo e o "Entrar como". */
function AcessoDoCliente({ aviso }: { aviso: string | null }) {
  const { lingua, t } = useLingua();
  const { entrar } = useSessao();
  const [personas, setPersonas] = useState<PersonaDaDemo[] | null>(null);
  const [escolhida, setEscolhida] = useState<string | null>(null);
  // Como no design, o dispositivo vem marcado em "cadastrado" (o bloqueio completo).
  const [dispositivo, setDispositivo] = useState<Dispositivo>("cadastrado");
  useEffect(() => {
    listarPersonas()
      .then(setPersonas)
      .catch(() => setPersonas([]));
  }, []);
  const persona = personas?.find((p) => p.customer_id === escolhida) ?? personas?.[0];
  const dispositivos: [Dispositivo, string, string][] = [
    ["cadastrado", t.acc.devReg, t.acc.devRegSub],
    ["novo", t.acc.devNew, t.acc.devNewSub],
  ];
  return (
    <div className="acc">
      <div className="acc-texto">
        <p className="acc-kicker">
          <span className="app-quadrado" />
          {t.acc.kicker}
        </p>
        <h1>{t.acc.title}</h1>
        <p className="acc-corpo">{t.acc.body}</p>
        <p className="acc-nota">{t.acc.note}</p>
      </div>
      <div className="acc-escolha">
        {aviso && <p role="alert">{traduzir(CLIENTE.expirou, lingua)}</p>}
        <p className="acc-passo">{t.acc.s1}</p>
        {personas === null && <p role="status">{traduzir(CLIENTE.carregandoPersonas, lingua)}</p>}
        {personas?.length === 0 && <p>{traduzir(CLIENTE.semPersonas, lingua)}</p>}
        <div className="acc-personas">
          {personas?.map((p) => {
            const frase = p.exemplo ? frasesDoExemplo(p.exemplo)[lingua === "pt" ? 1 : 0] : null;
            return (
              <button
                key={p.customer_id}
                type="button"
                aria-pressed={p === persona}
                className="acc-persona"
                onClick={() => setEscolhida(p.customer_id)}
              >
                <span className="acc-persona-cab">
                  <span>{p.customer_id}</span>
                </span>
                <span className="acc-persona-corpo">
                  <span className="acc-persona-nome">{p.nome}</span>
                  <span className="acc-numeros">
                    <span>
                      <span className="acc-numero">{p.cartoes_bloqueaveis}</span>
                      <span className="acc-rotulo">{t.acc.stats.cards}</span>
                    </span>
                    <span>
                      <span className="acc-numero">{p.transacoes_recusadas}</span>
                      <span className="acc-rotulo">{t.acc.stats.declines}</span>
                    </span>
                    <span>
                      <span className="acc-numero">{p.pre_casos_recentes}</span>
                      <span className="acc-rotulo">{t.acc.stats.recent}</span>
                    </span>
                    <span>
                      <span className="acc-numero">{p.contestaveis}</span>
                      <span className="acc-rotulo">{t.acc.stats.disputable}</span>
                    </span>
                  </span>
                  {frase && <span className="acc-frase">“{frase}”</span>}
                </span>
              </button>
            );
          })}
        </div>
        <p className="acc-passo">{t.acc.s2}</p>
        <div className="acc-dispositivos">
          {dispositivos.map(([d, rotulo, sub]) => (
            <button key={d} type="button" aria-pressed={dispositivo === d} className="acc-dispositivo" onClick={() => setDispositivo(d)}>
              <span className="acc-marca" />
              <span>
                <span className="acc-dispositivo-nome">{rotulo}</span>
                <span className="acc-dispositivo-sub">{sub}</span>
              </span>
            </button>
          ))}
        </div>
        {persona && (
          <button type="button" className="acc-entrar" onClick={() => void entrar(persona, dispositivo)}>
            {t.acc.enter} {persona.nome} →
          </button>
        )}
      </div>
    </div>
  );
}

/** As transações do cliente, com a situação, o pré-caso e o "Ask about this one". */
function MinhasTransacoes({
  token,
  aoExpirar,
  idioma,
  preCasos,
  aoPerguntar,
}: {
  token: string;
  aoExpirar: () => void;
  idioma: Idioma;
  preCasos: PreCaso[];
  aoPerguntar: (pergunta: string) => void;
}) {
  const { lingua, t } = useLingua();
  const [transacoes, setTransacoes] = useState<Transacao[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let ativo = true;
    minhasTransacoes(token)
      .then((lista) => ativo && setTransacoes(lista))
      .catch((e: unknown) => {
        if (!ativo) return;
        if (e instanceof SessaoExpirada) aoExpirar();
        else setErro(String(e));
      });
    return () => {
      ativo = false;
    };
  }, [token, aoExpirar]);

  return (
    <section aria-label={t.side.txns} className="lado-bloco">
      <div className="lado-cab">
        <h2>{t.side.txns}</h2>
        <p>{t.side.askNote}</p>
      </div>
      {erro && <p role="alert">{traduzir(CLIENTE.transacoesIndisponiveis, lingua)} ({erro})</p>}
      {!erro && transacoes === null && <p role="status">{traduzir(CLIENTE.carregandoTransacoes, lingua)}</p>}
      {transacoes?.length === 0 && <p>{traduzir(CLIENTE.semTransacoes, lingua)}</p>}
      <ul className="lado-lista">
        {transacoes?.map((tr) => {
          const st = STATUS[tr.transaction_status];
          const pc = preCasos.find((p) => p.transaction_id === tr.transaction_id);
          return (
            <li key={tr.transaction_id} className="trx">
              <span className="trx-data">{diaEMes(tr.transaction_date)}</span>
              <span className="trx-comercio">{tr.merchant_name ?? tr.transaction_type ?? tr.transaction_id}</span>
              <span className="trx-valor">{valor(tr, lingua)}</span>
              <span />
              <span className="trx-situacao">
                <span className={"trx-st trx-" + (st ?? "outra")}>
                  {(st ? t.side.st[st] : tr.transaction_status) + (tr.response_code ? " · " + tr.response_code : "")}
                </span>
                {pc && <span className="trx-pc">{pc.protocolo}</span>}
              </span>
              <button type="button" className="trx-perguntar" onClick={() => aoPerguntar(perguntaSobre(tr, idioma))}>
                {t.side.ask} →
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Os pedidos de revisão (pré-casos) do cliente, com o comércio, o valor e o dia da transação. */
function MeusPedidos({ preCasos, transacoes }: { preCasos: PreCaso[]; transacoes: Transacao[] }) {
  const { lingua, t } = useLingua();
  return (
    <section aria-label={t.side.reqs} className="lado-bloco">
      <div className="lado-cab">
        <h2>{t.side.reqs}</h2>
      </div>
      {preCasos.length === 0 && <p className="lado-vazio">{t.side.reqNone}</p>}
      <ul className="lado-lista">
        {preCasos.map((p) => {
          const tr = transacoes.find((x) => x.transaction_id === p.transaction_id);
          const desc = tr ? `${tr.merchant_name ?? tr.transaction_type ?? ""} · ${valor(tr, lingua)} · ${diaEMes(tr.transaction_date)}` : p.transaction_id;
          return (
            <li key={p.protocolo} className="pedido">
              <span className="pedido-pc">{p.protocolo}</span>
              <span className="pedido-desc">{desc}</span>
              <span className="pedido-st">{t.side.inReview}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const NOVAS_TENTATIVAS = 3;
const ESPERA_DA_NOVA_TENTATIVA_MS = 1500;

/** Os cartões do cliente (GET /minhas/cartoes, 2.1 do fechamento): ativo, ou bloqueado por aqui
 * (completo ou preventivo), com a nota do design. Relidos a cada efeito da conversa (um bloqueio, um
 * desbloqueio ou um relato de fraude). */
function MeusCartoes({ token, versao, aoExpirar }: { token: string; versao: number; aoExpirar: () => void }) {
  const { lingua, t } = useLingua();
  const [cartoes, setCartoes] = useState<CartaoDoCliente[] | null>(null);
  // Uma falha da leitura não é "sem cartões": o painel avisa e tenta de novo algumas vezes, como o resto
  // da aba relê a cada efeito da conversa.
  const [falhou, setFalhou] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    let ativo = true;
    let espera: ReturnType<typeof setTimeout> | undefined;
    meusCartoes(token)
      .then((lista) => {
        if (!ativo) return;
        setCartoes(lista);
        setFalhou(false);
      })
      .catch((e: unknown) => {
        if (!ativo) return;
        if (e instanceof SessaoExpirada) return aoExpirar();
        setFalhou(true);
        if (tentativa < NOVAS_TENTATIVAS) espera = setTimeout(() => setTentativa((n) => n + 1), ESPERA_DA_NOVA_TENTATIVA_MS);
      });
    return () => {
      ativo = false;
      clearTimeout(espera);
    };
  }, [token, versao, tentativa, aoExpirar]);
  return (
    <section aria-label={t.side.cards} className="lado-bloco">
      <div className="lado-cab cartoes-cab">
        <h2>{t.side.cards}</h2>
      </div>
      {falhou && cartoes === null && <p role="alert">{traduzir(CLIENTE.cartoesIndisponiveis, lingua)}</p>}
      {cartoes?.length === 0 && <p className="lado-vazio">{traduzir(CLIENTE.semCartoes, lingua)}</p>}
      <ul className="lado-lista">
        {cartoes?.map((c) => {
          const preventivo = c.bloqueio?.tipo === "preventivo";
          // O cartão encerrado na base (product_status) não é ativo nem se bloqueia por aqui (ACH-165).
          const encerrado = !c.bloqueio && c.status !== "Active";
          const situacao = c.bloqueio ? (preventivo ? "preventivo" : "completo") : encerrado ? "encerrado" : "ativo";
          return (
            <li key={c.product_id} className="cli-cartao" data-situacao={situacao}>
              <span className="cartao-final">•••• {c.ultimos4 ?? "—"}</span>
              <span className="cartao-produto">{c.produto}</span>
              <span className="cartao-st">{c.bloqueio ? (preventivo ? t.side.blockedPrev : t.side.blockedFull) : encerrado ? t.side.closed : t.side.active}</span>
              {c.bloqueio && <span className="cartao-nota">{preventivo ? t.side.prevNote : t.side.undoNote}</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** A aba do cliente do design: sem sessão, o acesso; com ela, a conversa ao lado do painel. Abaixo de
 * 900 px, o painel vira abas internas (Chat, Transações, Pedidos e cartões). `aoMudar` avisa que a
 * conversa criou algo (pré-caso, encaminhamento) para a fila e as métricas se atualizarem. `pergunta`
 * é a frase que vai para a conversa como mensagem do cliente: a do "Ask about this one" ou a do "Try in
 * ES/PT" das outras abas (`experimentar` do App). */
export function Atendimento({
  versao = 0,
  aoMudar = () => {},
  pergunta = null,
  aoPerguntar,
  aoPerguntado = () => {},
}: {
  /** A versão do app: muda a cada efeito de outra área (o desbloqueio pelo console do atendente, ACH-164). */
  versao?: number;
  aoMudar?: () => void;
  pergunta?: string | null;
  aoPerguntar?: (pergunta: string) => void;
  aoPerguntado?: () => void;
}) {
  const { lingua, t } = useLingua();
  const { sessao, aviso, expirou } = useSessao();
  const [versaoPreCasos, setVersaoPreCasos] = useState(0);
  // Os cartões mudam também fora desta aba: pelo console do atendente nesta janela (a versão do app) ou
  // noutra janela (o console aberto noutra aba do navegador): a volta à página relê (ACH-164).
  const [voltas, setVoltas] = useState(0);
  useEffect(() => {
    const voltou = () => {
      if (document.visibilityState === "visible") setVoltas((n) => n + 1);
    };
    window.addEventListener("focus", voltou);
    document.addEventListener("visibilitychange", voltou);
    return () => {
      window.removeEventListener("focus", voltou);
      document.removeEventListener("visibilitychange", voltou);
    };
  }, []);
  const [painel, setPainel] = useState(0);
  // "Ask about this one": a frase vai na língua da conversa aberta (ou na da interface).
  const [idiomaDaConversa, setIdiomaDaConversa] = useState<Idioma | null>(null);
  const [perguntaLocal, setPerguntaLocal] = useState<string | null>(null);
  const perguntar = aoPerguntar ?? setPerguntaLocal;
  const perguntaAtual = aoPerguntar ? pergunta : perguntaLocal;
  const perguntada = useCallback(() => {
    setPerguntaLocal(null);
    aoPerguntado();
  }, [aoPerguntado]);
  // O pré-caso nasce na conversa: cada registro atualiza a lista, a fila e as métricas.
  const conversaMudou = useCallback(() => {
    setVersaoPreCasos((v) => v + 1);
    aoMudar();
  }, [aoMudar]);
  const [preCasos, setPreCasos] = useState<PreCaso[]>([]);
  const [transacoes, setTransacoes] = useState<Transacao[]>([]);
  const [exemplo, setExemplo] = useState<readonly [string, string] | null>(null);
  const token = sessao?.token;
  const clienteId = sessao?.cliente.customer_id;
  useEffect(() => {
    if (!token) return;
    let ativo = true;
    meusPreCasos(token)
      .then((lista) => ativo && setPreCasos(lista))
      .catch(() => ativo && setPreCasos([]));
    return () => {
      ativo = false;
    };
  }, [token, versaoPreCasos]);
  useEffect(() => {
    if (!token) return;
    let ativo = true;
    minhasTransacoes(token)
      .then((lista) => ativo && setTransacoes(lista))
      .catch(() => ativo && setTransacoes([]));
    return () => {
      ativo = false;
    };
  }, [token]);
  // O exemplo do estado vazio da conversa: a compra contestável da própria persona.
  useEffect(() => {
    if (!clienteId) return;
    let ativo = true;
    listarPersonas()
      .then((ps) => {
        const p = ps.find((x) => x.customer_id === clienteId);
        if (ativo) setExemplo(p?.exemplo ? frasesDoExemplo(p.exemplo) : null);
      })
      .catch(() => ativo && setExemplo(null));
    return () => {
      ativo = false;
    };
  }, [clienteId]);

  if (!sessao) return <AcessoDoCliente aviso={aviso} />;
  const idioma: Idioma = idiomaDaConversa ?? (lingua === "pt" ? "pt" : "es");
  return (
    <div className="cli" data-painel={painel}>
      <div role="tablist" aria-label={t.conv.title} className="cli-paineis">
        {t.side.panels.map((rotulo, i) => (
          <button key={rotulo} type="button" role="tab" aria-selected={painel === i} onClick={() => setPainel(i)}>
            {rotulo}
          </button>
        ))}
      </div>
      <div className="cli-corpo">
        <div className="cli-conversa">
          <Conversa
            token={sessao.token}
            aoExpirar={expirou}
            aoMudar={conversaMudou}
            aoIdioma={setIdiomaDaConversa}
            pergunta={perguntaAtual}
            aoPerguntado={perguntada}
            exemplo={exemplo}
          />
        </div>
        <aside className="cli-lado">
          <div className="cli-transacoes">
            <MinhasTransacoes
              token={sessao.token}
              aoExpirar={expirou}
              idioma={idioma}
              preCasos={preCasos}
              aoPerguntar={(frase) => {
                setPainel(0);
                perguntar(frase);
              }}
            />
          </div>
          <div className="cli-pedidos">
            <MeusPedidos preCasos={preCasos} transacoes={transacoes} />
            <MeusCartoes token={sessao.token} versao={versaoPreCasos + versao + voltas} aoExpirar={expirou} />
          </div>
        </aside>
      </div>
    </div>
  );
}

export type { Persona };
