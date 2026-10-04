import { useCallback, useEffect, useRef, useState } from "react";
import { AreaDoAtendente } from "./abas/Atendente";
import { AreaDoCliente } from "./abas/Cliente";
import { AreaComoTestar } from "./abas/ComoTestar";
import { AreaDaOperacao } from "./abas/Operacao";
import { listarPersonas } from "./api/cliente";
import { type Aba, ENDERECO, abaDoEndereco } from "./app/abas";
import { avisarRota } from "./app/ponte";
import { SessaoProvider, useSessao } from "./app/sessao";
import { Topo } from "./app/Topo";
import { escolherPersona } from "./personas";
import "./app/app.css";

// A casca do app (DEV-032b, design de 03/10): a barra do topo e quatro áreas, cada uma com endereço
// próprio (#customer, #agent, #operations e #how-to-test; os de antes em português abrem a mesma). Sem endereço, abre a do cliente. As áreas
// escondidas continuam montadas: a conversa não se perde, e a fila, os bloqueios e as métricas seguem
// sendo atualizados enquanto o cliente conversa.
function Casca() {
  // Cada pré-caso, encaminhamento ou bloqueio criado na conversa atualiza o console e as métricas.
  const [versao, setVersao] = useState(0);
  const mudou = useCallback(() => setVersao((v) => v + 1), []);
  const [aba, setAba] = useState<Aba>(abaDoEndereco);
  useEffect(() => {
    const seguir = () => setAba(abaDoEndereco());
    window.addEventListener("hashchange", seguir);
    return () => window.removeEventListener("hashchange", seguir);
  }, []);
  // A aba mudou (não ao abrir): o site, com o app na janela dele, mostra o endereço na barra.
  const anterior = useRef(aba);
  useEffect(() => {
    if (anterior.current === aba) return;
    anterior.current = aba;
    avisarRota(`#${ENDERECO[aba]}`);
  }, [aba]);

  // A frase que vai para a conversa: a do "Perguntar sobre esta" ou a do "Try in ES/PT" das outras
  // abas, que entra sozinho (a persona da demonstração, com o dispositivo cadastrado) quando preciso.
  const [pergunta, setPergunta] = useState<string | null>(null);
  const perguntado = useCallback(() => setPergunta(null), []);
  const { sessao, entrar } = useSessao();
  const experimentar = useCallback(
    async (frase: string) => {
      if (!sessao) {
        const persona = escolherPersona(await listarPersonas());
        if (!persona) return;
        await entrar(persona, "cadastrado");
      }
      window.location.hash = `#${ENDERECO.cliente}`;
      setAba("cliente");
      setPergunta(frase);
    },
    [sessao, entrar],
  );
  const area = { versao, aoMudar: mudou, experimentar: (frase: string) => void experimentar(frase) };

  return (
    <div className="app-pagina">
      <Topo aba={aba} versao={versao} aoEscolher={setAba} />
      <main className="app-conteudo">
        <div role="tabpanel" id="painel-cliente" aria-labelledby="aba-cliente" hidden={aba !== "cliente"} className="app-area">
          <AreaDoCliente {...area} pergunta={pergunta} aoPerguntar={setPergunta} aoPerguntado={perguntado} />
        </div>
        <div
          role="tabpanel"
          id="painel-atendente"
          aria-labelledby="aba-atendente"
          hidden={aba !== "atendente"}
          className="app-area"
        >
          <AreaDoAtendente {...area} />
        </div>
        <div role="tabpanel" id="painel-operacao" aria-labelledby="aba-operacao" hidden={aba !== "operacao"} className="app-area">
          <AreaDaOperacao {...area} />
        </div>
        <div role="tabpanel" id="painel-how-to-test" aria-labelledby="aba-how-to-test" hidden={aba !== "how-to-test"} className="app-area">
          <AreaComoTestar {...area} />
        </div>
      </main>
    </div>
  );
}

export function App() {
  return (
    <SessaoProvider>
      <Casca />
    </SessaoProvider>
  );
}
