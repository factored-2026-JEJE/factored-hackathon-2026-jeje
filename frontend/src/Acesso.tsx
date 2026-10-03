import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { ACESSO_RESTRITO, entrarComSenha, situacaoDoAcesso } from "./api/cliente";
import { useLingua } from "./app/LinguaDoApp";
import { PORTAO, traduzir } from "./app/textos";
import "./app/app.css";

/** Portão dos jurados (PRD-009): com a senha configurada na API, a demonstração só abre depois dela
 * e começa pelo guia (#how-to-test). Sem senha (desenvolvimento, CI), abre direto. Quem decide é a
 * API, que recusa toda rota sem o cookie de acesso: aqui a tela só segue o que ela responde. */
export function Acesso({ children }: { children: ReactNode }) {
  const [situacao, setSituacao] = useState<"carregando" | "aberto" | "fechado">("carregando");
  const [senha, setSenha] = useState("");
  const [errada, setErrada] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const { lingua } = useLingua();
  const t = (texto: (typeof PORTAO)[keyof typeof PORTAO]) => traduzir(texto, lingua);

  useEffect(() => {
    let ativo = true;
    situacaoDoAcesso()
      .then((s) => ativo && setSituacao(s.liberado ? "aberto" : "fechado"))
      // Sem resposta da API, a demonstração abre e mostra o próprio erro de cada parte.
      .catch(() => ativo && setSituacao("aberto"));
    const fechar = () => setSituacao("fechado");
    window.addEventListener(ACESSO_RESTRITO, fechar);
    return () => {
      ativo = false;
      window.removeEventListener(ACESSO_RESTRITO, fechar);
    };
  }, []);

  async function entrar(evento: FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    try {
      if (await entrarComSenha(senha)) {
        window.location.hash = "#how-to-test";
        setSituacao("aberto");
      } else {
        setErrada(true);
      }
    } finally {
      setEnviando(false);
    }
  }

  if (situacao === "carregando") return <p role="status">{t(PORTAO.carregando)}</p>;
  if (situacao === "aberto") return <>{children}</>;
  // No estilo do design (o portão não foi desenhado): o quadrado azul, o título condensado e o campo.
  return (
    <main className="app-portao">
      <p className="app-portao-kicker">
        <span className="app-quadrado" />
        {t(PORTAO.kicker)}
      </p>
      <h1>JEJE</h1>
      <p>{t(PORTAO.corpo)}</p>
      <form className="app-portao-form" onSubmit={(evento) => void entrar(evento)}>
        <label htmlFor="senha">{t(PORTAO.senha)}</label>
        <input
          id="senha"
          type="password"
          autoComplete="current-password"
          value={senha}
          onChange={(evento) => {
            setSenha(evento.target.value);
            setErrada(false);
          }}
        />
        <button type="submit" disabled={enviando || senha === ""}>
          {t(PORTAO.entrar)}
        </button>
      </form>
      {errada && <p role="alert">{t(PORTAO.errada)}</p>}
    </main>
  );
}
