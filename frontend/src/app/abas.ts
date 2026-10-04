// As quatro áreas do app, cada uma com endereço próprio em inglês, a língua do site dos jurados
// (#customer, #agent, #operations e o guia em #how-to-test, PRD-009), com a chave do rótulo de cada uma
// no conteúdo do design. Os endereços em português de antes (#cliente, #atendente, #operacao) seguem
// abrindo a mesma área, para não quebrar os links já citados. Sem endereço (ou com um desconhecido),
// abre a do cliente.
export const ABAS = [
  ["cliente", "cliente"],
  ["atendente", "atendente"],
  ["operacao", "operacao"],
  ["how-to-test", "guia"],
] as const;

export type Aba = (typeof ABAS)[number][0];

export const ENDERECO: Readonly<Record<Aba, string>> = {
  cliente: "customer",
  atendente: "agent",
  operacao: "operations",
  "how-to-test": "how-to-test",
};

export function abaDoEndereco(hash: string = window.location.hash): Aba {
  const pedida = hash.slice(1);
  return ABAS.find(([id]) => ENDERECO[id] === pedida || id === pedida)?.[0] ?? "cliente";
}
