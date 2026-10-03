import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { type Lingua, type Textos, textos } from "./conteudo";
import { linguaInicial, marcarDocumento } from "./lingua";
import { ouvirLingua } from "./ponte";

interface LinguaDoApp {
  readonly lingua: Lingua;
  readonly t: Textos;
  readonly mudarLingua: (lingua: Lingua) => void;
}

// Fora do provedor (um componente testado sozinho), o inglês, a língua padrão do app.
const Contexto = createContext<LinguaDoApp>({ lingua: "en", t: textos("en"), mudarLingua: () => {} });

/** A língua da interface para todo o app: a do endereço ao abrir, a da barra e a que o site mandar. */
export function LinguaDoAppProvider({ children }: { children: ReactNode }) {
  const [lingua, mudarLingua] = useState<Lingua>(() => linguaInicial());
  useEffect(() => ouvirLingua(mudarLingua), []);
  useEffect(() => marcarDocumento(lingua), [lingua]);
  const valor = useMemo(() => ({ lingua, t: textos(lingua), mudarLingua }), [lingua]);
  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useLingua(): LinguaDoApp {
  return useContext(Contexto);
}
