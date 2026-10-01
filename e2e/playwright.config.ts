// Jornadas reais no navegador contra a stack do compose. BASE_URL vem do compose (ENG-003).
import { defineConfig, devices } from "@playwright/test";
import { ESTADO_DO_ACESSO } from "./acesso";

const baseURL = process.env.BASE_URL;
if (!baseURL) throw new Error("BASE_URL ausente: rode pelo serviço e2e do compose");

// Com o portão dos jurados ligado (ACESSO_SENHA, PRD-009), as jornadas entram com a senha antes e
// reaproveitam o cookie de acesso; sem ele, nada muda.
const comSenha = Boolean(process.env.ACESSO_SENHA);

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  retries: 0,
  reporter: [["list"]],
  globalSetup: comSenha ? "./entrar-com-senha.ts" : undefined,
  use: { baseURL, trace: "retain-on-failure", storageState: comSenha ? ESTADO_DO_ACESSO : undefined },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
  ],
});
