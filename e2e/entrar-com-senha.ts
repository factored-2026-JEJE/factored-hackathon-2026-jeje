// Antes das jornadas, numa stack com o portão dos jurados ligado (PRD-009, make e2e-pelo-portao):
// entra com a senha e guarda o cookie de acesso, que o navegador e as chamadas à API reaproveitam.
import { request } from "@playwright/test";
import { ESTADO_DO_ACESSO } from "./acesso";

export default async function entrarComSenha() {
  const contexto = await request.newContext({ baseURL: process.env.BASE_URL });
  const resposta = await contexto.post("/api/acesso", { data: { senha: process.env.ACESSO_SENHA } });
  if (resposta.status() !== 204) throw new Error(`portão recusou a senha de teste: HTTP ${resposta.status()}`);
  await contexto.storageState({ path: ESTADO_DO_ACESSO });
  await contexto.dispose();
}
