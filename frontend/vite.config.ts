import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Duas páginas no mesmo build: o app em / e o site do JEJE em /site/ (DEV-032a).
const pagina = (caminho: string) => fileURLToPath(new URL(caminho, import.meta.url));

export default defineConfig({
  plugins: [react()],
  build: {
    // O three.js (~660 kB) é um pedaço à parte, carregado só com movimento e WebGL (o mapa 3D).
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      input: { app: pagina("./index.html"), site: pagina("./site/index.html") },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
});
