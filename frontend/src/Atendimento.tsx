import { useCallback, useEffect, useState } from "react";
import {
  abrirSessao,
  listarPersonas,
  minhasTransacoes,
  type Persona,
  SessaoExpirada,
  sessaoAtual,
  type Transacao,
} from "./api/cliente";

const CHAVE_SESSAO = "jeje.sessao";

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

type Sessao = { token: string; cliente: Persona };

function lerSessaoGuardada(): string | null {
  try {
    return sessionStorage.getItem(CHAVE_SESSAO);
  } catch {
    return null;
  }
}

function guardarSessao(token: string | null) {
  try {
    if (token) sessionStorage.setItem(CHAVE_SESSAO, token);
    else sessionStorage.removeItem(CHAVE_SESSAO);
  } catch {
    // Sem armazenamento: a sessão vale só enquanto a página estiver aberta.
  }
}

function MinhasTransacoes({ token, aoExpirar }: { token: string; aoExpirar: () => void }) {
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
        </tr>
      </thead>
      <tbody>
        {transacoes.map((t) => (
          <tr key={t.transaction_id}>
            <td>{quando(t.transaction_date)}</td>
            <th scope="row">{t.merchant_name ?? t.transaction_type ?? t.transaction_id}</th>
            <td>{valor(t)}</td>
            <td>{STATUS[t.transaction_status] ?? t.transaction_status}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Acesso de teste por persona e área do cliente (a identidade vem só da sessão). */
export function Atendimento() {
  const [sessao, setSessao] = useState<Sessao | null>(null);
  const [personas, setPersonas] = useState<Persona[] | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const sair = useCallback((mensagem: string | null = null) => {
    guardarSessao(null);
    setSessao(null);
    setAviso(mensagem);
  }, []);
  const expirou = useCallback(() => sair("Sua sessão expirou. Entre de novo."), [sair]);

  useEffect(() => {
    const token = lerSessaoGuardada();
    if (token) {
      sessaoAtual(token)
        .then((cliente) => setSessao({ token, cliente }))
        .catch(() => sair("Sua sessão expirou. Entre de novo."));
    }
    listarPersonas()
      .then(setPersonas)
      .catch(() => setPersonas([]));
  }, [sair]);

  async function entrar(persona: Persona) {
    const aberta = await abrirSessao(persona.customer_id);
    guardarSessao(aberta.token);
    setAviso(null);
    setSessao({ token: aberta.token, cliente: aberta.cliente });
  }

  if (sessao) {
    return (
      <section aria-label="Atendimento">
        <h2>Olá, {sessao.cliente.nome}</h2>
        <button type="button" onClick={() => sair()}>
          Sair
        </button>
        <MinhasTransacoes token={sessao.token} aoExpirar={expirou} />
      </section>
    );
  }
  return (
    <section aria-label="Atendimento">
      <h2>Acesso de teste</h2>
      <p>Escolha um cliente de demonstração. Dados sintéticos do desafio; não é um login real.</p>
      {aviso && <p role="alert">{aviso}</p>}
      {personas === null && <p role="status">Carregando clientes de demonstração…</p>}
      <ul>
        {personas?.map((persona) => (
          <li key={persona.customer_id}>
            <button type="button" onClick={() => void entrar(persona)}>
              Entrar como {persona.nome}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
