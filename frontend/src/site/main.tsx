import { createRoot } from "react-dom/client";
import { Site } from "./Site";
import "./site.css";

// Como no runtime do design: a raiz e o hospedeiro ocupam a janela, e o site rola por cima.
const raiz = document.getElementById("raiz");
if (!raiz) throw new Error("elemento #raiz ausente em site/index.html");
createRoot(raiz).render(
  <div className="site-host">
    <Site />
  </div>,
);
