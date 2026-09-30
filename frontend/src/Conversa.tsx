import { useEffect, useRef, useState } from "react";
import { AvaliarConversa } from "./AvaliarConversa";
import {
  abrirConversa,
  enviarMensagem,
  historicoDaConversa,
  type Idioma,
  NaoRegistrado,
  type ResultadoDoTurno,
  SessaoExpirada,
} from "./api/cliente";

const CHAVE_CONVERSA = "jeje.conversa";

// Respostas rápidas na língua da conversa: enviam o mesmo texto que o cliente digitaria, e quem
// decide o que ele significa é a API (a tela não confirma nada sozinha).
const RESPOSTAS: Record<Idioma, { sim: string; nao: string; confirmar: string }> = {
  es: { sim: "Sí", nao: "No", confirmar: "Sí, confirmo" },
  pt: { sim: "Sim", nao: "Não", confirmar: "Sim, confirmo" },
};

type Fala = { id: number; autor: "cliente" | "assistente"; texto: string };

type Situacao = {
  idioma: Idioma;
  estado: string;
  opcoes: ResultadoDoTurno["opcoes"];
  protocolo: string | null;
  atendimento: string | null;
};

function lerGuardada(): string | null {
  try {
    return sessionStorage.getItem(CHAVE_CONVERSA);
  } catch {
    return null;
  }
}

function guardar(conversaId: string | null) {
  try {
    if (conversaId) sessionStorage.setItem(CHAVE_CONVERSA, conversaId);
    else sessionStorage.removeItem(CHAVE_CONVERSA);
  } catch {
    // Sem armazenamento: a conversa vale enquanto a página estiver aberta.
  }
}

/** Conversa com o assistente (sem modelo): cada resposta, opção e protocolo vêm da API. */
// Efeitos que o console do atendente precisa ver: pré-caso, encaminhamento e bloqueio.
const AVISAM_O_CONSOLE = ["registrar_pre_caso", "humano", "bloquear_cartao"];

export function Conversa({
  token,
  aoExpirar,
  aoMudar,
}: {
  token: string;
  aoExpirar: () => void;
  aoMudar: () => void;
}) {
  const [conversaId, setConversaId] = useState<string | null>(null);
  const [falas, setFalas] = useState<Fala[]>([]);
  const [situacao, setSituacao] = useState<Situacao | null>(null);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<{ mensagem: string; detalhe: string } | null>(null);
  const [carregando, setCarregando] = useState(true);
  const proximo = useRef(0);
  const fala = (autor: Fala["autor"], conteudo: string): Fala => ({ id: proximo.current++, autor, texto: conteudo });

  // Recarregar a página reabre a conversa desta aba pelo histórico: nada é reenviado.
  useEffect(() => {
    let ativo = true;
    const guardada = lerGuardada();
    if (!guardada) {
      setCarregando(false);
      return;
    }
    historicoDaConversa(token, guardada)
      .then((historico) => {
        if (!ativo) return;
        if (historico === null) {
          guardar(null);
          return;
        }
        setConversaId(historico.conversa_id);
        setFalas(
          historico.turnos.flatMap((t) => [
            { id: proximo.current++, autor: "cliente" as const, texto: t.mensagem },
            { id: proximo.current++, autor: "assistente" as const, texto: t.resposta },
          ]),
        );
        setSituacao({ idioma: historico.idioma, estado: historico.estado, opcoes: [], protocolo: null, atendimento: null });
      })
      .catch((e: unknown) => {
        if (ativo && e instanceof SessaoExpirada) aoExpirar();
      })
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [token, aoExpirar]);

  async function iniciar(idioma: Idioma) {
    try {
      const aberta = await abrirConversa(token, idioma);
      guardar(aberta.conversa_id);
      setConversaId(aberta.conversa_id);
      setFalas([fala("assistente", aberta.resposta)]);
      setSituacao({ idioma: aberta.idioma, estado: aberta.estado, opcoes: [], protocolo: null, atendimento: null });
    } catch (e) {
      if (e instanceof SessaoExpirada) aoExpirar();
      else setFalha({ mensagem: "", detalhe: "Não foi possível abrir a conversa. Tente de novo." });
    }
  }

  async function enviar(mensagem: string) {
    const limpa = mensagem.trim();
    if (!conversaId || enviando || limpa === "") return;
    setEnviando(true);
    setFalha(null);
    try {
      const turno = await enviarMensagem(token, conversaId, limpa);
      setFalas((atuais) => [...atuais, fala("cliente", limpa), fala("assistente", turno.resposta)]);
      setSituacao({
        idioma: turno.idioma,
        estado: turno.estado,
        opcoes: turno.opcoes,
        // Só um pré-caso gravado agora e relido pela API vira "recebido".
        protocolo: turno.acao === "registrar_pre_caso" ? turno.protocolo : null,
        atendimento: turno.atendimento,
      });
      setTexto("");
      if (AVISAM_O_CONSOLE.includes(turno.acao)) aoMudar();
    } catch (e) {
      if (e instanceof SessaoExpirada) aoExpirar();
      else if (e instanceof NaoRegistrado) setFalha({ mensagem: limpa, detalhe: e.message });
      else if (!(await jaProcessada(limpa)))
        setFalha({ mensagem: limpa, detalhe: "Sem resposta do servidor. Reenviar é seguro: a conversa não repete efeitos." });
    } finally {
      setEnviando(false);
    }
  }

  // Resposta perdida (ACH-105): a API pode ter feito o turno sem a resposta chegar. Antes de
  // afirmar qualquer coisa, a tela relê a conversa; se a mensagem já foi processada, mostra o que
  // ficou registrado (com o protocolo, se houve pré-caso) e avisa quem relê pré-casos e fila.
  async function jaProcessada(limpa: string): Promise<boolean> {
    if (!conversaId) return false;
    try {
      const historico = await historicoDaConversa(token, conversaId);
      const ultimo = historico?.turnos.at(-1);
      const mostrados = falas.filter((f) => f.autor === "cliente").length;
      if (!historico || !ultimo || historico.turnos.length <= mostrados || ultimo.mensagem !== limpa) return false;
      setFalas((atuais) => [...atuais, fala("cliente", ultimo.mensagem), fala("assistente", ultimo.resposta)]);
      setSituacao({ idioma: historico.idioma, estado: historico.estado, opcoes: [], protocolo: null, atendimento: null });
      setTexto("");
      setFalha(null);
      aoMudar();
      return true;
    } catch {
      return false;
    }
  }

  // Reenviar também relê antes: a primeira conferência pode ter falhado junto com a rede.
  async function reenviar(mensagem: string) {
    setEnviando(true);
    const processada = await jaProcessada(mensagem);
    setEnviando(false);
    if (!processada) await enviar(mensagem);
  }

  function novaConversa() {
    guardar(null);
    setConversaId(null);
    setSituacao(null);
    setFalas([]);
    setFalha(null);
  }

  if (carregando) return <p role="status">Carregando conversa…</p>;

  if (!conversaId || !situacao) {
    return (
      <section aria-label="Conversa" className="cartao conversa">
        <h3>Conversar com o assistente</h3>
        <p>Consulta de transações e pedido de revisão de cobrança, em espanhol ou português.</p>
        <div className="acoes">
          <button type="button" onClick={() => void iniciar("es")}>
            Conversar em español
          </button>
          <button type="button" onClick={() => void iniciar("pt")}>
            Conversar em português
          </button>
        </div>
        {falha && <p role="alert">{falha.detalhe}</p>}
      </section>
    );
  }

  const rapidas = RESPOSTAS[situacao.idioma];
  // A recarga dos dados encerrou a conversa: nada do contexto vale mais, só uma nova conversa.
  const encerrada = situacao.estado === "encerrada";
  return (
    <section aria-label="Conversa" className="cartao conversa">
      <div className="cabecalho">
        <h3>Conversa</h3>
        <button type="button" className="secundario" onClick={novaConversa}>
          Nova conversa
        </button>
      </div>
      <div role="log" aria-label="Mensagens" className="mensagens">
        <ol>
          {falas.map((f) => (
            <li key={f.id} className={`fala fala-${f.autor}`}>
              <span className="autor">{f.autor === "cliente" ? "Você" : "Assistente"}</span>
              <p>{f.texto}</p>
            </li>
          ))}
        </ol>
      </div>
      {enviando && <p role="status">Enviando…</p>}
      {situacao.protocolo && (
        <p role="status" className="sucesso">
          Pré-caso recebido: protocolo {situacao.protocolo}
        </p>
      )}
      {situacao.estado === "com_humano" && (
        <p role="status" className="aviso">
          Com atendimento humano{situacao.atendimento ? ` (${situacao.atendimento})` : ""}.
        </p>
      )}
      {encerrada && (
        <p role="status" className="aviso">
          Conversa encerrada: os dados foram atualizados. Abra uma nova conversa.
        </p>
      )}
      {situacao.opcoes.length > 0 && (
        <div role="group" aria-label="Opções" className="acoes coluna">
          {situacao.opcoes.map((o) => (
            <button key={o.numero} type="button" disabled={enviando} onClick={() => void enviar(String(o.numero))}>
              {o.numero}. {o.descricao}
            </button>
          ))}
        </div>
      )}
      {situacao.estado === "confirmando" && (
        <div role="group" aria-label="Confirmação" className="acoes">
          <button type="button" disabled={enviando} onClick={() => void enviar(rapidas.confirmar)}>
            {rapidas.confirmar}
          </button>
          <button type="button" className="secundario" disabled={enviando} onClick={() => void enviar(rapidas.nao)}>
            {rapidas.nao}
          </button>
        </div>
      )}
      {situacao.estado === "oferecendo_humano" && (
        <div role="group" aria-label="Atendente" className="acoes">
          <button type="button" disabled={enviando} onClick={() => void enviar(rapidas.sim)}>
            {rapidas.sim}
          </button>
          <button type="button" className="secundario" disabled={enviando} onClick={() => void enviar(rapidas.nao)}>
            {rapidas.nao}
          </button>
        </div>
      )}
      {falha && (
        <div role="alert" className="erro">
          <p>{falha.detalhe}</p>
          <button type="button" disabled={enviando} onClick={() => void reenviar(falha.mensagem)}>
            Reenviar
          </button>
        </div>
      )}
      <form
        className="envio"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar(texto);
        }}
      >
        <label htmlFor="mensagem">Mensagem</label>
        <input
          id="mensagem"
          value={texto}
          maxLength={500}
          disabled={enviando || encerrada}
          onChange={(e) => setTexto(e.target.value)}
          placeholder={situacao.idioma === "es" ? "Escribe tu mensaje" : "Escreva sua mensagem"}
        />
        <button type="submit" disabled={enviando || encerrada || texto.trim() === ""}>
          Enviar
        </button>
      </form>
      {falas.length > 1 && <AvaliarConversa key={conversaId} token={token} conversaId={conversaId} aoExpirar={aoExpirar} />}
    </section>
  );
}
