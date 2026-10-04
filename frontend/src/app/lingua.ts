// A língua da interface do app (DEV-032b), como no design: o ?lang= do endereço (o site abre o app com
// a língua dele) e, sem ele, o inglês. A troca pela barra e a mensagem do site mudam a língua da
// página aberta. O <html lang> acompanha, para leitores de tela e o corretor do navegador.
import type { Lingua } from "./conteudo";

export const LINGUAS: readonly Lingua[] = ["en", "es", "pt"];

export function ehLingua(valor: unknown): valor is Lingua {
  return typeof valor === "string" && (LINGUAS as readonly string[]).includes(valor);
}

/** A língua ao abrir: a do ?lang= quando válida; senão, o inglês. */
export function linguaInicial(busca: string = window.location.search): Lingua {
  let pedida: string | null = null;
  try {
    pedida = new URLSearchParams(busca).get("lang");
  } catch {
    // Endereço sem busca legível: fica o padrão.
  }
  return ehLingua(pedida) ? pedida : "en";
}

const LOCALE: Readonly<Record<Lingua, string>> = { en: "en", es: "es", pt: "pt-BR" };

export function marcarDocumento(lingua: Lingua, documento: Document = document) {
  if (documento.documentElement.lang !== LOCALE[lingua]) documento.documentElement.lang = LOCALE[lingua];
}
