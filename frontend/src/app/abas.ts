// As quatro áreas do app, cada uma com endereço próprio (#cliente, #atendente, #operacao e o guia dos
// jurados em #how-to-test, PRD-009), com a chave do rótulo de cada uma no conteúdo do design. Sem
// endereço (ou com um desconhecido), abre a do cliente.
export const ABAS = [
  ["cliente", "cliente"],
  ["atendente", "atendente"],
  ["operacao", "operacao"],
  ["how-to-test", "guia"],
] as const;

export type Aba = (typeof ABAS)[number][0];

export function abaDoEndereco(hash: string = window.location.hash): Aba {
  const pedida = hash.slice(1);
  return ABAS.find(([id]) => id === pedida)?.[0] ?? "cliente";
}
