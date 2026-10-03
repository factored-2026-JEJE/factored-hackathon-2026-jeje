// Textos da casca que o design não tem (DEV-032b), no tom e nas três línguas dele: o portão dos jurados
// (PRD-009). Os do design ficam em conteudo.ts, só para leitura.
import { E, type Lingua, type Traducao } from "./conteudo";

export const PORTAO = {
  kicker: E("Factored AI & Data Hackathon 2026", "Factored AI & Data Hackathon 2026", "Factored AI & Data Hackathon 2026"),
  corpo: E(
    "This demo is for the judges of the Factored AI & Data Hackathon 2026. Enter the password the team sent you.",
    "Esta demo es para el jurado del Factored AI & Data Hackathon 2026. Escribe la contraseña que te envió el equipo.",
    "Esta demo é para os jurados do Factored AI & Data Hackathon 2026. Digite a senha que o time enviou.",
  ),
  senha: E("Password", "Contraseña", "Senha"),
  entrar: E("Enter", "Entrar", "Entrar"),
  errada: E("Wrong password.", "Contraseña incorrecta.", "Senha errada."),
  carregando: E("Loading…", "Cargando…", "Carregando…"),
} as const;

export const traduzir = (texto: Traducao, lingua: Lingua): string => texto[lingua] ?? texto.en;
