import { useCallback, useEffect, useState } from "react";
import {
  type Dispositivo,
  type Idioma,
  listarPersonas,
  meusPreCasos,
  minhasTransacoes,
  type Persona,
  type PersonaDaDemo,
  type PreCaso,
  SessaoExpirada,
  type Transacao,
} from "./api/cliente";
import { useSessao } from "./app/sessao";
import { Conversa } from "./Conversa";
import { frasesDoExemplo, quantiaDoCliente } from "./frasesDoCliente";

const STATUS: Record<string, string> = {
  Approved: "Aprovada",
  Declined: "Recusada",
  Pending: "Pendente",
  Reversed: "Estornada",
};

// Sempre com centavos: o ICU omite as casas do COP, o que arredondaria valores reais.
const valor = (t: Transacao) =>
  Number(t.amount).toLocaleString("pt-BR", {
    style: "currency",
    currency: t.currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

const quando = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });

const DISPOSITIVOS: [Dispositivo, string][] = [
  ["novo", "Novo"],
  ["cadastrado", "Cadastrado"],
];

function MeusPreCasos({ token, versao }: { token: string; versao: number }) {
  const [preCasos, setPreCasos] = useState<PreCaso[]>([]);
  useEffect(() => {
    let ativo = true;
    meusPreCasos(token)
      .then((lista) => ativo && setPreCasos(lista))
      .catch(() => ativo && setPreCasos([]));
    return () => {
      ativo = false;
    };
  }, [token, versao]);
  if (preCasos.length === 0) return null;
  return (
    <section aria-label="Meus pré-casos">
      <h3>Meus pré-casos</h3>
      <ul>
        {preCasos.map((p) => (
          <li key={p.protocolo}>
            {p.protocolo} — transação {p.transaction_id} ({p.estado})
          </li>
        ))}
      </ul>
    </section>
  );
}

// "Perguntar sobre esta" (PRD-006): as pistas da linha como o cliente escreveria (valor, data
// dd/mm/aaaa e o comércio), na língua da conversa aberta. Nunca o identificador da transação: as
// regras procuram pelas pistas (POL-ID-02).
function perguntaSobre(t: Transacao, idioma: Idioma): string {
  const quantia = quantiaDoCliente(t.amount);
  const [ano, mes, dia] = t.transaction_date.slice(0, 10).split("-");
  const data = `${dia}/${mes}/${ano}`;
  if (idioma === "es") {
    return `¿Qué pasó con la transacción de ${quantia} del ${data}${t.merchant_name ? ` en ${t.merchant_name}` : ""}?`;
  }
  return `O que aconteceu com a transação de ${quantia} do dia ${data}${t.merchant_name ? ` na ${t.merchant_name}` : ""}?`;
}

function MinhasTransacoes({
  token,
  aoExpirar,
  idioma,
  aoPerguntar,
}: {
  token: string;
  aoExpirar: () => void;
  idioma: Idioma | null;
  aoPerguntar: (pergunta: string) => void;
}) {
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

  if (erro) return <p role="alert">Transações indisponíveis ({erro})</p>;
  if (transacoes === null) return <p role="status">Carregando transações…</p>;
  if (transacoes.length === 0) return <p>Nenhuma transação encontrada.</p>;
  return (
    <table aria-label="Minhas transações">
      <thead>
        <tr>
          <th scope="col">Data</th>
          <th scope="col">Descrição</th>
          <th scope="col">Valor</th>
          <th scope="col">Situação</th>
          <th scope="col">Conversa</th>
        </tr>
      </thead>
      <tbody>
        {transacoes.map((t) => (
          <tr key={t.transaction_id}>
            <td>{quando(t.transaction_date)}</td>
            <th scope="row">{t.merchant_name ?? t.transaction_type ?? t.transaction_id}</th>
            <td>{valor(t)}</td>
            <td>{STATUS[t.transaction_status] ?? t.transaction_status}</td>
            <td>
              {idioma && (
                <button type="button" className="secundario" onClick={() => aoPerguntar(perguntaSobre(t, idioma))}>
                  Perguntar sobre esta
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Acesso de teste por persona e área do cliente (a identidade vem só da sessão, que é do app inteiro).
 * `aoMudar` avisa que a conversa criou algo (pré-caso, encaminhamento) para a fila e as métricas se
 * atualizarem. `pergunta` é a frase que vai para a conversa como mensagem do cliente: a do "Perguntar
 * sobre esta" ou a do "Try in ES/PT" das outras abas (`experimentar` do App). */
export function Atendimento({
  aoMudar = () => {},
  pergunta = null,
  aoPerguntar,
  aoPerguntado = () => {},
}: {
  aoMudar?: () => void;
  pergunta?: string | null;
  aoPerguntar?: (pergunta: string) => void;
  aoPerguntado?: () => void;
}) {
  const { sessao, aviso, entrar: entrarNaSessao, sair, expirou } = useSessao();
  const [personas, setPersonas] = useState<PersonaDaDemo[] | null>(null);
  const [versaoPreCasos, setVersaoPreCasos] = useState(0);
  // Sem escolha, "novo": o lado conservador (bloqueio preventivo e atendente).
  const [dispositivo, setDispositivo] = useState<Dispositivo>("novo");
  // "Perguntar sobre esta": a tabela monta a pergunta na língua da conversa aberta, e a conversa a
  // envia como mensagem do cliente.
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

  useEffect(() => {
    listarPersonas()
      .then(setPersonas)
      .catch(() => setPersonas([]));
  }, []);

  async function entrar(persona: Persona) {
    await entrarNaSessao(persona, dispositivo);
  }

  if (sessao) {
    return (
      <section aria-label="Atendimento" className="atendimento">
        <div className="cabecalho">
          <h2>Olá, {sessao.cliente.nome}</h2>
          <button type="button" className="secundario" onClick={() => sair()}>
            Sair
          </button>
        </div>
        <p className="nota">Dispositivo (simulação): {sessao.dispositivo}</p>
        <Conversa
          token={sessao.token}
          aoExpirar={expirou}
          aoMudar={conversaMudou}
          aoIdioma={setIdiomaDaConversa}
          pergunta={perguntaAtual}
          aoPerguntado={perguntada}
        />
        <MinhasTransacoes
          token={sessao.token}
          aoExpirar={expirou}
          idioma={idiomaDaConversa}
          aoPerguntar={perguntar}
        />
        <MeusPreCasos token={sessao.token} versao={versaoPreCasos} />
      </section>
    );
  }
  return (
    <section aria-label="Atendimento" className="atendimento cartao">
      <h2>Acesso de teste</h2>
      <p>Escolha um cliente de demonstração. Dados sintéticos do desafio; não é um login real.</p>
      {aviso && <p role="alert">{aviso}</p>}
      <div role="radiogroup" aria-label="Dispositivo (simulação)" className="dispositivo">
        <p>Dispositivo (simulação):</p>
        {DISPOSITIVOS.map(([valor, rotulo]) => (
          <label key={valor}>
            <input
              type="radio"
              name="dispositivo"
              value={valor}
              checked={dispositivo === valor}
              onChange={() => setDispositivo(valor)}
            />{" "}
            {rotulo}
          </label>
        ))}
        <p className="nota">
          Não há aparelho real: o escolhido decide o bloqueio de cartão (cadastrado: completo; novo: preventivo, com
          atendente).
        </p>
      </div>
      {personas === null && <p role="status">Carregando clientes de demonstração…</p>}
      <ul>
        {personas?.map((persona) => (
          <li key={persona.customer_id}>
            <button type="button" onClick={() => void entrar(persona)}>
              Entrar como {persona.nome}
            </button>{" "}
            {/* Para escolher o caminho da demonstração (PRD-009): fraude com vários cartões, recusas e
                reincidência. */}
            <span className="nota">
              cartões para bloquear: {persona.cartoes_bloqueaveis} · recusas: {persona.transacoes_recusadas} · pré-casos
              recentes: {persona.pre_casos_recentes} · contestáveis: {persona.contestaveis}
            </span>
            {persona.exemplo && (
              <span className="nota exemplo">
                {" "}
                para contestar: <q>{frasesDoExemplo(persona.exemplo)[0]}</q> /{" "}
                <q>{frasesDoExemplo(persona.exemplo)[1]}</q>
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
