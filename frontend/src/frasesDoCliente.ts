// As frases como o cliente as escreveria, usadas pelo app (o guia de cada persona) e pela conversa do
// site (DEV-032a): uma fonte só para o formato do valor e da data.
import type { ExemploDeContestacao } from "./api/cliente";

// O valor como o cliente escreveria: milhar em ponto e decimal em vírgula ("1.234,56").
export function quantiaDoCliente(valor: string): string {
  const [inteiro = "0", centavos = "00"] = Number(valor).toFixed(2).split(".");
  return `${inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${centavos}`;
}

// O exemplo do guia (DEV-073): uma compra contestável da própria persona, com valor e dia que só ela
// tem, na frase que o cliente digitaria em cada língua ([espanhol, português]).
export function frasesDoExemplo(e: ExemploDeContestacao): [string, string] {
  const quantia = quantiaDoCliente(e.valor);
  const [, mes, dia] = e.data.split("-");
  return [
    `No reconozco el cobro de ${quantia} del ${dia}/${mes}`,
    `Não reconheço a cobrança de ${quantia} do dia ${dia}/${mes}`,
  ];
}

// A língua de uma frase do cliente pelas marcas mais comuns: ã, õ e ç ou palavras do português; ñ, ¿ e ¡
// ou palavras do espanhol. Null quando não dá para dizer. Serve só para abrir a conversa na língua da
// primeira frase (o site e o "Try in ES/PT" do app): a API relê a língua a cada turno.
export function idiomaDaFrase(texto: string): "es" | "pt" | null {
  const s = " " + texto.toLowerCase() + " ";
  if (/[ãõç]|\snão\s|\snao\s|\smeu\s|\sminha\s|\svocê\s|\scartão\s|\scobrança\s|\squero\s|\sroubaram\s/.test(s)) return "pt";
  if (/[ñ¿¡]|\smi\s|\starjeta\s|\squiero\s|\scobro\s|\srobaron\s|\sme\s/.test(s)) return "es";
  return null;
}
