// Formatos das abas do console (DEV-032b, 2.10), os mesmos do design: a hora em HH:MM:SS, o dia em
// dd/mm e o valor com duas casas (no inglês, com ponto; no espanhol e no português, com vírgula e o
// milhar com ponto, como o money() do design).
import type { Lingua } from "../app/conteudo";

const dois = (n: number) => String(n).padStart(2, "0");

export function hora(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : `${dois(d.getHours())}:${dois(d.getMinutes())}:${dois(d.getSeconds())}`;
}

export function diaMes(iso: string): string {
  const [ano, mes, dia] = iso.slice(0, 10).split("-");
  return ano && mes && dia ? `${dia}/${mes}` : "—";
}

export function dinheiro(valor: string | number, lingua: Lingua): string {
  const n = Number(valor);
  if (!Number.isFinite(n)) return String(valor);
  if (lingua === "en") return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const [inteiro = "0", centavos = "00"] = n.toFixed(2).split(".");
  return `${inteiro.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${centavos}`;
}

// As contagens e as proporções no mesmo separador do dinheiro: o do inglês, ou o ponto no milhar.
const local = (lingua: Lingua) => (lingua === "en" ? "en-US" : "pt-BR");

export const numero = (n: number, lingua: Lingua): string => n.toLocaleString(local(lingua));

export const percentual = (p: number | null, lingua: Lingua): string =>
  p === null
    ? "—"
    : p.toLocaleString(local(lingua), { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });
