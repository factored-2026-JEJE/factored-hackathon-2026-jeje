import type { PersonaDaDemo } from "./api/cliente";

/**
 * A persona da conversa de verdade (o site e o "Try in ES/PT" do app): a que tem um exemplo para
 * contestar e, depois, mais de uma recusa (o "qual transação" do design) e um cartão para bloquear
 * (sem ele, o relato de fraude ainda vai ao atendente).
 */
export function escolherPersona(personas: readonly PersonaDaDemo[]): PersonaDaDemo | undefined {
  const nota = (p: PersonaDaDemo) =>
    (p.exemplo ? 4 : 0) + (p.transacoes_recusadas > 1 ? 2 : 0) + (p.cartoes_bloqueaveis > 0 ? 1 : 0);
  return [...personas].sort((a, b) => nota(b) - nota(a))[0];
}
