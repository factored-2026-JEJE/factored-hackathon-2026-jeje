import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { abrirSessao, type Dispositivo, type Persona, sessaoAtual } from "../api/cliente";

// A sessão de teste do app inteiro (DEV-032b): a barra do topo mostra quem entrou e sai por ela; a aba do
// cliente entra por uma persona; o "Try in ES/PT" do guia e do atendente entra sozinho, se preciso. A
// lógica é a de antes (Atendimento.tsx), só levada para cima: a identidade vem só da sessão da API.
const CHAVE_SESSAO = "jeje.sessao";

export type Sessao = { token: string; cliente: Persona; dispositivo: Dispositivo };

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

interface SessaoDoApp {
  readonly sessao: Sessao | null;
  readonly aviso: string | null;
  readonly entrar: (persona: Persona, dispositivo: Dispositivo) => Promise<Sessao>;
  readonly sair: (mensagem?: string | null) => void;
  readonly expirou: () => void;
}

const Contexto = createContext<SessaoDoApp | null>(null);

export function SessaoProvider({ children }: { children: ReactNode }) {
  const [sessao, setSessao] = useState<Sessao | null>(null);
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
        .then((atual) => setSessao({ token, cliente: atual, dispositivo: atual.dispositivo }))
        .catch(() => sair("Sua sessão expirou. Entre de novo."));
    }
  }, [sair]);

  const entrar = useCallback(async (persona: Persona, dispositivo: Dispositivo) => {
    const aberta = await abrirSessao(persona.customer_id, dispositivo);
    guardarSessao(aberta.token);
    setAviso(null);
    const nova = { token: aberta.token, cliente: aberta.cliente, dispositivo: aberta.dispositivo };
    setSessao(nova);
    return nova;
  }, []);

  const valor = useMemo(() => ({ sessao, aviso, entrar, sair, expirou }), [sessao, aviso, entrar, sair, expirou]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useSessao(): SessaoDoApp {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useSessao fora do SessaoProvider");
  return valor;
}
