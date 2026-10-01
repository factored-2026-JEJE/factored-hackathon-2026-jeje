import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Acesso } from "./Acesso";
import { App } from "./App";
import "./estilo.css";

const raiz = document.getElementById("root");
if (!raiz) throw new Error("elemento #root ausente em index.html");
createRoot(raiz).render(
  <StrictMode>
    <Acesso>
      <App />
    </Acesso>
  </StrictMode>,
);
