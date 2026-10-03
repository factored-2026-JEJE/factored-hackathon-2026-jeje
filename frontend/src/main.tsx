// O estilo antigo primeiro: o da casca (app/app.css, importado pelo App) vem depois e prevalece.
import "./estilo.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Acesso } from "./Acesso";
import { App } from "./App";
import { LinguaDoAppProvider } from "./app/LinguaDoApp";

const raiz = document.getElementById("root");
if (!raiz) throw new Error("elemento #root ausente em index.html");
createRoot(raiz).render(
  <StrictMode>
    <LinguaDoAppProvider>
      <Acesso>
        <App />
      </Acesso>
    </LinguaDoAppProvider>
  </StrictMode>,
);
