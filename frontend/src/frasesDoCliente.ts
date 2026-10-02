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
