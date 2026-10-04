import { useEffect, useRef, useState } from "react";
import { CLIENTE, FRASE_DO_ATALHO } from "./abas/cliente/textos";
import { linhasDoPorQue, type Motivo } from "./abas/cliente/porQue";
import {
  abrirConversa,
  buscarProntidao,
  enviarMensagem,
  historicoDaConversa,
  type Idioma,
  NaoRegistrado,
  type ResultadoDoTurno,
  SessaoExpirada,
} from "./api/cliente";
import { ATALHOS, OPCOES } from "./app/conteudo";
import { useLingua } from "./app/LinguaDoApp";
import { avisarTurno } from "./app/ponte";
import { traduzir } from "./app/textos";
import { AvaliarConversa } from "./AvaliarConversa";
import { idiomaDaFrase } from "./frasesDoCliente";

const CHAVE_CONVERSA = "jeje.conversa";

// O que vai para a API quando o cliente toca numa resposta rápida: o mesmo texto que ele digitaria, e
// quem decide o que ele significa é a API (a tela não confirma nada sozinha). Na oferta do atendente,
// os rótulos são os do design, e o que vai é o sí/sim e o no/não.
const RESPOSTAS: Record<Idioma, { sim: string; nao: string; confirmar: string }> = {
  es: { sim: "Sí", nao: "No", confirmar: "Sí, confirmo" },
  pt: { sim: "Sim", nao: "Não", confirmar: "Sim, confirmo" },
};

// Os passos do design (1 · Pedido, 2 · Transação, 3 · Confirmação) pelo estado da conversa na API.
const PASSO: Readonly<Record<string, number>> = {
  esclarecendo: 1,
  escolhendo_cartao: 1,
  confirmando: 2,
  confirmando_desbloqueio: 2,
  confirmando_bloqueio: 2,
};

type Fala = { id: number; autor: "cliente" | "assistente"; texto: string; motivo?: Motivo };

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

// Efeitos que o console do atendente precisa ver: pré-caso, encaminhamento, bloqueio e desbloqueio.
const AVISAM_O_CONSOLE = ["registrar_pre_caso", "humano", "bloquear_cartao", "desbloquear_cartao"];

/** O "Por que esta resposta?" de uma fala, com as linhas do design (ui.rc) lidas do turno da API. */
function PorQue({ motivo, versaoCarregada }: { motivo: Motivo; versaoCarregada: string | null }) {
  const { lingua, t } = useLingua();
  const [aberto, setAberto] = useState(false);
  return (
    <>
      <button type="button" className="conv-porque" aria-expanded={aberto} onClick={() => setAberto(!aberto)}>
        {t.conv.why} {aberto ? "↑" : "↓"}
      </button>
      {aberto && (
        <dl className="conv-recibo">
          {linhasDoPorQue(motivo, t, lingua, versaoCarregada).map(([k, v]) => (
            <div key={k} className="conv-recibo-linha">
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  );
}

/** Conversa com o assistente: cada resposta, opção, passo e protocolo vêm da API. */
export function Conversa({
  token,
  aoExpirar,
  aoMudar,
  aoIdioma = () => {},
  pergunta = null,
  aoPerguntado = () => {},
  exemplo = null,
}: {
  token: string;
  aoExpirar: () => void;
  aoMudar: () => void;
  // "Perguntar sobre esta" (PRD-006): a língua da conversa aberta vai para quem monta a pergunta, e
  // a pergunta montada entra como mensagem do cliente (quem decide o que ela significa é a API).
  aoIdioma?: (idioma: Idioma | null) => void;
  pergunta?: string | null;
  aoPerguntado?: () => void;
  /** A frase de exemplo da persona, nas duas línguas da conversa ([espanhol, português]). */
  exemplo?: readonly [string, string] | null;
}) {
  const { lingua, t } = useLingua();
  const [conversaId, setConversaId] = useState<string | null>(null);
  const [falas, setFalas] = useState<Fala[]>([]);
  const [situacao, setSituacao] = useState<Situacao | null>(null);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<{ mensagem: string; detalhe: string } | null>(null);
  const [carregando, setCarregando] = useState(true);
  // A versão do conjunto de dados carregado na API, para o porquê das respostas sem recibo.
  const [versaoCarregada, setVersaoCarregada] = useState<string | null>(null);
  useEffect(() => {
    let ativo = true;
    buscarProntidao()
      .then((p) => ativo && setVersaoCarregada(p.dataset?.version ?? null))
      .catch(() => {});
    return () => {
      ativo = false;
    };
  }, []);
  const proximo = useRef(0);
  const fala = (autor: Fala["autor"], conteudo: string, motivo?: Motivo): Fala => ({
    id: proximo.current++,
    autor,
    texto: conteudo,
    motivo,
  });
  // A fala nova fica inteira à vista (ACH-209 da validação): a caixa das falas e a página rolam até
  // ela, pelo mínimo. O jsdom dos testes não tem scrollIntoView.
  const log = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const ultima = log.current?.querySelector(".conv-falas > li:last-child");
    if (ultima && typeof ultima.scrollIntoView === "function") ultima.scrollIntoView({ block: "nearest" });
  }, [falas, enviando]);

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
            { id: proximo.current++, autor: "assistente" as const, texto: t.resposta, motivo: { regra: t.regra, acao: t.acao } },
          ]),
        );
        setSituacao({ idioma: historico.idioma, estado: historico.estado, opcoes: [], protocolo: null, atendimento: historico.atendimento });
      })
      .catch((e: unknown) => {
        if (ativo && e instanceof SessaoExpirada) aoExpirar();
      })
      .finally(() => ativo && setCarregando(false));
    return () => {
      ativo = false;
    };
  }, [token, aoExpirar]);

  // O caso está com o atendente: encaminhado, ou o relato de fraude que ainda pergunta o cartão a
  // bloquear (PRD-009). A tela mostra isso e não oferece atalhos nem "Perguntar sobre esta".
  const comAtendente = situacao !== null && (situacao.estado === "com_humano" || situacao.atendimento !== null);
  const aberta = conversaId && situacao && situacao.estado !== "encerrada" && !comAtendente;
  const idiomaAberto = aberta ? situacao.idioma : null;
  useEffect(() => {
    aoIdioma(idiomaAberto);
  }, [idiomaAberto, aoIdioma]);
  // A frase de fora ("Perguntar sobre esta" ou o "Try in ES/PT" das outras abas) vai como mensagem do
  // cliente; sem conversa aberta, o envio abre uma.
  useEffect(() => {
    if (!pergunta || carregando) return;
    aoPerguntado();
    void enviar(pergunta);
  }, [pergunta, aoPerguntado, carregando]);

  // Sem conversa aberta, a primeira mensagem abre uma na língua da frase (ou na da interface: português
  // ou, senão, espanhol). A saudação da API não aparece: o estado vazio do design faz esse papel.
  async function abrir(idioma: Idioma): Promise<string | null> {
    try {
      const nova = await abrirConversa(token, idioma);
      guardar(nova.conversa_id);
      setConversaId(nova.conversa_id);
      setSituacao({ idioma: nova.idioma, estado: nova.estado, opcoes: [], protocolo: null, atendimento: null });
      return nova.conversa_id;
    } catch (e) {
      if (e instanceof SessaoExpirada) aoExpirar();
      else setFalha({ mensagem: "", detalhe: traduzir(CLIENTE.naoAbriu, lingua) });
      return null;
    }
  }

  async function enviar(mensagem: string) {
    const limpa = mensagem.trim();
    if (enviando || limpa === "") return;
    setEnviando(true);
    setFalha(null);
    try {
      const idioma = idiomaDaFrase(limpa) ?? (lingua === "pt" ? "pt" : "es");
      const conversa = conversaId ?? (await abrir(idioma));
      if (!conversa) return;
      const turno = await enviarMensagem(token, conversa, limpa);
      setFalas((atuais) => [
        ...atuais,
        fala("cliente", limpa),
        fala("assistente", turno.resposta, { regra: turno.regra, acao: turno.acao, turno }),
      ]);
      setSituacao({
        idioma: turno.idioma,
        estado: turno.estado,
        opcoes: turno.opcoes,
        // Só um pré-caso gravado agora e relido pela API vira "recebido".
        protocolo: turno.acao === "registrar_pre_caso" ? turno.protocolo : null,
        atendimento: turno.atendimento,
      });
      setTexto("");
      // O site, com o app na janela dele, acende o caminho do turno no mapa.
      avisarTurno(turno);
      if (AVISAM_O_CONSOLE.includes(turno.acao)) aoMudar();
    } catch (e) {
      if (e instanceof SessaoExpirada) aoExpirar();
      else if (e instanceof NaoRegistrado) setFalha({ mensagem: limpa, detalhe: e.message });
      else if (!(await jaProcessada(limpa)))
        setFalha({ mensagem: limpa, detalhe: traduzir(CLIENTE.semResposta, lingua) });
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
      setFalas((atuais) => [...atuais, fala("cliente", ultimo.mensagem), fala("assistente", ultimo.resposta, { regra: ultimo.regra, acao: ultimo.acao })]);
      setSituacao({ idioma: historico.idioma, estado: historico.estado, opcoes: [], protocolo: null, atendimento: historico.atendimento });
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

  if (carregando) return <p role="status">{traduzir(CLIENTE.carregandoConversa, lingua)}</p>;

  const idiomaDaConversa: Idioma = situacao?.idioma ?? (lingua === "pt" ? "pt" : "es");
  const rapidas = RESPOSTAS[idiomaDaConversa];
  const opcoes = OPCOES[idiomaDaConversa];
  // A recarga dos dados encerrou a conversa: nada do contexto vale mais, só uma nova conversa.
  const encerrada = situacao?.estado === "encerrada";
  const passo = situacao ? (PASSO[situacao.estado] ?? 0) : 0;
  const ultima = falas.at(-1);
  // A fala que passou o caso para uma pessoa: o selo e a borda laranja do design (também no histórico).
  const comPessoa = (f: Fala) => f.motivo !== undefined && (f.motivo.acao === "humano" || Boolean(f.motivo.turno?.atendimento));
  // As opções ficam só na última resposta, e somem enquanto a próxima não chega.
  const opcoesDaUltima = (f: Fala) => f === ultima && f.autor === "assistente" && !enviando && situacao !== null;

  return (
    <section aria-label={t.conv.title} className="conv">
      <div className="conv-cab">
        <span className="conv-titulo">{t.conv.title}</span>
        <span className="conv-lingua">{idiomaDaConversa.toUpperCase()}</span>
        <ol className="conv-passos" aria-label={t.conv.title}>
          {t.conv.steps.map((rotulo, i) => (
            <li key={rotulo} className={i === passo ? "atual" : i < passo ? "feito" : undefined} aria-current={i === passo ? "step" : undefined}>
              {rotulo}
            </li>
          ))}
        </ol>
        <button type="button" className="conv-nova" onClick={novaConversa}>
          {t.conv.newConv}
        </button>
      </div>
      <div role="log" aria-label={t.conv.title} className="conv-log" ref={log}>
        {falas.length === 0 && (
          <div className="conv-vazia">
            <p>{t.conv.empty}</p>
            {exemplo && (
              <>
                <span className="conv-mono">{t.conv.tryThis}</span>
                <button type="button" className="conv-exemplo" disabled={enviando} onClick={() => void enviar(exemplo[idiomaDaConversa === "es" ? 0 : 1])}>
                  “{exemplo[idiomaDaConversa === "es" ? 0 : 1]}”
                </button>
              </>
            )}
          </div>
        )}
        <ol className="conv-falas">
          {falas.map((f) =>
            f.autor === "cliente" ? (
              <li key={f.id} className="conv-fala conv-cliente">
                <span className="conv-mono">{t.conv.you}</span>
                <p>{f.texto}</p>
              </li>
            ) : (
              <li key={f.id} className={"conv-fala conv-sistema" + (comPessoa(f) ? " humano" : "")}>
                <span className="conv-mono">
                  <span>JEJE</span>
                  {f.motivo && <span className="conv-regra">{f.motivo.regra}</span>}
                </span>
                <div className="conv-balao">
                  {comPessoa(f) && <span className="conv-humano">{t.conv.human}</span>}
                  <p>{f.texto}</p>
                  {f === ultima && situacao?.protocolo && (
                    <span role="status" className="conv-protocolo">
                      {situacao.protocolo} · {traduzir(CLIENTE.recebido, lingua)}
                    </span>
                  )}
                </div>
                {opcoesDaUltima(f) && situacao && (
                  <div role="group" aria-label={traduzir(CLIENTE.opcoes, lingua)} className="conv-opcoes">
                    {situacao.opcoes.map((o) => (
                      <button key={o.numero} type="button" className="conv-opcao" disabled={enviando} onClick={() => void enviar(String(o.numero))}>
                        {o.descricao}
                      </button>
                    ))}
                    {(situacao.estado === "confirmando" ||
                      situacao.estado === "confirmando_desbloqueio" ||
                      situacao.estado === "confirmando_bloqueio") && (
                      <>
                        <button type="button" className="conv-opcao" disabled={enviando} onClick={() => void enviar(rapidas.confirmar)}>
                          {opcoes.yes}
                        </button>
                        <button type="button" className="conv-opcao" disabled={enviando} onClick={() => void enviar(rapidas.nao)}>
                          {opcoes.no}
                        </button>
                      </>
                    )}
                    {situacao.estado === "oferecendo_humano" && (
                      <>
                        {/* Rótulos do design; o que vai para a API continua sendo o sí/sim e o no/não. */}
                        <button type="button" className="conv-opcao" disabled={enviando} onClick={() => void enviar(rapidas.sim)}>
                          {opcoes.agent}
                        </button>
                        <button type="button" className="conv-opcao" disabled={enviando} onClick={() => void enviar(rapidas.nao)}>
                          {opcoes.stay}
                        </button>
                      </>
                    )}
                  </div>
                )}
                {f.motivo && <PorQue motivo={f.motivo} versaoCarregada={versaoCarregada} />}
              </li>
            ),
          )}
          {enviando && (
            <li className="conv-lendo" role="status">
              {t.conv.reading} · {t.rd.rules} …
            </li>
          )}
        </ol>
        {encerrada && (
          <p role="status" className="conv-aviso">
            {traduzir(CLIENTE.encerrada, lingua)}
          </p>
        )}
        {falha && (
          <div role="alert" className="conv-erro">
            <p>{falha.detalhe}</p>
            {falha.mensagem && (
              <button type="button" disabled={enviando} onClick={() => void reenviar(falha.mensagem)}>
                {traduzir(CLIENTE.reenviar, lingua)}
              </button>
            )}
          </div>
        )}
        {conversaId && falas.length > 1 && <AvaliarConversa key={conversaId} token={token} conversaId={conversaId} aoExpirar={aoExpirar} />}
      </div>
      <div className="conv-envio">
        {!encerrada && !comAtendente && (
          <div role="group" aria-label={traduzir(CLIENTE.atalhos, lingua)} className="conv-atalhos">
            {ATALHOS[idiomaDaConversa].map(([rotulo, frase]) => (
              <button key={rotulo} type="button" disabled={enviando} onClick={() => void enviar(FRASE_DO_ATALHO[frase] ?? frase)}>
                {rotulo}
              </button>
            ))}
          </div>
        )}
        <form
          className="conv-form"
          onSubmit={(e) => {
            e.preventDefault();
            void enviar(texto);
          }}
        >
          <input
            value={texto}
            maxLength={500}
            disabled={enviando || encerrada}
            onChange={(e) => setTexto(e.target.value)}
            placeholder={t.conv.ph}
            aria-label={t.conv.ph}
          />
          <button type="submit" disabled={enviando || encerrada || texto.trim() === ""}>
            {t.conv.send}
          </button>
        </form>
      </div>
    </section>
  );
}
