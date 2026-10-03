// O site do JEJE (DEV-032a): a réplica do design entregue (04-solucao/design-do-site no vault), com o
// mesmo template, a mesma lógica e o mesmo mapa da arquitetura, em 3D (Three.js, carregado só com
// movimento e WebGL) ou em 2D (SVG), preso à rolagem.
import { Component, Fragment, createRef, type ChangeEvent, type KeyboardEvent } from "react";
import type * as THREE from "three";
import {
  AcessoRestrito,
  SessaoExpirada,
  abrirConversa,
  abrirSessao,
  enviarMensagem,
  listarPersonas,
  situacaoDoAcesso,
  type PersonaDaDemo,
  type ResultadoDoTurno,
} from "../api/cliente";
import { frasesDoExemplo, idiomaDaFrase } from "../frasesDoCliente";
import { escolherPersona } from "../personas";
import { SEM_NUMEROS, comNumerosAoVivo, lerNumerosAoVivo, type NumerosAoVivo } from "./aoVivo";
import {
  C as frase,
  CONTEUDO,
  T,
  resolver,
  type CategoriaDeRegra,
  type IdDaJornada,
  type Idioma,
  type IdiomaDaConversa,
  type TipoDeFonte,
} from "./conteudo";
import { CONTEUDO_DO_MAIN, MAPA_DO_MAIN } from "./fatos";
import {
  DADOS,
  IDS_DOS_NOS,
  MAPA_DO_DESIGN,
  MENSAGEM,
  caminho,
  construirLigacoes,
  pontoNoCaminho,
  quadro,
  suavizar,
  type Caminho,
  type IdDoNo,
  type Ligacao,
} from "./mapa";
import { caminhoDaJornada, caminhoDoTurno, type CaminhoDoTurno } from "./turnoNoMapa";

// Só o design (VITE_SO_DESIGN=1): o conteúdo e o mapa do designer, sem a API. É assim que a réplica
// é comparada com o HTML do designer; o site publicado mostra os fatos do main e os números ao vivo.
const SO_DESIGN = import.meta.env.VITE_SO_DESIGN === "1";
const CONTEUDO_DO_SITE = SO_DESIGN ? CONTEUDO : CONTEUDO_DO_MAIN;
const MAPA = SO_DESIGN ? MAPA_DO_DESIGN : MAPA_DO_MAIN;
const NOS = MAPA.nos;

type ItemDaConversa =
  | { readonly who: "c"; readonly text: string }
  // a resposta de uma jornada de exemplo do design
  | { readonly who: "s"; readonly id: IdDaJornada; readonly lang: IdiomaDaConversa; readonly done?: boolean }
  // a resposta da API de verdade, com o turno inteiro
  | { readonly who: "v"; readonly turno: ResultadoDoTurno; readonly done?: boolean }
  // um aviso da conversa (a API não respondeu)
  | { readonly who: "e"; readonly text: string; readonly done?: boolean };

interface Estado {
  lang: Idioma;
  motion: boolean;
  vw: number;
  vh: number;
  confirmed: boolean | null;
  drawer: IdDoNo | "rules" | null;
  src: string | null;
  model: number;
  dockOpen: boolean;
  conv: ItemDaConversa[];
  draft: string;
  convLang: IdiomaDaConversa;
  obsOn: boolean;
  mutant: boolean;
  reproN: number;
  whyOpen: Record<number, boolean>;
  /** Números lidos da API (os do design enquanto ela não responde). */
  numeros: NumerosAoVivo;
  /** A conversa fala com a API de verdade quando o acesso está aberto (local, ou com a senha dos jurados). */
  acesso: "verificando" | "aberto" | "fechado";
}

interface Rotulo {
  readonly el: HTMLElement;
  readonly sub: HTMLElement | null;
  last: string;
}

interface Cena3D {
  readonly T: typeof THREE;
  readonly renderer: THREE.WebGLRenderer;
  readonly scene: THREE.Scene;
  readonly cam: THREE.PerspectiveCamera;
  readonly n3: Partial<Record<IdDoNo, { readonly mat: THREE.MeshStandardMaterial; lit: number; readonly top: number }>>;
  readonly e3: { readonly coreGeo: THREE.TubeGeometry; readonly coreMat: THREE.MeshBasicMaterial; readonly seg: number; readonly rad: number }[];
  readonly capM: THREE.Mesh<THREE.CapsuleGeometry, THREE.MeshStandardMaterial>;
  readonly capD: THREE.Mesh<THREE.CapsuleGeometry, THREE.MeshStandardMaterial>;
  readonly cBase: THREE.Color;
  readonly cCob: THREE.Color;
  readonly cVer: THREE.Color;
  readonly cHov: THREE.Color;
  readonly tmpV: THREE.Vector3;
  readonly upV: THREE.Vector3;
}

interface Cena2D {
  readonly svg: SVGSVGElement;
  readonly g2: SVGGElement;
  readonly zone2: SVGRectElement;
  readonly e2: { readonly base: SVGPathElement; readonly core: SVGPathElement; readonly L: number; readonly solid: boolean; readonly ty: string }[];
  readonly nd2: Partial<Record<IdDoNo, SVGElement>>;
  readonly capM2: SVGCircleElement;
  readonly capD2: SVGCircleElement;
}

interface Geometria {
  readonly edges: Ligacao[];
  readonly msgR: Caminho;
  readonly dataR: Caminho;
}

const CHAVES_DA_CAMERA = ["x", "y", "z", "r", "th", "ph", "ox", "oy", "mu", "du"] as const;
type Camera = Record<(typeof CHAVES_DA_CAMERA)[number], number>;

interface Demo {
  readonly t0: number;
  readonly caminho: CaminhoDoTurno;
}

/** O que a gaveta lateral mostra: um componente do mapa ou a lista das regras. */
interface Gaveta {
  title: string;
  kicker: string;
  isRules: boolean;
  isNode: boolean;
  sub: string;
  planned: boolean;
  does: string;
  protects: readonly string[];
  hasStat: boolean;
  statV: string;
  statL: string;
  statS: string;
  openStat?: () => void;
  hasModel: boolean;
  modelLbl: string;
  goModel?: () => void;
}

const GAVETA_VAZIA: Gaveta = {
  title: "",
  kicker: "",
  isRules: false,
  isNode: false,
  sub: "",
  planned: false,
  does: "",
  protects: [],
  hasStat: false,
  statV: "",
  statL: "",
  statS: "",
  hasModel: false,
  modelLbl: "",
};

/** Uma fala na conversa da tela: a do cliente (isC) ou a do sistema (isS), com o "por que". */
interface FalaNaTela {
  isC: boolean;
  isS: boolean;
  text: string;
  human: boolean;
  humanL: string;
  bc: string;
  rows: { k: string; v: string }[];
  hasOpts: boolean;
  opts: { l: string; pick: () => void }[];
  whyL: string;
  whyArrow: string;
  whyOpen: boolean;
  toggleWhy?: () => void;
}

type Projecao = (x: number, y: number, z: number) => { sx: number; sy: number; ok: boolean };

// A conversa de verdade (DEV-032a): os botões mandam o mesmo texto que o cliente digitaria, como no
// app (Conversa.tsx), com os rótulos das jornadas do design.
const RESPOSTAS = {
  confirmar: frase("Sí, confirmo", "Sim, confirmo"),
  nao: frase("No", "Não"),
  sim: frase("Sí", "Sim"),
  humano: frase("Hablar con un agente", "Falar com um atendente"),
  seguir: frase("Seguir aquí", "Continuar aqui"),
};

// Como a transação do turno foi achada (o rastro do resolvedor), nos três idiomas do site.
const TRANSACAO_AO_VIVO = {
  possiveis: T("possíveis · pergunta qual", "posibles · pregunta cuál", "candidates · asks which"),
  filtro: T("filtro exato", "filtro exacto", "exact filter"),
  ranking: T("ranking com garantia (α = 5%)", "ranking con garantía (α = 5%)", "ranking with a guarantee (α = 5%)"),
  semGarantia: T("ranking sem garantia: mostra as possíveis", "ranking sin garantía: muestra las posibles", "ranking without a guarantee: shows candidates"),
  escolha: T("escolhida pelo cliente", "elegida por el cliente", "chosen by the customer"),
  foco: T("a da proposta", "la de la propuesta", "the proposed one"),
  erro: T(
    "A API não respondeu agora. Mande de novo: a conversa não repete efeitos.",
    "La API no respondió ahora. Vuelve a enviar: la conversación no repite efectos.",
    "The API did not answer just now. Send it again: the chat does not repeat effects.",
  ),
};

// A persona da conversa de verdade (personas.ts), a mesma que o "Try in ES/PT" do app usa.
export { escolherPersona };

/**
 * Um valor no meio de um texto, como no runtime do design: num <span> próprio. Num contêiner flex o
 * span é um item à parte (o gap separa "MOVIMENTO", "·" e "LIGADO", e "Abrir o app" cola no "↗").
 */
function I(valor: string | number | null | undefined) {
  return valor == null ? null : <span className="sc-interp">{valor}</span>;
}

export class Site extends Component<object, Estado> {
  state: Estado = {
    lang: "pt",
    motion: true,
    vw: window.innerWidth,
    vh: window.innerHeight,
    confirmed: null,
    drawer: null,
    src: null,
    model: 0,
    dockOpen: false,
    conv: [],
    draft: "",
    convLang: "pt",
    obsOn: false,
    mutant: false,
    reproN: 0,
    whyOpen: {},
    numeros: SEM_NUMEROS,
    acesso: SO_DESIGN ? "fechado" : "verificando",
  };
  canvasRef = createRef<HTMLCanvasElement>();
  stageRef = createRef<HTMLDivElement>();
  svgHostRef = createRef<HTMLDivElement>();
  labelsRef = createRef<HTMLDivElement>();
  progRef = createRef<HTMLDivElement>();
  receiptRef = createRef<HTMLDivElement>();
  convRef = createRef<HTMLDivElement>();
  zoneRef = createRef<HTMLDivElement>();

  private ro: ResizeObserver | null = null;
  private raf = 0;
  private rt: ReturnType<typeof setInterval> | undefined;
  private inited = false;
  private movimentoAplicado = true;
  private blocks: HTMLElement[] = [];
  private lbls: Partial<Record<IdDoNo, Rotulo>> = {};
  private mode: "2d" | "3d" = "2d";
  private geo: Geometria | null = null;
  private tres: Cena3D | null = null;
  private loading3d: Promise<boolean> | null = null;
  private plano: Cena2D | null = null;
  private cv: Camera | null = null;
  private snap = false;
  private demo: Demo | null = null;
  private hover: IdDoNo | null = null;
  private leitura = new AbortController();
  private sessao: { readonly token: string; readonly persona: PersonaDaDemo } | null = null;
  private conversa: { readonly id: string; readonly idioma: IdiomaDaConversa } | null = null;
  private enviando = false;

  componentDidMount() {
    let lang: Idioma = "pt";
    // Sem matchMedia (jsdom), o padrão é com movimento, como no design.
    let motion = !(typeof window.matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches);
    try {
      const l = localStorage.getItem("jeje.site.lang");
      if (l === "pt" || l === "es" || l === "en") lang = l;
      const m = localStorage.getItem("jeje.site.motion");
      if (m) motion = m === "1";
    } catch {
      // sem armazenamento (janela privada): fica o padrão
    }
    this.setState({ lang, motion, convLang: lang === "pt" ? "pt" : "es", vw: innerWidth, vh: innerHeight });
    if (window.ResizeObserver) {
      this.ro = new ResizeObserver(() => {
        if (innerWidth !== this.state.vw || innerHeight !== this.state.vh) this.onResize();
      });
      this.ro.observe(document.documentElement);
    }
    setTimeout(() => this.init(), 0);
    if (!SO_DESIGN) this.lerDaApi();
    addEventListener("resize", this.onResize);
    addEventListener("keydown", this.onKeyEsc);
    this.raf = requestAnimationFrame(this.tick);
  }

  componentWillUnmount() {
    cancelAnimationFrame(this.raf);
    removeEventListener("resize", this.onResize);
    removeEventListener("keydown", this.onKeyEsc);
    clearInterval(this.rt);
    this.leitura.abort();
    if (this.ro) this.ro.disconnect();
    if (this.tres) this.tres.renderer.dispose();
  }

  /** Os números ao vivo e se a conversa pode falar com a API (sem resposta, fica o design). */
  private lerDaApi() {
    const sinal = this.leitura.signal;
    void lerNumerosAoVivo(sinal).then((numeros) => {
      if (!sinal.aborted) this.setState({ numeros });
    });
    situacaoDoAcesso()
      .then((s) => !sinal.aborted && this.setState({ acesso: !s.restrito || s.liberado ? "aberto" : "fechado" }))
      .catch(() => !sinal.aborted && this.setState({ acesso: "fechado" }));
  }

  componentDidUpdate() {
    this.cacheEls();
    if (this.inited && this.movimentoAplicado !== this.state.motion) {
      this.movimentoAplicado = this.state.motion;
      void this.applyMode();
    }
  }

  private onResize = () => {
    this.setState({ vw: innerWidth, vh: innerHeight });
    this.resize();
    this.snap = true;
  };

  private onKeyEsc = (e: globalThis.KeyboardEvent) => {
    if (e.key === "Escape") this.setState({ drawer: null, src: null });
  };

  private cacheEls() {
    const st = this.stageRef.current;
    if (!st) return;
    const root = st.parentNode;
    if (!(root instanceof HTMLElement)) return;
    this.blocks = Array.from(root.querySelectorAll<HTMLElement>("[data-stop]"));
    this.lbls = {};
    root.querySelectorAll<HTMLElement>("[data-lbl]").forEach((el) => {
      this.lbls[el.getAttribute("data-lbl") as IdDoNo] = { el, sub: el.querySelector<HTMLElement>("[data-sub]"), last: "" };
    });
  }

  private init() {
    if (this.inited) return;
    this.inited = true;
    this.movimentoAplicado = this.state.motion;
    this.buildGeo();
    this.cacheEls();
    this.build2D();
    void this.applyMode();
  }

  private webgl() {
    try {
      const c = document.createElement("canvas");
      return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
    } catch {
      return false;
    }
  }

  private async applyMode() {
    if (!this.inited) return;
    let mode: "2d" | "3d" = "2d";
    if (this.state.motion && this.webgl()) {
      const ok = await this.load3D();
      if (ok) mode = "3d";
    }
    this.mode = mode;
    if (this.canvasRef.current) this.canvasRef.current.style.display = mode === "3d" ? "block" : "none";
    if (this.plano) this.plano.svg.style.display = mode === "2d" ? "block" : "none";
    this.snap = true;
  }

  private load3D(): Promise<boolean> {
    if (this.tres) return Promise.resolve(true);
    if (this.loading3d) return this.loading3d;
    this.loading3d = (async () => {
      try {
        const T = await import("three");
        this.build3D(T);
        return true;
      } catch (e) {
        console.warn("JEJE: 3D indisponível, usando o mapa 2D", e);
        return false;
      }
    })();
    return this.loading3d;
  }

  private buildGeo() {
    const edges = construirLigacoes(MAPA);
    this.geo = { edges, msgR: caminho(edges, MENSAGEM), dataR: caminho(edges, DADOS) };
  }

  private build2D() {
    const host = this.svgHostRef.current;
    if (!host || this.plano || !this.geo) return;
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");
    svg.style.display = "none";
    const g = document.createElementNS(NS, "g");
    svg.appendChild(g);
    const mk = <K extends keyof SVGElementTagNameMap>(tag: K, at: Record<string, string | number>): SVGElementTagNameMap[K] => {
      const el = document.createElementNS(NS, tag);
      for (const k in at) el.setAttribute(k, String(at[k]));
      g.appendChild(el);
      return el;
    };
    const zone2 = mk("rect", { x: 4.2, y: -1.0, width: 13, height: 4.9, fill: "#F7F4EC", stroke: "#16150F" });
    const e2 = this.geo.edges.map((e) => {
      const d = "M" + e.pts.map((p) => p[0].toFixed(3) + " " + p[2].toFixed(3)).join(" L");
      const solid = e.ty === "m" || e.ty === "d";
      const base = mk("path", { d, fill: "none", stroke: solid ? "#C9C1B1" : "#16150F", "stroke-linecap": "round" });
      const core = mk("path", {
        d,
        fill: "none",
        stroke: "#2B35F0",
        "stroke-linecap": "round",
        "stroke-dasharray": e.len2 + " " + e.len2,
        "stroke-dashoffset": e.len2,
      });
      return { base, core, L: e.len2, solid, ty: e.ty };
    });
    const nd2: Partial<Record<IdDoNo, SVGElement>> = {};
    for (const id of IDS_DOS_NOS) {
      const n = NOS[id];
      let el: SVGElement;
      if (n.k === "db" || n.k === "bucket") el = mk("circle", { cx: n.x, cy: n.y, r: 0.52 });
      else {
        const w = n.k === "screen" ? 1.0 : n.k === "gate" ? 0.34 : n.w || 0.82;
        const h = n.k === "screen" ? 0.66 : n.k === "gate" ? 1.05 : (n.w || 0.82) * 0.78;
        el = mk("rect", { x: n.x - w / 2, y: n.y - h / 2, width: w, height: h });
      }
      el.setAttribute("fill", "#FBF9F3");
      el.setAttribute("stroke", "#16150F");
      if (n.plan) el.setAttribute("fill-opacity", "0");
      nd2[id] = el;
    }
    const capM2 = mk("circle", { r: 0.14, fill: "#2B35F0" });
    const capD2 = mk("circle", { r: 0.14, fill: "#16150F" });
    host.appendChild(svg);
    this.plano = { svg, g2: g, zone2, e2, nd2, capM2, capD2 };
  }

  private build3D(T: typeof THREE) {
    const cv = this.canvasRef.current;
    if (!cv || !this.geo) throw new Error("no canvas");
    const r = new T.WebGLRenderer({ canvas: cv, antialias: true });
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    r.setClearColor(0xf0ece3, 1);
    r.shadowMap.enabled = true;
    r.shadowMap.type = T.PCFSoftShadowMap;
    const sc = new T.Scene();
    sc.fog = new T.Fog(0xf0ece3, 36, 84);
    const cam = new T.PerspectiveCamera(32, 1, 0.1, 220);
    sc.add(new T.HemisphereLight(0xffffff, 0xcfc6b4, 1.3));
    const dl = new T.DirectionalLight(0xffffff, 1.6);
    dl.position.set(4, 16, 9);
    dl.target.position.set(8.1, 0, 2.6);
    dl.castShadow = true;
    dl.shadow.mapSize.set(2048, 2048);
    Object.assign(dl.shadow.camera, { left: -14, right: 14, top: 11, bottom: -11, near: 1, far: 42 });
    dl.shadow.bias = -0.0006;
    sc.add(dl, dl.target);
    const ground = new T.Mesh(new T.PlaneGeometry(240, 240), new T.ShadowMaterial({ opacity: 0.14 }));
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    sc.add(ground);
    const grid = new T.GridHelper(72, 72, 0xd3cbbc, 0xdfd8ca);
    grid.position.set(8.1, 0.002, 2.6);
    sc.add(grid);
    const INK = 0x16150f;
    const zg = new T.BoxGeometry(13, 0.05, 4.9);
    const zone = new T.Mesh(zg, new T.MeshStandardMaterial({ color: 0xf6f3eb, roughness: 1 }));
    zone.position.set(10.7, 0.025, 1.45);
    zone.receiveShadow = true;
    sc.add(zone);
    const ze = new T.LineSegments(new T.EdgesGeometry(zg), new T.LineBasicMaterial({ color: INK }));
    ze.position.copy(zone.position);
    sc.add(ze);
    const n3: Cena3D["n3"] = {};
    for (const id of IDS_DOS_NOS) {
      const d = NOS[id];
      const grp = new T.Group();
      grp.position.set(d.x, 0, d.y);
      const parts: { geo: THREE.BufferGeometry; y: number; x: number; z: number }[] = [];
      const add = (geo: THREE.BufferGeometry, y: number, x = 0, z = 0) => parts.push({ geo, y, x, z });
      if (d.k === "screen") {
        add(new T.BoxGeometry(1.0, 0.68, 0.08), 0.5);
        add(new T.BoxGeometry(0.34, 0.14, 0.26), 0.07);
      } else if (d.k === "gate") {
        add(new T.BoxGeometry(0.16, 0.95, 0.16), 0.475, 0, -0.42);
        add(new T.BoxGeometry(0.16, 0.95, 0.16), 0.475, 0, 0.42);
        add(new T.BoxGeometry(0.2, 0.16, 1.04), 1.02);
      } else if (d.k === "db") add(new T.CylinderGeometry(0.62, 0.62, 0.82, 48), 0.41);
      else if (d.k === "bucket") add(new T.CylinderGeometry(0.55, 0.4, 0.62, 40), 0.31);
      else if (d.k === "sheet") [0, 1, 2].forEach((i) => add(new T.BoxGeometry(0.86, 0.07, 0.64), 0.05 + i * 0.1, i * 0.03, -i * 0.03));
      else {
        const w = d.w || 0.82;
        const h = d.h || 0.5;
        add(new T.BoxGeometry(w, h, w), h / 2);
      }
      const mat = new T.MeshStandardMaterial({
        color: 0xfbf9f3,
        roughness: 0.82,
        metalness: 0,
        transparent: !!d.plan,
        opacity: d.plan ? 0 : 1,
        emissive: 0x000000,
      });
      const lmat = d.plan
        ? new T.LineDashedMaterial({ color: INK, dashSize: 0.07, gapSize: 0.05 })
        : new T.LineBasicMaterial({ color: INK });
      parts.forEach((p) => {
        const m = new T.Mesh(p.geo, mat);
        m.position.set(p.x, p.y, p.z);
        m.castShadow = !d.plan;
        m.receiveShadow = true;
        grp.add(m);
        const l = new T.LineSegments(new T.EdgesGeometry(p.geo, 25), lmat);
        l.position.copy(m.position);
        if (d.plan) l.computeLineDistances();
        grp.add(l);
      });
      if (d.k === "db")
        [0.27, 0.55].forEach((y) => {
          const pts: THREE.Vector3[] = [];
          for (let i = 0; i < 64; i++)
            pts.push(new T.Vector3(Math.cos((i / 64) * Math.PI * 2) * 0.625, y, Math.sin((i / 64) * Math.PI * 2) * 0.625));
          grp.add(new T.LineLoop(new T.BufferGeometry().setFromPoints(pts), new T.LineBasicMaterial({ color: INK })));
        });
      sc.add(grp);
      const top =
        d.k === "gate" ? 1.12 : d.k === "db" ? 0.84 : d.k === "screen" ? 0.86 : d.k === "bucket" ? 0.64 : d.k === "sheet" ? 0.3 : d.h || 0.5;
      n3[id] = { mat, lit: 0, top };
    }
    const e3 = this.geo.edges.map((e) => {
      const curve = new T.CatmullRomCurve3(e.pts.map((p) => new T.Vector3(p[0], p[1], p[2])));
      const seg = 64;
      const rad = 8;
      sc.add(
        new T.Mesh(
          new T.TubeGeometry(curve, seg, 0.12, 14, false),
          new T.MeshStandardMaterial({ color: 0xffffff, transparent: true, opacity: e.ty === "p" ? 0.1 : 0.32, roughness: 0.15, depthWrite: false }),
        ),
      );
      const dashed = e.ty === "c" || e.ty === "p";
      const line = new T.Line(
        new T.BufferGeometry().setFromPoints(curve.getPoints(90)),
        dashed
          ? new T.LineDashedMaterial({ color: INK, dashSize: e.ty === "p" ? 0.1 : 0.05, gapSize: 0.07 })
          : new T.LineBasicMaterial({ color: 0x8c8577 }),
      );
      if (dashed) line.computeLineDistances();
      sc.add(line);
      const coreGeo = new T.TubeGeometry(curve, seg, 0.055, rad, false);
      const coreMat = new T.MeshBasicMaterial({ color: 0x2b35f0 });
      coreGeo.setDrawRange(0, 0);
      sc.add(new T.Mesh(coreGeo, coreMat));
      return { coreGeo, coreMat, seg, rad };
    });
    const capGeo = new T.CapsuleGeometry(0.085, 0.24, 6, 14);
    const capM = new T.Mesh(capGeo, new T.MeshStandardMaterial({ color: 0x2b35f0, roughness: 0.35, emissive: 0x2b35f0, emissiveIntensity: 0.25 }));
    capM.castShadow = true;
    sc.add(capM);
    const capD = new T.Mesh(capGeo, new T.MeshStandardMaterial({ color: 0x16150f, roughness: 0.4 }));
    capD.castShadow = true;
    sc.add(capD);
    this.tres = {
      T,
      renderer: r,
      scene: sc,
      cam,
      n3,
      e3,
      capM,
      capD,
      cBase: new T.Color(0xfbf9f3),
      cCob: new T.Color(0x2b35f0),
      cVer: new T.Color(0xff5520),
      cHov: new T.Color(0xc9ccff),
      tmpV: new T.Vector3(),
      upV: new T.Vector3(0, 1, 0),
    };
    this.resize();
  }

  private resize() {
    if (!this.tres) return;
    const W = innerWidth;
    const H = innerHeight;
    this.tres.renderer.setSize(W, H, false);
    this.tres.cam.aspect = W / H;
    this.tres.cam.updateProjectionMatrix();
  }

  private tick = (now: number) => {
    this.raf = requestAnimationFrame(this.tick);
    const geo = this.geo;
    const stage = this.stageRef.current;
    if (!geo || !stage) return;
    const W = innerWidth;
    const H = innerHeight;
    const de = document.documentElement;
    const max = de.scrollHeight - H;
    if (this.progRef.current) this.progRef.current.style.width = (max > 0 ? Math.min(100, (scrollY / max) * 100) : 0) + "%";
    this.receiptTick(H);
    const bl = this.blocks;
    const ultimo = bl[bl.length - 1];
    if (bl.length < 17 || !ultimo) return;
    const lastR = ultimo.getBoundingClientRect();
    const visible = lastR.bottom > 60;
    const vis = visible ? "visible" : "hidden";
    if (stage.style.visibility !== vis) {
      stage.style.visibility = vis;
      if (this.labelsRef.current) this.labelsRef.current.style.visibility = vis;
    }
    if (!visible) return;
    const cs = bl.map((b) => {
      const rr = b.getBoundingClientRect();
      return rr.top + rr.height / 2 - H / 2;
    });
    const c = (i: number) => cs[i] ?? 0;
    let s = 0;
    if (c(0) >= 0) s = 0;
    else if (c(cs.length - 1) <= 0) s = cs.length - 1;
    else
      for (let i = 0; i < cs.length - 1; i++)
        if (c(i) <= 0 && c(i + 1) > 0) {
          s = i + -c(i) / (c(i + 1) - c(i));
          break;
        }
    const stat = this.mode === "2d" && !this.state.motion;
    let i = Math.floor(s);
    let f = s - i;
    if (i >= 16) {
      i = 15;
      f = 1;
    }
    let e = suavizar(Math.max(0, Math.min(1, (f - 0.18) / 0.64)));
    if (stat) e = f < 0.5 ? 0 : 1;
    const A = quadro(i, W, H, geo.msgR, geo.dataR, NOS);
    const B = quadro(i + 1, W, H, geo.msgR, geo.dataR, NOS);
    const lp = (a: number, b: number) => a + (b - a) * e;
    const goal: Camera = {
      x: lp(A.tg[0], B.tg[0]),
      y: lp(A.tg[1], B.tg[1]),
      z: lp(A.tg[2], B.tg[2]),
      r: lp(A.r, B.r),
      th: lp(A.th, B.th),
      ph: lp(A.ph, B.ph),
      ox: lp(A.ox, B.ox),
      oy: lp(A.oy, B.oy),
      mu: lp(A.mu, B.mu),
      du: lp(A.du, B.du),
    };
    const cv = this.cv || (this.cv = { ...goal });
    const k = this.snap || stat ? 1 : 0.13;
    this.snap = false;
    for (const key of CHAVES_DA_CAMERA) cv[key] += (goal[key] - cv[key]) * k;
    const activeNode = e < 0.5 ? A.node : B.node;
    let um = cv.mu;
    const ud = cv.du;
    let set: readonly IdDoNo[] | null = null;
    let human = false;
    let reader = false;
    let leitura: CaminhoDoTurno["leitura"] = "regras";
    const inOv = s > 15.5;
    if (this.demo && inOv) {
      const p = Math.max(0, Math.min(1, (now - this.demo.t0) / 3400));
      um = suavizar(p);
      set = this.demo.caminho.nos;
      human = this.demo.caminho.humano;
      leitura = this.demo.caminho.leitura;
      reader = leitura !== "regras";
    }
    const MR = (id: IdDoNo) => geo.msgR.par[id] ?? 0;
    const DR = (id: IdDoNo) => geo.dataR.par[id] ?? 0;
    const lit: Partial<Record<IdDoNo, 1>> = {};
    const msgOn = s > 1.6;
    const dataOn = s > 10.55;
    MENSAGEM.forEach((id) => {
      if (msgOn && um >= MR(id) - 0.001 && (!set || set.includes(id))) lit[id] = 1;
    });
    if (reader && um >= MR("regras")) lit.leitor = 1;
    if (leitura === "llm" && um >= MR("regras")) lit.llm = 1;
    DADOS.forEach((id) => {
      if (dataOn && ud >= DR(id) - 0.001) lit[id] = 1;
    });
    const humanFrom = MR("politica");
    const coreP = geo.edges.map((ed) => {
      if (ed.ty === "m") {
        if (!msgOn) return 0;
        const pa = MR(ed.a);
        const pb = MR(ed.b);
        return Math.max(0, Math.min(1, (um - pa) / (pb - pa)));
      }
      if (ed.ty === "d") {
        if (!dataOn) return 0;
        const pa = DR(ed.a);
        const pb = DR(ed.b);
        return Math.max(0, Math.min(1, (ud - pa) / (pb - pa)));
      }
      if ((ed.ty === "c" || ed.ty === "l") && reader) {
        const p = Math.max(0, Math.min(1, (um - MR("regras")) / (MR("etapas") - MR("regras"))));
        // Lido pelo LLM (só na conversa de verdade): regras → leitor → LLM → etapas, em terços.
        if (leitura === "llm") {
          if (ed.a === "regras") return Math.min(1, p * 3);
          if (ed.ty === "l") return Math.max(0, Math.min(1, p * 3 - (ed.a === "leitor" ? 1 : 2)));
          return 0;
        }
        if (ed.ty === "l") return 0;
        return ed.a === "regras" ? Math.min(1, p * 2) : Math.max(0, p * 2 - 1);
      }
      return 0;
    });
    const coreH = geo.edges.map((ed) => human && ed.ty === "m" && MR(ed.a) >= humanFrom - 0.001);
    const isHumanNode = (id: IdDoNo) => human && ["politica", "acoes", "banco"].includes(id) && !!lit[id];
    const capM = pontoNoCaminho(geo.msgR, um);
    const capD = pontoNoCaminho(geo.dataR, ud);
    const wide = cv.r > 13;
    const tgt = [cv.x, cv.y, cv.z] as const;
    let project: Projecao;
    const t3 = this.tres;
    const p2 = this.plano;
    if (this.mode === "3d" && t3) {
      const cam = t3.cam;
      const th = (cv.th * Math.PI) / 180;
      const ph = (cv.ph * Math.PI) / 180;
      cam.position.set(cv.x + cv.r * Math.cos(ph) * Math.sin(th), cv.y + cv.r * Math.sin(ph), cv.z + cv.r * Math.cos(ph) * Math.cos(th));
      cam.lookAt(cv.x, cv.y, cv.z);
      cam.setViewOffset(W, H, cv.ox * W, cv.oy * H, W, H);
      for (const id of IDS_DOS_NOS) {
        const n = t3.n3[id];
        if (!n) continue;
        n.lit += ((lit[id] ? 1 : 0) - n.lit) * 0.1;
        n.mat.color.copy(t3.cBase).lerp(isHumanNode(id) ? t3.cVer : t3.cCob, n.lit);
        if (this.hover === id && n.lit < 0.5) n.mat.color.lerp(t3.cHov, 0.6);
      }
      t3.e3.forEach((cc, j) => {
        const p = coreP[j] ?? 0;
        cc.coreGeo.setDrawRange(0, Math.floor(p * cc.seg) * cc.rad * 6);
        cc.coreMat.color.copy(coreH[j] ? t3.cVer : t3.cCob);
      });
      t3.capM.visible = msgOn;
      t3.capM.position.set(capM.p[0], capM.p[1], capM.p[2]);
      t3.tmpV.set(capM.d[0], capM.d[1], capM.d[2]);
      if (t3.tmpV.lengthSq() > 1e-8) t3.capM.quaternion.setFromUnitVectors(t3.upV, t3.tmpV.normalize());
      t3.capM.material.color.copy(human && um >= humanFrom ? t3.cVer : t3.cCob);
      t3.capM.material.emissive.copy(t3.capM.material.color);
      t3.capD.visible = dataOn;
      t3.capD.position.set(capD.p[0], capD.p[1], capD.p[2]);
      t3.tmpV.set(capD.d[0], capD.d[1], capD.d[2]);
      if (t3.tmpV.lengthSq() > 1e-8) t3.capD.quaternion.setFromUnitVectors(t3.upV, t3.tmpV.normalize());
      t3.renderer.render(t3.scene, cam);
      const v = t3.tmpV;
      project = (x, y, z) => {
        v.set(x, y, z).project(cam);
        return { sx: ((v.x + 1) / 2) * W, sy: ((1 - v.y) / 2) * H, ok: v.z < 1 && Math.abs(v.x) < 1.15 && Math.abs(v.y) < 1.15 };
      };
    } else if (p2) {
      let sc: number;
      let cx: number;
      let cy: number;
      let ox: number;
      let oy: number;
      if (stat) {
        sc = Math.min((W - 40) / 19.5, (H - 200) / 8.2);
        cx = 8.1;
        cy = 2.6;
        ox = 0;
        oy = -0.02;
      } else {
        sc = Math.min(W, 1.6 * H) / (cv.r * (cv.r < 13 ? 1.55 : 1.0));
        cx = cv.x;
        cy = cv.z;
        ox = cv.ox;
        oy = cv.oy;
      }
      const tx = W / 2 - ox * W;
      const ty = H / 2 - oy * H;
      const inv = 1 / sc;
      p2.g2.setAttribute("transform", "translate(" + tx + " " + ty + ") scale(" + sc + ") translate(" + -cx + " " + -cy + ")");
      p2.zone2.setAttribute("stroke-width", String(inv));
      p2.e2.forEach((o, j) => {
        o.base.setAttribute("stroke-width", String((o.solid ? 7 : 1.3) * inv));
        if (!o.solid) o.base.setAttribute("stroke-dasharray", (o.ty === "p" ? 6 : 3) * inv + " " + 4 * inv);
        o.core.setAttribute("stroke-width", String(3.4 * inv));
        o.core.setAttribute("stroke-dashoffset", String(o.L * (1 - (coreP[j] ?? 0))));
        o.core.setAttribute("stroke", coreH[j] ? "#FF5520" : "#2B35F0");
      });
      for (const id of IDS_DOS_NOS) {
        const el = p2.nd2[id];
        if (!el) continue;
        el.setAttribute("stroke-width", String(1.3 * inv));
        if (NOS[id].plan) el.setAttribute("stroke-dasharray", 4 * inv + " " + 3 * inv);
        el.setAttribute("fill", lit[id] ? (isHumanNode(id) ? "#FF5520" : "#2B35F0") : this.hover === id ? "#E3E4FF" : "#FBF9F3");
      }
      p2.capM2.setAttribute("cx", String(capM.p[0]));
      p2.capM2.setAttribute("cy", String(capM.p[2]));
      p2.capM2.setAttribute("r", String(6 * inv));
      p2.capM2.style.display = msgOn ? "" : "none";
      p2.capM2.setAttribute("fill", human && um >= humanFrom ? "#FF5520" : "#2B35F0");
      p2.capM2.setAttribute("stroke", "#F0ECE3");
      p2.capM2.setAttribute("stroke-width", String(2 * inv));
      p2.capD2.setAttribute("cx", String(capD.p[0]));
      p2.capD2.setAttribute("cy", String(capD.p[2]));
      p2.capD2.setAttribute("r", String(6 * inv));
      p2.capD2.style.display = dataOn ? "" : "none";
      project = (x, y, z) => ({ sx: tx + (x - cx) * sc, sy: ty + (z - cy) * sc - (y > 0.3 ? Math.min(30, sc * 0.45) : 0), ok: true });
    } else return;
    const wideL = wide || stat;
    for (const id of IDS_DOS_NOS) {
      const L = this.lbls[id];
      if (!L) continue;
      const n = NOS[id];
      const top = this.tres?.n3[id]?.top ?? 0.6;
      const pr = project(n.x, top + 0.34, n.y);
      const near = wideL || Math.hypot(n.x - tgt[0], n.y - tgt[2]) < 6.8;
      const on = pr.ok && near && pr.sx > -80 && pr.sx < W + 80 && pr.sy > 40 && pr.sy < H + 40;
      L.el.style.transform = "translate(" + pr.sx.toFixed(1) + "px," + pr.sy.toFixed(1) + "px) translate(-50%,-100%)";
      const act = id === activeNode && !wideL;
      const hum = isHumanNode(id);
      const sig = (on ? 1 : 0) + "|" + (act ? 1 : 0) + "|" + (lit[id] ? 1 : 0) + "|" + (hum ? 1 : 0) + "|" + (wideL ? 1 : 0);
      if (L.last !== sig) {
        L.last = sig;
        L.el.style.opacity = on ? "1" : "0";
        L.el.style.pointerEvents = on ? "auto" : "none";
        L.el.style.background = act ? "#16150F" : "#F7F4EC";
        L.el.style.color = act ? "#F7F4EC" : "#16150F";
        L.el.style.borderColor = hum ? "#FF5520" : lit[id] ? "#2B35F0" : "#16150F";
        L.el.style.boxShadow = lit[id] ? (hum ? "inset 0 -3px 0 #FF5520" : "inset 0 -3px 0 #2B35F0") : "none";
        if (L.sub) L.sub.style.display = wideL ? "none" : "block";
      }
    }
    if (this.zoneRef.current) {
      const pz = project(4.45, 0.1, -0.85);
      this.zoneRef.current.style.transform = "translate(" + pz.sx.toFixed(1) + "px," + pz.sy.toFixed(1) + "px)";
      this.zoneRef.current.style.opacity = pz.ok && cv.r > 7.5 ? "1" : "0";
    }
  };

  private receiptTick(H: number) {
    const el = this.receiptRef.current;
    if (!el) return;
    const sec = el.closest("[data-stop]");
    if (!sec) return;
    const r = sec.getBoundingClientRect();
    let p = (H * 0.78 - r.top) / (r.height * 0.5);
    p = Math.max(0, Math.min(1, p));
    if (!this.state.motion) p = 1;
    const v = "inset(0 0 " + ((1 - p) * 100).toFixed(2) + "% 0)";
    if (el.style.clipPath !== v) el.style.clipPath = v;
  }

  private setLang(l: Idioma) {
    try {
      localStorage.setItem("jeje.site.lang", l);
    } catch {
      // sem armazenamento: a escolha vale só nesta visita
    }
    this.setState({ lang: l, convLang: l === "pt" ? "pt" : l === "es" ? "es" : this.state.convLang });
  }

  private toggleMotion = () => {
    const m = !this.state.motion;
    try {
      localStorage.setItem("jeje.site.motion", m ? "1" : "0");
    } catch {
      // sem armazenamento: a escolha vale só nesta visita
    }
    this.setState({ motion: m });
  };

  private openSrc(id: string) {
    this.setState({ src: id });
  }

  private goModels(i: number) {
    this.setState({ model: i, drawer: null });
    const el = document.getElementById("modelos");
    if (el) window.scrollTo({ top: el.getBoundingClientRect().top + scrollY - 56, behavior: this.state.motion ? "smooth" : "auto" });
  }

  private goMap() {
    const bl = this.blocks;
    const mapa = bl[16];
    if (bl.length < 17 || !mapa) return 0;
    const r = mapa.getBoundingClientRect();
    const target = scrollY + r.top + r.height / 2 - innerHeight / 2 + 10;
    if (Math.abs(target - scrollY) > 40) {
      window.scrollTo({ top: target, behavior: this.state.motion ? "smooth" : "auto" });
      return this.state.motion ? 1000 : 0;
    }
    return 0;
  }

  private detectLang(t?: string): IdiomaDaConversa | null {
    return t ? idiomaDaFrase(t) : null;
  }

  private match(t: string): IdDaJornada {
    const s = t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    const R: [IdDaJornada, RegExp][] = [
      ["injecao", /ignor|instruc|prompt|reembols/],
      ["desbloq", /desbloq/],
      ["fraude", /robaron|roubar|robo|roubo|perdi|clonar|clonaram|fraud|furt/],
      ["bloquear", /bloq/],
      ["repetida", /dos veces|duas vezes|duplicad|repetid/],
      ["contestar", /no reconozco|nao reconhe|desconozco|nao fiz|no hice|contest|impugn|no reconoc/],
      ["ambiguo", /rechaz|recus|negad|declin/],
      ["acompanhar", /solicitud|pedido|como va|como esta|protocolo|status/],
      ["escopo", /prestamo|emprestimo|credito|inversi|invest|senha|contrasena|clave/],
      ["humano", /agente|atendente|humano|persona|pessoa/],
    ];
    for (const [id, re] of R) if (re.test(s)) return id;
    return "ajuda";
  }

  /** Uma jornada de exemplo do design (com `jaMostrada`, a fala do cliente já está na conversa). */
  private send(id: IdDaJornada, text?: string, jaMostrada = false) {
    const j = CONTEUDO_DO_SITE.journeys[id];
    const cl = this.detectLang(text) || this.state.convLang;
    const msg = text || (j.msg ? j.msg[cl] : "");
    const novos: ItemDaConversa[] = jaMostrada
      ? [{ who: "s", id, lang: cl }]
      : [
          { who: "c", text: msg },
          { who: "s", id, lang: cl },
        ];
    this.setState(
      (s) => ({
        conv: s.conv.map((m): ItemDaConversa => (m.who === "c" ? m : { ...m, done: true })).concat(novos),
        dockOpen: true,
        convLang: cl,
        draft: "",
      }),
      () => {
        const el = this.convRef.current;
        if (el) el.scrollTop = el.scrollHeight;
      },
    );
    const delay = this.goMap();
    this.demo = { t0: performance.now() + delay, caminho: caminhoDaJornada(j.turn.route, id, !!j.turn.human) };
  }

  private pickOpt(o: { readonly next: IdDaJornada | null }, label: string) {
    if (o.next) {
      this.send(o.next, label);
      return;
    }
    const conv = this.state.conv
      .map((m): ItemDaConversa => (m.who === "s" ? { ...m, done: true } : m))
      .concat([{ who: "c", text: label }]);
    this.setState({ conv });
  }

  /** A conversa fala com a API de verdade (acesso aberto) ou mostra as jornadas de exemplo do design. */
  private aoVivo() {
    return !SO_DESIGN && this.state.acesso === "aberto";
  }

  private async garantirSessao() {
    if (this.sessao) return this.sessao;
    const persona = escolherPersona(await listarPersonas());
    if (!persona) throw new Error("sem personas de demonstração");
    const aberta = await abrirSessao(persona.customer_id, "cadastrado");
    this.sessao = { token: aberta.token, persona };
    return this.sessao;
  }

  private async garantirConversa(token: string, idioma: IdiomaDaConversa) {
    if (this.conversa && this.conversa.idioma === idioma) return this.conversa;
    const aberta = await abrirConversa(token, idioma);
    this.conversa = { id: aberta.conversa_id, idioma };
    return this.conversa;
  }

  /** Acrescenta falas à conversa, com as anteriores do sistema já respondidas (sem opções). */
  private mostrar(itens: ItemDaConversa[]) {
    this.setState(
      (s) => ({ conv: s.conv.map((m): ItemDaConversa => (m.who === "c" ? m : { ...m, done: true })).concat(itens) }),
      () => {
        const el = this.convRef.current;
        if (el) el.scrollTop = el.scrollHeight;
      },
    );
  }

  /**
   * Um turno de verdade: a sessão de uma persona de demonstração, a conversa na língua da mensagem e o
   * turno pela API; o mapa acende o caminho que o turno fez. Sem o acesso, volta às jornadas de exemplo.
   */
  private async enviarAoVivo(
    montar: (persona: PersonaDaDemo) => string,
    idioma: IdiomaDaConversa,
    exemplo: IdDaJornada,
    digitado?: string,
  ) {
    if (this.enviando) return;
    this.enviando = true;
    const inicio = performance.now();
    this.setState({ dockOpen: true, convLang: idioma, draft: "" });
    const delay = this.goMap();
    let mostrado = "";
    try {
      const sessao = await this.garantirSessao();
      const texto = montar(sessao.persona);
      this.mostrar([{ who: "c", text: texto }]);
      mostrado = texto;
      const conversa = await this.garantirConversa(sessao.token, idioma);
      const turno = await enviarMensagem(sessao.token, conversa.id, texto);
      if (turno.estado === "encerrada") this.conversa = null;
      this.mostrar([{ who: "v", turno }]);
      this.demo = { t0: Math.max(performance.now(), inicio + delay), caminho: caminhoDoTurno(turno) };
    } catch (e) {
      if (e instanceof AcessoRestrito || e instanceof SessaoExpirada) {
        // Sem o acesso (ou com a sessão vencida), a conversa segue com os exemplos do design.
        this.sessao = null;
        this.conversa = null;
        if (e instanceof AcessoRestrito) this.setState({ acesso: "fechado" });
        this.send(exemplo, mostrado || digitado, mostrado !== "");
      } else this.mostrar([{ who: "e", text: TRANSACAO_AO_VIVO.erro[this.state.lang] }]);
    } finally {
      this.enviando = false;
    }
  }

  /** Um atalho: na conversa de verdade, a contestação usa uma compra da própria persona. */
  private atalho(id: IdDaJornada) {
    if (!this.aoVivo()) {
      this.send(id);
      return;
    }
    const idioma = this.state.convLang;
    const desenho = CONTEUDO_DO_SITE.journeys[id].msg?.[idioma] ?? "";
    void this.enviarAoVivo(
      (p) => (id === "contestar" && p.exemplo ? frasesDoExemplo(p.exemplo)[idioma === "es" ? 0 : 1] : desenho),
      idioma,
      id,
    );
  }

  /** O que o cliente digitou (ou o texto da injeção do pilar de segurança). */
  private digitado(texto: string) {
    if (!this.aoVivo()) {
      this.send(this.match(texto), texto);
      return;
    }
    void this.enviarAoVivo(() => texto, this.detectLang(texto) || this.state.convLang, this.match(texto), texto);
  }

  private runRepro = () => {
    clearInterval(this.rt);
    const n = CONTEUDO_DO_SITE.pillars.rep.lines.length;
    if (!this.state.motion) {
      this.setState({ reproN: n });
      return;
    }
    this.setState({ reproN: 0 });
    let k = 0;
    this.rt = setInterval(() => {
      k++;
      this.setState({ reproN: k });
      if (k >= n) clearInterval(this.rt);
    }, 420);
  };

  /** Um turno da API no balão do design: a resposta, as opções e o "Por que esta resposta?". */
  private falaDeVerdade(tr: ResultadoDoTurno, ultima: boolean, t: ReturnType<typeof resolver>, ruleDesc: Record<string, string>): FalaNaTela {
    const S = this.state;
    const R = t.receipt;
    const L = S.lang;
    const res = tr.resolucao;
    const transacao =
      tr.opcoes.length > 0
        ? tr.opcoes.length + " " + TRANSACAO_AO_VIVO.possiveis[L]
        : res
          ? res.resolvedor === "ranking"
            ? (tr.transaction_id ? TRANSACAO_AO_VIVO.ranking : TRANSACAO_AO_VIVO.semGarantia)[L]
            : TRANSACAO_AO_VIVO[res.resolvedor][L]
          : (tr.transaction_id ?? "—");
    const rows: [string, string][] = [
      [R.f.lang, tr.idioma],
      [R.f.reader, tr.interpretacao],
      [R.f.intent, tr.intencao],
      [R.f.txn, transacao],
      [R.f.rule, tr.regra],
      ["", tr.descricao ?? ruleDesc[tr.regra] ?? ""],
      [R.f.action, tr.acao],
      [R.f.effect, tr.efeito ?? "—"],
    ];
    if (tr.protocolo) rows.push([R.f.protocol, tr.protocolo]);
    if (tr.recibo) {
      rows.push([R.f.file, tr.recibo.arquivo]);
      rows.push([R.f.line, String(tr.recibo.linha)]);
    }
    rows.push([R.f.version, tr.recibo?.versao_dos_dados?.slice(0, 12) ?? "—"]);
    const i = tr.idioma;
    const manda = (envia: string) => () => void this.enviarAoVivo(() => envia, i, "ajuda");
    const opts = !ultima
      ? []
      : tr.opcoes.length > 0
        ? tr.opcoes.map((o) => ({ l: o.descricao, pick: manda(String(o.numero)) }))
        : tr.estado === "confirmando" || tr.estado === "confirmando_desbloqueio"
          ? [
              { l: RESPOSTAS.confirmar[i], pick: manda(RESPOSTAS.confirmar[i]) },
              { l: RESPOSTAS.nao[i], pick: manda(RESPOSTAS.nao[i]) },
            ]
          : tr.estado === "oferecendo_humano"
            ? [
                { l: RESPOSTAS.humano[i], pick: manda(RESPOSTAS.sim[i]) },
                { l: RESPOSTAS.seguir[i], pick: manda(RESPOSTAS.nao[i]) },
              ]
            : [];
    const k = S.conv.findIndex((c) => c.who === "v" && c.turno === tr);
    const wo = !!S.whyOpen[k];
    const human = tr.acao === "humano" || tr.atendimento != null || tr.estado === "com_humano";
    return {
      isC: false,
      isS: true,
      text: tr.resposta,
      human,
      humanL: t.rules.cats.h,
      bc: human ? "#FF5520" : "#16150F",
      rows: rows.map((r) => ({ k: r[0], v: r[1] })),
      hasOpts: opts.length > 0,
      opts,
      whyL: t.dock.why,
      whyArrow: wo ? "↑" : "↓",
      whyOpen: wo,
      toggleWhy: () => this.setState({ whyOpen: { ...S.whyOpen, [k]: !wo } }),
    };
  }

  private renderVals() {
    const S = this.state;
    const mob = S.vw < 760;
    const L = {
      wideInline: mob ? "none" : "inline",
      wideFlex: mob ? "none" : "flex",
      langMargin: mob ? "auto" : "0",
      cardAlign: mob ? "flex-end" : "center",
      padBottom: mob ? "92px" : "64px",
      mapBody: mob ? "none" : "block",
    };
    const vivo = this.aoVivo();
    const doSite = comNumerosAoVivo(resolver(CONTEUDO_DO_SITE, S.lang), S.numeros, S.lang);
    const t = vivo ? { ...doSite, dock: { ...doSite.dock, note: doSite.dock.noteLive ?? doSite.dock.note } } : doSite;
    const C = CONTEUDO_DO_SITE;
    const cl = S.convLang;
    const ink = "#16150F";
    const paper = "#F7F4EC";
    const cob = "#2B35F0";
    const ver = "#FF5520";
    const kindStyle: Record<TipoDeFonte, readonly [string, string, string]> = {
      live: [cob, "#fff", "solid"],
      evid: [ink, paper, "solid"],
      code: [paper, ink, "solid"],
      plan: [paper, ink, "dashed"],
      ref: [paper, ink, "dotted"],
      team: ["#E3E4FF", ink, "solid"],
      pending: [ver, ink, "solid"],
    };
    const srcBtn = (s: string) => () => this.openSrc(s);
    const ruleDesc: Record<string, string> = {};
    t.rules.list.forEach((r) => {
      ruleDesc[r[0]] = r[2];
    });
    const phraseLang = S.lang === "pt" ? "pt" : "es";

    const R = t.receipt;
    const st = S.confirmed === true ? R.yes : S.confirmed === false ? R.no : R.wait;
    const jt = t.journeys.contestar.turn;
    const rcRows = [
      { k: R.f.req, v: "c1f4e2a9-7b0d" },
      { k: R.f.lang, v: phraseLang },
      { k: R.f.reader, v: jt.reader },
      { k: R.f.intent, v: jt.intent },
      { k: R.f.txn, v: jt.txn },
      { k: R.f.rule, v: "POL-DISP-01" },
      { k: R.f.action, v: st.action },
      { k: R.f.effect, v: st.effect, c: S.confirmed === true ? cob : S.confirmed === false ? ink : ink, w: 700 },
      { k: R.f.protocol, v: st.protocol },
    ].map((r) => ({ c: ink, w: 400, ...r }));
    const stops = t.stops.map((s, i) => ({
      ...s,
      idx: 3 + i,
      num: String(i + 1).padStart(2, "0") + " / 08",
      minH: s.id === "banco" ? "170vh" : "108vh",
      align: L.cardAlign,
      padB: L.padBottom,
      lblProtects: t.ui.protects,
      lblHere: t.ui.thisMsg,
      hasHere: !!s.here,
      protects: s.protects || [],
      hasStat: !!s.stat,
      statV: s.stat ? s.stat.v : "",
      statL: s.stat ? s.stat.l : "",
      statS: s.stat ? s.stat.s : "",
      openStat: s.stat ? srcBtn(s.stat.s) : undefined,
      isLeitura: s.id === "leitura",
      isEtapas: s.id === "etapas",
      isQual: s.id === "qual",
      isPolitica: s.id === "politica",
      isAcao: s.id === "acao",
      isBanco: s.id === "banco",
      cascade: (s.cascade || []).map((c, k) => ({
        n: c.n,
        d: c.d,
        k: c.st === "on" ? "✓" : c.st === "plan" ? "◌" : "—",
        bg: c.st === "on" ? cob : "transparent",
        fg: c.st === "on" ? "#fff" : ink,
        bstyle: c.st === "plan" ? "dashed" : "solid",
        indent: k * 14 + "px",
      })),
      statesL: (s.states || []).map((x, k) => ({ x: k + 1 + " · " + x, bg: k === 0 ? cob : "transparent", fg: k === 0 ? "#fff" : ink })),
      cluesL: s.clues || [],
      openRules: () => this.setState({ drawer: "rules" }),
      onYes: () => this.setState({ confirmed: true }),
      onNo: () => this.setState({ confirmed: false }),
      yesBg: S.confirmed === true ? cob : "#FFFDF7",
      yesFg: S.confirmed === true ? "#fff" : cob,
      noBg: S.confirmed === false ? ink : "#FFFDF7",
      noFg: S.confirmed === false ? paper : ink,
      answered: S.confirmed !== null,
      ansText: S.confirmed === true ? s.afterYes : s.afterNo,
      ansColor: S.confirmed === true ? cob : ink,
      receiptRef: this.receiptRef,
      rcTitle: R.title,
      rcRows,
      rcFactsT: R.facts,
      rcFacts: [
        { k: R.f.file, v: "fixture/transacoes.csv" },
        { k: R.f.line, v: "212" },
        { k: R.f.version, v: "sint-2026.09 · 7c1e…a90b" },
      ],
      rcReplyT: R.reply,
      rcReply: st.reply,
      rcFoot: R.foot,
      rcFixture: R.fixture,
    }));
    const dataStops = t.dataStops.map((s, i) => ({
      ...s,
      idx: 11 + i,
      num: "D" + (i + 1) + " / 05",
      align: L.cardAlign,
      padB: L.padBottom,
      isFirst: i === 0,
      introK: t.dataIntro.kicker,
      introT: t.dataIntro.title,
      hasStat: !!s.stat,
      statV: s.stat ? s.stat.v : "",
      statL: s.stat ? s.stat.l : "",
      statS: s.stat ? s.stat.s : "",
      openStat: s.stat ? srcBtn(s.stat.s) : undefined,
    }));
    const labels = IDS_DOS_NOS.map((id) => ({
      id,
      name: t.nodes[id].n,
      sub: t.nodes[id].s,
      bs: NOS[id].plan ? "dashed" : "solid",
      open: () => this.setState({ drawer: id }),
      enter: () => {
        this.hover = id;
      },
      leave: () => {
        this.hover = null;
      },
    }));

    const chips = (Object.keys(C.journeys) as IdDaJornada[])
      .filter((k) => !C.journeys[k].hidden)
      .map((k) => ({ l: C.journeys[k].chip?.[cl] ?? "", go: () => this.atalho(k) }));
    const mlist = t.models.list;
    const m = mlist[S.model] ?? mlist[0];
    if (!m) throw new Error("conteúdo sem modelos");
    const primeiroPar = m.pairs?.[0];
    const primeiraEst = m.stats?.[0];
    const mmSrc = m.barsSrc || (primeiroPar ? primeiroPar.s : primeiraEst ? primeiraEst.s : "");
    const mm = {
      n: m.n,
      does: m.does,
      data: m.data,
      limit: m.limit,
      planned: !!m.planned,
      hasBy: !!m.by,
      byL: m.by ? (S.lang === "en" ? "by " : S.lang === "es" ? "de " : "de ") + m.by : "",
      hasStats: !!m.stats,
      stats: m.stats || [],
      hasBars: !!m.bars,
      bars: (m.bars || []).map((b) => ({ l: b.l, v: b.v, wp: b.w + "%" })),
      hasPairs: !!m.pairs,
      pairs: (m.pairs || []).map((p) => ({ l: p.l, aw: p.a + "%", bw: p.b + "%", av: p.av || p.a + "%", bv: p.bv || p.b + "%" })),
      legA: m.pairLegend ? m.pairLegend[0] : "",
      legB: m.pairLegend ? m.pairLegend[1] : "",
      note: m.barsNote || (m.stats ? "" : ""),
      src: mmSrc,
      openSrc: srcBtn(mmSrc),
    };
    const modelTabs = mlist.map((x, i2) => ({
      num: "0" + (i2 + 1),
      name: x.n,
      role: x.role,
      on: i2 === S.model,
      bg: i2 === S.model ? ink : "transparent",
      fg: i2 === S.model ? paper : ink,
      pick: () => this.setState({ model: i2 }),
    }));
    const P = t.pillars.list.map((p) => ({ ...p, proofs: p.proofs.map(([txt, s]) => ({ txt, s, open: srcBtn(s) })) }));
    const [P0, P1, P2, P3] = P;
    if (!P0 || !P1 || !P2 || !P3) throw new Error("conteúdo sem os quatro pilares");
    const rl = t.pillars.rep.lines;
    const reproLines = rl.slice(0, S.reproN).map((x, k) => ({
      t: x,
      c: k < 2 ? "#B9B3A6" : k === rl.length - 1 ? "#FF5520" : "#F0ECE3",
      w: k === rl.length - 1 ? 700 : 400,
    }));

    let dw: Gaveta = GAVETA_VAZIA;
    if (S.drawer === "rules") dw = { ...GAVETA_VAZIA, isRules: true, title: t.rules.title, kicker: "politica.py · DESCRICOES" };
    else if (S.drawer && t.nodes[S.drawer]) {
      const nd = t.nodes[S.drawer];
      const stp = t.stops.concat(t.dataStops).find((x) => x.id === nd.stop);
      const modelo = nd.model != null ? mlist[nd.model] : undefined;
      dw = {
        ...GAVETA_VAZIA,
        isNode: true,
        title: nd.n,
        sub: nd.s,
        kicker: stp?.tag || "",
        planned: !!nd.planned,
        does: stp?.does || "",
        protects: stp?.protects || [],
        hasStat: !!stp?.stat,
        statV: stp?.stat ? stp.stat.v : "",
        statL: stp?.stat ? stp.stat.l : "",
        statS: stp?.stat ? stp.stat.s : "",
        openStat: stp?.stat ? srcBtn(stp.stat.s) : undefined,
        hasModel: nd.model != null,
        modelLbl: modelo ? t.models.f.does + " · " + modelo.n : "",
        goModel: () => this.goModels(nd.model ?? 0),
      };
    }
    const cats: Record<CategoriaDeRegra, readonly [string, string, string]> = {
      c: [paper, ink, "solid"],
      q: ["#FFFDF7", ink, "dashed"],
      p: [cob, "#fff", "solid"],
      b: ["#E3E4FF", ink, "solid"],
      h: [ver, ink, "solid"],
    };
    const ruleRows = t.rules.list.map((r) => ({ id: r[0], d: r[2], bg: cats[r[1]][0], fg: cats[r[1]][1], bs: cats[r[1]][2] }));
    const ruleCats = (Object.keys(cats) as CategoriaDeRegra[]).map((k) => ({ l: t.rules.cats[k], bg: cats[k][0], bs: cats[k][2] }));
    let sv: Partial<Record<"id" | "where" | "kind" | "note" | "bg" | "fg" | "bs", string>> = {};
    const fonte = S.src ? C.sources[S.src] : undefined;
    if (S.src && fonte) {
      const ks = kindStyle[fonte[0]];
      sv = { id: S.src, where: fonte[1], kind: t.ui.kinds[fonte[0]], note: t.ui.kindNotes[fonte[0]], bg: ks[0], fg: ks[1], bs: ks[2] };
    }

    const lastS = (() => {
      for (let k = S.conv.length - 1; k >= 0; k--) if (S.conv[k]?.who !== "c") return k;
      return -1;
    })();
    const convItems = S.conv.map((c, k): FalaNaTela => {
      if (c.who === "c")
        return { isC: true, isS: false, text: c.text, human: false, humanL: "", bc: ink, rows: [], hasOpts: false, opts: [], whyL: "", whyArrow: "", whyOpen: false };
      if (c.who === "e")
        return { isC: false, isS: true, text: c.text, human: false, humanL: "", bc: ink, rows: [], hasOpts: false, opts: [], whyL: "", whyArrow: "", whyOpen: false };
      if (c.who === "v") return this.falaDeVerdade(c.turno, k === lastS && !c.done, t, ruleDesc);
      const j = t.journeys[c.id];
      const tr = j.turn;
      const rows: [string, string][] = [
        [R.f.lang, c.lang],
        [R.f.reader, tr.reader],
        [R.f.intent, tr.intent],
        [R.f.txn, tr.txn],
        [R.f.rule, tr.rule],
        ["", ruleDesc[tr.rule] || ""],
        [R.f.action, tr.action],
        [R.f.effect, tr.effect],
      ];
      if (tr.protocol) rows.push([R.f.protocol, tr.protocol]);
      rows.push([R.f.version, "sint-2026.09"]);
      const opts =
        !c.done && k === lastS && tr.options
          ? tr.options.map((o) => ({ l: o.l[c.lang], pick: () => this.pickOpt(o, o.l[c.lang]) }))
          : [];
      const wo = !!S.whyOpen[k];
      return {
        isC: false,
        isS: true,
        text: tr.reply[c.lang],
        human: !!tr.human,
        humanL: t.rules.cats.h,
        bc: tr.human ? ver : ink,
        rows: rows.map((r) => ({ k: r[0], v: r[1] })),
        hasOpts: opts.length > 0,
        opts,
        whyL: t.dock.why,
        whyArrow: wo ? "↑" : "↓",
        whyOpen: wo,
        toggleWhy: () => this.setState({ whyOpen: { ...S.whyOpen, [k]: !wo } }),
      };
    });

    return {
      L,
      t,
      appUrl: C.appUrl,
      guideUrl: C.guideUrl,
      appShort: mob ? "App" : t.ui.app,
      stageRef: this.stageRef,
      canvasRef: this.canvasRef,
      svgHostRef: this.svgHostRef,
      labelsRef: this.labelsRef,
      progRef: this.progRef,
      zoneRef: this.zoneRef,
      convRef: this.convRef,
      navItems: t.ui.nav,
      langs: (
        [
          ["pt", "PT"],
          ["es", "ES"],
          ["en", "EN"],
        ] as const
      ).map(([c, code]) => ({ code, on: S.lang === c, bg: S.lang === c ? ink : "transparent", fg: S.lang === c ? paper : ink, pick: () => this.setLang(c) })),
      motionOn: S.motion,
      motionLabel: S.motion ? t.ui.on : t.ui.off,
      toggleMotion: this.toggleMotion,
      hasGloss: !!t.intro.gloss,
      probStats: t.problem.stats.map((p) => ({ v: p.v, l: p.l, s: p.s, open: srcBtn(p.s) })),
      stops,
      dataStops,
      labels,
      chips,
      convLangUp: cl.toUpperCase(),
      legend: t.map.legend.map((g) => ({
        l: g.l,
        bg: g.k === "lit" ? cob : g.k === "human" ? ver : g.k === "plan" ? "transparent" : "#FBF9F3",
        bs: g.k === "plan" ? "dashed" : "solid",
      })),
      modelTabs,
      mm,
      P0,
      P1,
      P2,
      P3,
      obsRows: t.pillars.obs.rows.map((r) => ({ k: r.k, v: r.v, bg: S.obsOn ? "#E3E4FF" : "#FFFDF7", op: S.obsOn ? 1 : 0.5 })),
      toggleObs: () => this.setState({ obsOn: !S.obsOn }),
      op: S.mutant ? "<" : "<=",
      opBg: S.mutant ? ver : "transparent",
      testLabel: S.mutant ? t.pillars.conf.fail : t.pillars.conf.pass,
      testBg: S.mutant ? ver : cob,
      testFg: S.mutant ? ink : "#fff",
      plantLabel: S.mutant ? t.pillars.conf.undo : t.pillars.conf.plant,
      togglePlant: () => this.setState({ mutant: !S.mutant }),
      fails: t.pillars.conf.fails.map((f) => ({ a: f[0], b: f[1], c: f[2] })),
      injMsg: S.lang === "pt" ? t.pillars.seg.msg : C.pillars.seg.msg.es,
      injRes: t.pillars.seg.result.map((r) => ({ k: r[0], v: r[1] })),
      sendInj: () => {
        const msg = S.lang === "pt" ? C.pillars.seg.msg.pt : C.pillars.seg.msg.es;
        if (this.aoVivo()) this.digitado(msg);
        else this.send("injecao", msg);
      },
      openHonest: srcBtn("NOV-13"),
      reproLines,
      reproCursor: S.reproN >= rl.length ? "$ _" : S.reproN === 0 ? "$ _" : "…",
      runRepro: this.runRepro,
      resRows: t.results.rows.map((l) => ({ l, cells: t.results.cols.map((_c, k) => (k === 5 ? "— / 80" : "—")) })),
      outItems: t.results.out.map((o) => ({
        id: o[0],
        txt: o[1],
        tag: o[2],
        bs: C.sources[o[0]] && C.sources[o[0]]?.[0] === "plan" ? "dashed" : "solid",
        open: srcBtn(o[0]),
      })),
      hasDrawer: !!S.drawer,
      dw,
      closeDrawer: () => this.setState({ drawer: null }),
      ruleRows,
      ruleCats,
      hasSrc: !!S.src,
      sv,
      closeSrc: () => this.setState({ src: null }),
      dockOpen: S.dockOpen,
      toggleDock: () => this.setState({ dockOpen: !S.dockOpen }),
      convItems,
      convEmpty: S.conv.length === 0,
      convLangs: (
        [
          ["es", "ES"],
          ["pt", "PT"],
        ] as const
      ).map(([c, code]) => ({ code, bg: cl === c ? ink : "transparent", fg: cl === c ? paper : ink, pick: () => this.setState({ convLang: c }) })),
      newConv: () => {
        this.demo = null;
        this.conversa = null;
        this.setState({ conv: [], whyOpen: {} });
      },
      draft: S.draft,
      onDraft: (e: ChangeEvent<HTMLInputElement>) => this.setState({ draft: e.target.value }),
      onKey: (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") {
          const v = S.draft.trim();
          if (v) this.digitado(v);
        }
      },
      onSend: () => {
        const v = S.draft.trim();
        if (v) this.digitado(v);
      },
    };
  }

  render() {
    const v = this.renderVals();
    return (
    <div style={{ position: "relative", fontFamily: "'Archivo',sans-serif", fontStretch: "100%", color: "#16150F", background: "#F0ECE3", minHeight: "100vh" }}>
      <div ref={v.stageRef} aria-hidden="true" style={{ position: "fixed", inset: "0", zIndex: "0", background: "#F0ECE3" }}>
        {" "}
        <canvas ref={v.canvasRef} style={{ position: "absolute", inset: "0", width: "100%", height: "100%", display: "none" }}></canvas>
        {" "}
        <div ref={v.svgHostRef} style={{ position: "absolute", inset: "0" }}></div>
      </div>
      <div ref={v.labelsRef} style={{ position: "fixed", inset: "0", zIndex: "1", pointerEvents: "none", overflow: "hidden" }}>
        {" "}
        <div ref={v.zoneRef} style={{ position: "absolute", left: "0", top: "0", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", letterSpacing: ".04em", textTransform: "uppercase", color: "#16150F", whiteSpace: "nowrap", opacity: "0" }}>
          {I(v.t.zone)}
        </div>
        {" "}
        {v.labels.map((n, i0) => (
          <Fragment key={i0}>
            {" "}
            <button data-lbl={n.id} onClick={n.open} onMouseEnter={n.enter} onMouseLeave={n.leave} style={{ position: "absolute", left: "0", top: "0", opacity: "0", pointerEvents: "none", display: "flex", flexDirection: "column", alignItems: "center", gap: "2px", padding: "4px 7px 5px", border: "1px solid #16150F", borderStyle: n.bs, background: "#F7F4EC", color: "#16150F", whiteSpace: "nowrap", willChange: "transform", transition: "background-color .25s,color .25s,border-color .25s" }}>
              {" "}
              <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "75%", fontWeight: "700", fontSize: "12px", lineHeight: "1.05", textTransform: "uppercase", letterSpacing: ".01em" }}>
                {I(n.name)}
              </span>
              {" "}
              <span data-sub="1" style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "9px", lineHeight: "1.2", opacity: ".8" }}>
                {I(n.sub)}
              </span>
              {" "}
            </button>
            {" "}
          </Fragment>
        ))}
      </div>
      <header style={{ position: "fixed", top: "0", left: "0", right: "0", zIndex: "50", height: "56px", display: "flex", alignItems: "center", gap: "clamp(8px,1.6vw,20px)", padding: "0 clamp(12px,3vw,32px)", background: "rgba(240,236,227,.95)", backdropFilter: "blur(10px)", "WebkitBackdropFilter": "blur(10px)", borderBottom: "1px solid #16150F" }}>
        {" "}
        <a href="#inicio" style={{ display: "flex", alignItems: "baseline", gap: "10px", textDecoration: "none", color: "#16150F", flex: "0 0 auto" }}>
          {" "}
          <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "900", fontSize: "30px", lineHeight: "1", letterSpacing: ".01em" }}>
            {"JEJE"}
          </span>
          {" "}
          <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", letterSpacing: ".03em", textTransform: "uppercase", color: "#57534A", display: v.L.wideInline }}>
            {I(v.t.ui.tag)}
          </span>
          {" "}
        </a>
        {" "}
        <nav style={{ display: v.L.wideFlex, gap: "2px", marginLeft: "auto" }}>
          {" "}
          {v.navItems.map((n, i0) => (
            <Fragment key={i0}>
              {" "}
              <a href={n.href} style={{ fontSize: "13px", fontWeight: "500", color: "#16150F", textDecoration: "none", padding: "8px 9px" }} className="dc-h0">
                {I(n.label)}
              </a>
              {" "}
            </Fragment>
          ))}
          {" "}
        </nav>
        {" "}
        <div role="group" aria-label="Idioma" style={{ display: "flex", border: "1px solid #16150F", marginLeft: v.L.langMargin }}>
          {" "}
          {v.langs.map((l, i0) => (
            <Fragment key={i0}>
              {" "}
              <button onClick={l.pick} aria-pressed={l.on} style={{ border: "0", padding: "6px 8px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", background: l.bg, color: l.fg }}>
                {I(l.code)}
              </button>
              {" "}
            </Fragment>
          ))}
          {" "}
        </div>
        {" "}
        <button onClick={v.toggleMotion} aria-pressed={v.motionOn} style={{ display: v.L.wideFlex, alignItems: "center", gap: "6px", border: "1px solid #16150F", background: "transparent", padding: "6px 9px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", textTransform: "uppercase" }}>
          {I(v.t.ui.motion)}{" · "}{I(v.motionLabel)}
        </button>
        {" "}
        <a href={v.appUrl} target="_blank" rel="noopener" style={{ flex: "0 0 auto", background: "#2B35F0", color: "#fff", textDecoration: "none", fontWeight: "600", fontSize: "13.5px", padding: "9px 14px", border: "1px solid #2B35F0" }} className="dc-h1">
          {I(v.t.ui.app)}{" ↗"}
        </a>
        {" "}
        <div ref={v.progRef} style={{ position: "absolute", left: "0", bottom: "-1px", height: "3px", width: "0", background: "#2B35F0" }}></div>
      </header>
      <main style={{ position: "relative", zIndex: "2", pointerEvents: "none" }}>
        {" "}
        <section id="inicio" data-stop="0" style={{ minHeight: "100vh", display: "flex", flexDirection: "column", padding: "calc(56px + clamp(28px,7vh,84px)) clamp(16px,4vw,56px) 48px" }}>
          {" "}
          <div style={{ pointerEvents: "auto", maxWidth: "1320px", display: "flex", flexDirection: "column", gap: "22px" }}>
            {" "}
            <p style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", letterSpacing: ".04em", textTransform: "uppercase", margin: "0", display: "flex", gap: "10px", alignItems: "center" }}>
              <span style={{ width: "8px", height: "8px", background: "#2B35F0", display: "inline-block" }}></span>
              {I(v.t.hero.kicker)}
            </p>
            {" "}
            <h1 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".86", letterSpacing: "-.005em", margin: "0", fontSize: "clamp(54px,10.6vw,182px)", textWrap: "balance" }}>
              {I(v.t.hero.t1)}
              <br />
              <span style={{ color: "#2B35F0" }}>
                {I(v.t.hero.t2)}
              </span>
            </h1>
            {" "}
            <p style={{ maxWidth: "560px", fontSize: "clamp(16px,1.25vw,19px)", lineHeight: "1.5", margin: "0", textWrap: "pretty", background: "rgba(240,236,227,.86)", padding: "2px 0" }}>
              {I(v.t.hero.lede)}
            </p>
            {" "}
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              {" "}
              <a href="#viagem" style={{ background: "#16150F", color: "#F0ECE3", textDecoration: "none", fontWeight: "600", fontSize: "15px", padding: "13px 18px", border: "1px solid #16150F" }} className="dc-h2">
                {I(v.t.hero.follow)}{" ↓"}
              </a>
              {" "}
              <a href={v.appUrl} target="_blank" rel="noopener" style={{ background: "#F0ECE3", color: "#16150F", textDecoration: "none", fontWeight: "600", fontSize: "15px", padding: "13px 18px", border: "1px solid #16150F" }} className="dc-h3">
                {I(v.t.ui.app)}{" ↗"}
              </a>
              {" "}
            </div>
            {" "}
          </div>
          {" "}
        </section>
        {" "}
        <section data-stop="1" style={{ minHeight: "112vh", display: "flex", alignItems: "center", padding: "96px clamp(16px,4vw,56px)" }}>
          {" "}
          <div style={{ pointerEvents: "auto", maxWidth: "860px", background: "#F7F4EC", border: "1px solid #16150F" }}>
            {" "}
            <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "9px 18px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", letterSpacing: ".04em", textTransform: "uppercase" }}>
              <span>
                {I(v.t.problem.kicker)}
              </span>
              <span style={{ color: "#2B35F0" }}>
                {"GET /dados/eda"}
              </span>
            </div>
            {" "}
            <div style={{ padding: "clamp(20px,3vw,36px)", display: "flex", flexDirection: "column", gap: "26px" }}>
              {" "}
              <h2 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".92", margin: "0", fontSize: "clamp(34px,4.4vw,66px)", textWrap: "balance" }}>
                {I(v.t.problem.title)}
              </h2>
              {" "}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(170px,1fr))", borderTop: "1px solid #16150F" }}>
                {" "}
                {v.probStats.map((p, i0) => (
                  <Fragment key={i0}>
                    {" "}
                    <button onClick={p.open} style={{ textAlign: "left", background: "transparent", border: "0", borderBottom: "1px solid #CFC7B8", padding: "16px 16px 16px 0", display: "flex", flexDirection: "column", gap: "8px" }} className="dc-h4">
                      {" "}
                      <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "clamp(46px,4.6vw,68px)", lineHeight: ".9", color: "#2B35F0" }}>
                        {I(p.v)}
                      </span>
                      {" "}
                      <span style={{ fontSize: "13.5px", lineHeight: "1.4", color: "#16150F", textWrap: "pretty" }}>
                        {I(p.l)}
                      </span>
                      {" "}
                      <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", color: "#2B35F0" }}>
                        {"↗ "}{I(p.s)}
                      </span>
                      {" "}
                    </button>
                    {" "}
                  </Fragment>
                ))}
                {" "}
              </div>
              {" "}
              <p style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", lineHeight: "1.6", color: "#57534A", margin: "0" }}>
                {I(v.t.problem.note)}
              </p>
              {" "}
            </div>
            {" "}
          </div>
          {" "}
        </section>
        {" "}
        <div id="viagem" style={{ scrollMarginTop: "56px" }}>
          {" "}
          <section data-stop="2" style={{ minHeight: "108vh", display: "flex", alignItems: v.L.cardAlign, padding: `96px clamp(16px,4vw,56px) ${v.L.padBottom ?? ""}` }}>
            {" "}
            <div style={{ pointerEvents: "auto", flex: "0 1 520px", maxWidth: "100%", display: "flex", flexDirection: "column", gap: "18px" }}>
              {" "}
              <p style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", letterSpacing: ".04em", textTransform: "uppercase", margin: "0", background: "#F0ECE3", alignSelf: "flex-start", padding: "3px 0" }}>
                {I(v.t.intro.kicker)}
              </p>
              {" "}
              <h2 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".9", margin: "0", fontSize: "clamp(40px,5vw,78px)", background: "rgba(240,236,227,.9)" }}>
                {I(v.t.intro.title)}
              </h2>
              {" "}
              <div style={{ background: "#FFFDF7", border: "1px solid #16150F", padding: "16px 18px 18px", display: "flex", flexDirection: "column", gap: "8px", maxWidth: "460px" }}>
                {" "}
                <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", textTransform: "uppercase", letterSpacing: ".04em", color: "#57534A" }}>
                  {I(v.t.intro.who)}
                </span>
                {" "}
                <span style={{ fontSize: "clamp(20px,2vw,27px)", lineHeight: "1.25", fontWeight: "500" }}>
                  {"“"}{I(v.t.intro.phrase)}{"”"}
                </span>
                {" "}
                {v.hasGloss ? (
                  <>
                    <span style={{ fontSize: "14px", color: "#57534A" }}>
                      {I(v.t.intro.gloss)}
                    </span>
                  </>
                ) : null}
                {" "}
              </div>
              {" "}
              <p style={{ fontSize: "16px", lineHeight: "1.5", margin: "0", maxWidth: "440px", background: "rgba(240,236,227,.9)" }}>
                {I(v.t.intro.body)}{" ↓"}
              </p>
              {" "}
            </div>
            {" "}
          </section>
          {" "}
          {v.stops.map((s, i0) => (
            <Fragment key={i0}>
              {" "}
              <section data-stop={s.idx} style={{ minHeight: s.minH, display: "flex", flexWrap: "wrap", alignItems: s.align, alignContent: s.align, gap: "clamp(20px,4vw,56px)", padding: `96px clamp(16px,4vw,56px) ${s.padB ?? ""}` }}>
                {" "}
                <article style={{ pointerEvents: "auto", flex: "0 1 440px", maxWidth: "100%", background: "#F7F4EC", border: "1px solid #16150F" }}>
                  {" "}
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "9px 16px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", letterSpacing: ".04em", textTransform: "uppercase" }}>
                    <span>
                      {I(s.num)}
                    </span>
                    <span style={{ color: "#2B35F0" }}>
                      {I(s.tag)}
                    </span>
                  </div>
                  {" "}
                  <div style={{ padding: "18px 20px 22px", display: "flex", flexDirection: "column", gap: "14px" }}>
                    {" "}
                    <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".92", margin: "0", fontSize: "clamp(32px,3.1vw,48px)" }}>
                      {I(s.title)}
                    </h3>
                    {" "}
                    <p style={{ fontSize: "15px", lineHeight: "1.5", margin: "0", textWrap: "pretty" }}>
                      {I(s.does)}
                    </p>
                    {" "}
                    {s.hasHere ? (
                      <>
                        {" "}
                        <div style={{ alignSelf: "flex-start", display: "flex", gap: "8px", alignItems: "center", background: "#2B35F0", color: "#fff", padding: "6px 10px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px" }}>
                          {I(s.lblHere)}{" · "}{I(s.here)}
                        </div>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                    {s.isLeitura ? (
                      <>
                        {" "}
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                          {" "}
                          {s.cascade.map((c, i1) => (
                            <Fragment key={i1}>
                              {" "}
                              <div style={{ display: "grid", gridTemplateColumns: "22px 1fr auto", gap: "10px", alignItems: "center", padding: "8px 10px", border: "1px solid #16150F", borderStyle: c.bstyle, background: c.bg, color: c.fg, marginLeft: c.indent }}>
                                {" "}
                                <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "10px" }}>
                                  {I(c.k)}
                                </span>
                                {" "}
                                <span style={{ fontSize: "13.5px", fontWeight: "600" }}>
                                  {I(c.n)}
                                </span>
                                {" "}
                                <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "9.5px", textTransform: "uppercase" }}>
                                  {I(c.d)}
                                </span>
                                {" "}
                              </div>
                              {" "}
                            </Fragment>
                          ))}
                          {" "}
                        </div>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                    {s.isEtapas ? (
                      <>
                        {" "}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", alignItems: "center" }}>
                          {" "}
                          {s.statesL.map((x, i1) => (
                            <Fragment key={i1}>
                              {" "}
                              <span style={{ padding: "6px 10px", border: "1px solid #16150F", background: x.bg, color: x.fg, fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
                                {I(x.x)}
                              </span>
                              {" "}
                            </Fragment>
                          ))}
                          {" "}
                        </div>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                    {s.isQual ? (
                      <>
                        {" "}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                          {" "}
                          {s.cluesL.map((x, i1) => (
                            <Fragment key={i1}>
                              {" "}
                              <span style={{ padding: "6px 10px", border: "1px solid #2B35F0", color: "#2B35F0", background: "#FFFDF7", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px" }}>
                                {I(x)}
                              </span>
                              {" "}
                            </Fragment>
                          ))}
                          {" "}
                        </div>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      {" "}
                      <p style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", letterSpacing: ".04em", textTransform: "uppercase", color: "#57534A", margin: "0" }}>
                        {I(s.lblProtects)}
                      </p>
                      {" "}
                      <ul style={{ listStyle: "none", margin: "0", padding: "0", display: "flex", flexDirection: "column", gap: "7px" }}>
                        {" "}
                        {s.protects.map((p, i1) => (
                          <Fragment key={i1}>
                            {" "}
                            <li style={{ display: "grid", gridTemplateColumns: "12px 1fr", gap: "8px", fontSize: "14px", lineHeight: "1.45" }}>
                              <span style={{ width: "6px", height: "6px", background: "#16150F", marginTop: "7px" }}></span>
                              <span>
                                {I(p)}
                              </span>
                            </li>
                            {" "}
                          </Fragment>
                        ))}
                        {" "}
                      </ul>
                      {" "}
                    </div>
                    {" "}
                    {s.isPolitica ? (
                      <>
                        {" "}
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center", justifyContent: "space-between" }}>
                          {" "}
                          <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", color: "#57534A" }}>
                            {I(s.note)}
                          </span>
                          {" "}
                          <button onClick={s.openRules} style={{ background: "#16150F", color: "#F0ECE3", border: "1px solid #16150F", padding: "8px 12px", fontSize: "13px", fontWeight: "600" }} className="dc-h5">
                            {I(s.rulesBtn)}{" →"}
                          </button>
                          {" "}
                        </div>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                    {s.isAcao ? (
                      <>
                        {" "}
                        <div style={{ border: "1px solid #16150F", background: "#FFFDF7", padding: "14px", display: "flex", flexDirection: "column", gap: "10px" }}>
                          {" "}
                          <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", textTransform: "uppercase", color: "#57534A" }}>
                            {"JEJE"}
                          </span>
                          {" "}
                          <p style={{ margin: "0", fontSize: "14px", lineHeight: "1.45" }}>
                            {I(s.proposal)}
                          </p>
                          {" "}
                          <p style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", textTransform: "uppercase", color: "#2B35F0", margin: "4px 0 0" }}>
                            {I(s.you)}
                          </p>
                          {" "}
                          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                            {" "}
                            <button onClick={s.onYes} style={{ background: s.yesBg, color: s.yesFg, border: "1px solid #2B35F0", padding: "9px 14px", fontWeight: "600", fontSize: "14px" }}>
                              {I(s.yes)}
                            </button>
                            {" "}
                            <button onClick={s.onNo} style={{ background: s.noBg, color: s.noFg, border: "1px solid #16150F", padding: "9px 14px", fontWeight: "600", fontSize: "14px" }}>
                              {I(s.no)}
                            </button>
                            {" "}
                          </div>
                          {" "}
                          {s.answered ? (
                            <>
                              {" "}
                              <p style={{ margin: "0", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", lineHeight: "1.5", color: s.ansColor }}>
                                {I(s.ansText)}
                              </p>
                              {" "}
                            </>
                          ) : null}
                          {" "}
                        </div>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                    {s.hasStat ? (
                      <>
                        {" "}
                        <button onClick={s.openStat} style={{ textAlign: "left", background: "transparent", border: "0", borderTop: "1px solid #16150F", padding: "14px 0 0", display: "flex", flexDirection: "column", gap: "6px" }} className="dc-h4">
                          {" "}
                          <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "clamp(42px,4vw,60px)", lineHeight: ".9", color: "#2B35F0" }}>
                            {I(s.statV)}
                          </span>
                          {" "}
                          <span style={{ fontSize: "13.5px", lineHeight: "1.4" }}>
                            {I(s.statL)}
                          </span>
                          {" "}
                          <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", color: "#2B35F0" }}>
                            {"↗ "}{I(s.statS)}
                          </span>
                          {" "}
                        </button>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                  </div>
                  {" "}
                </article>
                {" "}
                {s.isBanco ? (
                  <>
                    {" "}
                    <div style={{ pointerEvents: "auto", flex: "0 1 380px", maxWidth: "100%", display: "flex", flexDirection: "column" }}>
                      {" "}
                      <div style={{ height: "16px", background: "#16150F", borderRadius: "8px", margin: "0 -10px", position: "relative", zIndex: "1" }}></div>
                      {" "}
                      <div ref={s.receiptRef} style={{ margin: "-8px 10px 0", clipPath: "inset(0 0 100% 0)" }}>
                        {" "}
                        <div style={{ background: "#FFFDF7", padding: "26px 20px 18px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", lineHeight: "1.65", color: "#16150F", display: "flex", flexDirection: "column", gap: "12px" }}>
                          {" "}
                          <div style={{ display: "flex", justifyContent: "space-between", gap: "10px", alignItems: "baseline" }}>
                            <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "900", fontSize: "24px", lineHeight: "1" }}>
                              {"JEJE"}
                            </span>
                            <span style={{ textTransform: "uppercase", fontSize: "10px" }}>
                              {I(s.rcTitle)}
                            </span>
                          </div>
                          {" "}
                          <div style={{ borderTop: "1px dashed #16150F" }}></div>
                          {" "}
                          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", columnGap: "14px", rowGap: "3px" }}>
                            {" "}
                            {s.rcRows.map((r, i1) => (
                              <Fragment key={i1}>
                                {" "}
                                <span style={{ color: "#57534A", textTransform: "uppercase", fontSize: "9.5px", paddingTop: "2px" }}>
                                  {I(r.k)}
                                </span>
                                {" "}
                                <span style={{ fontWeight: r.w, color: r.c, textAlign: "right" }}>
                                  {I(r.v)}
                                </span>
                                {" "}
                              </Fragment>
                            ))}
                            {" "}
                          </div>
                          {" "}
                          <div style={{ borderTop: "1px dashed #16150F" }}></div>
                          {" "}
                          <span style={{ textTransform: "uppercase", fontSize: "9.5px", color: "#57534A" }}>
                            {I(s.rcFactsT)}
                          </span>
                          {" "}
                          <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", columnGap: "14px", rowGap: "3px" }}>
                            {" "}
                            {s.rcFacts.map((r, i1) => (
                              <Fragment key={i1}>
                                {" "}
                                <span style={{ color: "#57534A", textTransform: "uppercase", fontSize: "9.5px", paddingTop: "2px" }}>
                                  {I(r.k)}
                                </span>
                                {" "}
                                <span style={{ textAlign: "right" }}>
                                  {I(r.v)}
                                </span>
                                {" "}
                              </Fragment>
                            ))}
                            {" "}
                          </div>
                          {" "}
                          <div style={{ borderTop: "1px dashed #16150F" }}></div>
                          {" "}
                          <span style={{ textTransform: "uppercase", fontSize: "9.5px", color: "#57534A" }}>
                            {I(s.rcReplyT)}
                          </span>
                          {" "}
                          <p style={{ margin: "0", fontFamily: "'Archivo',sans-serif", fontStretch: "100%", fontSize: "14.5px", lineHeight: "1.45" }}>
                            {"“"}{I(s.rcReply)}{"”"}
                          </p>
                          {" "}
                          <div style={{ borderTop: "1px dashed #16150F" }}></div>
                          {" "}
                          <p style={{ margin: "0", fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", fontSize: "21px", lineHeight: "1" }}>
                            {I(s.rcFoot)}
                          </p>
                          {" "}
                          <span style={{ fontSize: "9.5px", color: "#57534A" }}>
                            {I(s.rcFixture)}
                          </span>
                          {" "}
                        </div>
                        {" "}
                        <div style={{ height: "8px", background: "conic-gradient(from -45deg at 50% 100%,#FFFDF7 90deg,transparent 0) 0 0/12px 8px repeat-x" }}></div>
                        {" "}
                      </div>
                      {" "}
                    </div>
                    {" "}
                  </>
                ) : null}
                {" "}
              </section>
              {" "}
            </Fragment>
          ))}
          {" "}
          {v.dataStops.map((s, i0) => (
            <Fragment key={i0}>
              {" "}
              <section data-stop={s.idx} style={{ minHeight: "104vh", display: "flex", alignItems: s.align, padding: `96px clamp(16px,4vw,56px) ${s.padB ?? ""}` }}>
                {" "}
                <article style={{ pointerEvents: "auto", flex: "0 1 420px", maxWidth: "100%", background: "#F7F4EC", border: "1px solid #16150F" }}>
                  {" "}
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "9px 16px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", letterSpacing: ".04em", textTransform: "uppercase" }}>
                    <span>
                      {I(s.num)}
                    </span>
                    <span style={{ color: "#2B35F0" }}>
                      {I(s.tag)}
                    </span>
                  </div>
                  {" "}
                  <div style={{ padding: "18px 20px 22px", display: "flex", flexDirection: "column", gap: "14px" }}>
                    {" "}
                    {s.isFirst ? (
                      <>
                        {" "}
                        <div style={{ display: "flex", flexDirection: "column", gap: "6px", paddingBottom: "12px", borderBottom: "1px solid #CFC7B8" }}>
                          {" "}
                          <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", letterSpacing: ".04em", textTransform: "uppercase", color: "#2B35F0" }}>
                            {I(s.introK)}
                          </span>
                          {" "}
                          <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".92", fontSize: "clamp(26px,2.4vw,36px)" }}>
                            {I(s.introT)}
                          </span>
                          {" "}
                        </div>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                    <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".92", margin: "0", fontSize: "clamp(30px,2.9vw,44px)" }}>
                      {I(s.title)}
                    </h3>
                    {" "}
                    <p style={{ fontSize: "15px", lineHeight: "1.5", margin: "0", textWrap: "pretty" }}>
                      {I(s.does)}
                    </p>
                    {" "}
                    {s.hasStat ? (
                      <>
                        {" "}
                        <button onClick={s.openStat} style={{ textAlign: "left", background: "transparent", border: "0", borderTop: "1px solid #16150F", padding: "14px 0 0", display: "flex", flexDirection: "column", gap: "6px" }} className="dc-h4">
                          {" "}
                          <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "clamp(40px,3.8vw,56px)", lineHeight: ".9", color: "#2B35F0" }}>
                            {I(s.statV)}
                          </span>
                          {" "}
                          <span style={{ fontSize: "13.5px", lineHeight: "1.4" }}>
                            {I(s.statL)}
                          </span>
                          {" "}
                          <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", color: "#2B35F0" }}>
                            {"↗ "}{I(s.statS)}
                          </span>
                          {" "}
                        </button>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                  </div>
                  {" "}
                </article>
                {" "}
              </section>
              {" "}
            </Fragment>
          ))}
          {" "}
          <section id="mapa" data-stop="16" style={{ minHeight: "190vh", padding: "84px clamp(16px,4vw,56px) 40px", scrollMarginTop: "0" }}>
            {" "}
            <div style={{ position: "sticky", top: "76px", pointerEvents: "auto", maxWidth: "400px", background: "#F7F4EC", border: "1px solid #16150F" }}>
              {" "}
              <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "9px 16px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", letterSpacing: ".04em", textTransform: "uppercase" }}>
                <span>
                  {I(v.t.map.kicker)}
                </span>
                <span style={{ color: "#2B35F0" }}>
                  {"16 · 17"}
                </span>
              </div>
              {" "}
              <div style={{ padding: "16px 18px 18px", display: "flex", flexDirection: "column", gap: "14px" }}>
                {" "}
                <h2 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".92", margin: "0", fontSize: "clamp(30px,2.8vw,42px)" }}>
                  {I(v.t.map.title)}
                </h2>
                {" "}
                <p style={{ fontSize: "14.5px", lineHeight: "1.5", margin: "0", display: v.L.mapBody }}>
                  {I(v.t.map.body)}
                </p>
                {" "}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: "8px 12px" }}>
                  {" "}
                  {v.legend.map((g, i0) => (
                    <Fragment key={i0}>
                      {" "}
                      <div style={{ display: "flex", gap: "8px", alignItems: "center", fontSize: "12px", lineHeight: "1.25" }}>
                        <span style={{ flex: "0 0 14px", height: "14px", background: g.bg, border: "1px solid #16150F", borderStyle: g.bs }}></span>
                        <span>
                          {I(g.l)}
                        </span>
                      </div>
                      {" "}
                    </Fragment>
                  ))}
                  {" "}
                </div>
                {" "}
                <div style={{ display: "flex", flexDirection: "column", gap: "8px", borderTop: "1px solid #CFC7B8", paddingTop: "12px" }}>
                  {" "}
                  <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", letterSpacing: ".04em", textTransform: "uppercase", color: "#57534A" }}>
                    {I(v.t.map.try)}{" · "}{I(v.convLangUp)}
                  </span>
                  {" "}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    {" "}
                    {v.chips.map((c, i0) => (
                      <Fragment key={i0}>
                        {" "}
                        <button onClick={c.go} style={{ border: "1px solid #16150F", background: "#FFFDF7", padding: "7px 10px", fontSize: "12.5px", textAlign: "left" }} className="dc-h6">
                          {I(c.l)}
                        </button>
                        {" "}
                      </Fragment>
                    ))}
                    {" "}
                  </div>
                  {" "}
                </div>
                {" "}
              </div>
              {" "}
            </div>
            {" "}
          </section>
          {" "}
        </div>
        {" "}
        <section id="modelos" style={{ position: "relative", pointerEvents: "auto", background: "#F0ECE3", borderTop: "1px solid #16150F", padding: "clamp(64px,11vh,128px) clamp(16px,4vw,56px)", scrollMarginTop: "56px" }}>
          {" "}
          <div style={{ maxWidth: "1320px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "clamp(28px,4vw,48px)" }}>
            {" "}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "20px 48px", alignItems: "flex-end", justifyContent: "space-between" }}>
              {" "}
              <div style={{ display: "flex", flexDirection: "column", gap: "14px", flex: "1 1 560px" }}>
                {" "}
                <p style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", letterSpacing: ".04em", textTransform: "uppercase", margin: "0", display: "flex", gap: "10px", alignItems: "center" }}>
                  <span style={{ width: "8px", height: "8px", background: "#2B35F0", display: "inline-block" }}></span>
                  {I(v.t.models.kicker)}
                </p>
                {" "}
                <h2 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".86", margin: "0", fontSize: "clamp(52px,8.6vw,138px)", textWrap: "balance" }}>
                  {I(v.t.models.title)}
                </h2>
                {" "}
              </div>
              {" "}
              <p style={{ flex: "0 1 380px", fontSize: "16px", lineHeight: "1.5", margin: "0", textWrap: "pretty" }}>
                {I(v.t.models.body)}
              </p>
              {" "}
            </div>
            {" "}
            <div style={{ display: "flex", flexWrap: "wrap", border: "1px solid #16150F", background: "#F7F4EC" }}>
              {" "}
              <div role="tablist" style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", borderRight: "1px solid #16150F" }}>
                {" "}
                {v.modelTabs.map((m, i0) => (
                  <Fragment key={i0}>
                    {" "}
                    <button role="tab" aria-selected={m.on} onClick={m.pick} style={{ textAlign: "left", padding: "16px 18px", border: "0", borderBottom: "1px solid #16150F", background: m.bg, color: m.fg, display: "grid", gridTemplateColumns: "30px 1fr", gap: "4px 10px", alignItems: "baseline" }}>
                      {" "}
                      <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px" }}>
                        {I(m.num)}
                      </span>
                      {" "}
                      <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", fontSize: "24px", lineHeight: ".95" }}>
                        {I(m.name)}
                      </span>
                      {" "}
                      <span></span>
                      {" "}
                      <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "9.5px", textTransform: "uppercase", letterSpacing: ".03em", opacity: ".85" }}>
                        {I(m.role)}
                      </span>
                      {" "}
                    </button>
                    {" "}
                  </Fragment>
                ))}
                {" "}
              </div>
              {" "}
              <article style={{ flex: "2 1 560px", minWidth: "0", padding: "clamp(20px,3vw,40px)", display: "flex", flexDirection: "column", gap: "24px" }}>
                {" "}
                <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "flex-start", justifyContent: "space-between" }}>
                  {" "}
                  <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".88", margin: "0", fontSize: "clamp(40px,4.8vw,74px)", flex: "1 1 320px" }}>
                    {I(v.mm.n)}
                  </h3>
                  {" "}
                  <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                    {" "}
                    {v.mm.planned ? (
                      <>
                        <span style={{ border: "1px dashed #16150F", padding: "6px 10px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", textTransform: "uppercase" }}>
                          {I(v.t.ui.planned)}{" · DEV-042"}
                        </span>
                      </>
                    ) : null}
                    {" "}
                    {v.mm.hasBy ? (
                      <>
                        <span style={{ border: "1px solid #16150F", padding: "6px 10px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", textTransform: "uppercase" }}>
                          {I(v.mm.byL)}
                        </span>
                      </>
                    ) : null}
                    {" "}
                  </div>
                  {" "}
                </div>
                {" "}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: "22px 32px" }}>
                  {" "}
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", letterSpacing: ".04em", textTransform: "uppercase", color: "#57534A" }}>
                      {I(v.t.models.f.does)}
                    </span>
                    <p style={{ margin: "0", fontSize: "15.5px", lineHeight: "1.5", textWrap: "pretty" }}>
                      {I(v.mm.does)}
                    </p>
                  </div>
                  {" "}
                  <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", letterSpacing: ".04em", textTransform: "uppercase", color: "#57534A" }}>
                      {I(v.t.models.f.data)}
                    </span>
                    <p style={{ margin: "0", fontSize: "15.5px", lineHeight: "1.5", textWrap: "pretty" }}>
                      {I(v.mm.data)}
                    </p>
                  </div>
                  {" "}
                </div>
                {" "}
                <div style={{ display: "flex", flexDirection: "column", gap: "12px", borderTop: "1px solid #16150F", paddingTop: "16px" }}>
                  {" "}
                  <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", letterSpacing: ".04em", textTransform: "uppercase", color: "#57534A" }}>
                    {I(v.t.models.f.measure)}
                  </span>
                  {" "}
                  {v.mm.hasStats ? (
                    <>
                      {" "}
                      {v.mm.stats.map((x, i0) => (
                        <Fragment key={i0}>
                          {" "}
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 16px", alignItems: "baseline" }}>
                            <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "64px", lineHeight: ".9", color: "#2B35F0" }}>
                              {I(x.v)}
                            </span>
                            <span style={{ fontSize: "14px", maxWidth: "320px" }}>
                              {I(x.l)}
                            </span>
                          </div>
                          {" "}
                        </Fragment>
                      ))}
                      {" "}
                    </>
                  ) : null}
                  {" "}
                  {v.mm.hasBars ? (
                    <>
                      {" "}
                      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                        {" "}
                        {v.mm.bars.map((b, i0) => (
                          <Fragment key={i0}>
                            {" "}
                            <div style={{ display: "grid", gridTemplateColumns: "28px minmax(0,1fr) 72px", gap: "12px", alignItems: "center" }}>
                              {" "}
                              <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "10.5px" }}>
                                {I(b.l)}
                              </span>
                              {" "}
                              <span style={{ height: "14px", border: "1px solid #16150F", position: "relative", display: "block" }}>
                                <span style={{ position: "absolute", left: "0", top: "0", bottom: "0", width: b.wp, background: "#2B35F0" }}></span>
                              </span>
                              {" "}
                              <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "12px", textAlign: "right" }}>
                                {I(b.v)}
                              </span>
                              {" "}
                            </div>
                            {" "}
                          </Fragment>
                        ))}
                        {" "}
                      </div>
                      {" "}
                    </>
                  ) : null}
                  {" "}
                  {v.mm.hasPairs ? (
                    <>
                      {" "}
                      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                        {" "}
                        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", fontSize: "12px" }}>
                          <span style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                            <span style={{ width: "12px", height: "12px", background: "#2B35F0" }}></span>
                            {I(v.mm.legA)}
                          </span>
                          <span style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                            <span style={{ width: "12px", height: "12px", border: "1px solid #16150F", background: "repeating-linear-gradient(135deg,transparent 0 3px,#16150F 3px 4px)" }}></span>
                            {I(v.mm.legB)}
                          </span>
                        </div>
                        {" "}
                        {v.mm.pairs.map((p, i0) => (
                          <Fragment key={i0}>
                            {" "}
                            <div style={{ display: "grid", gridTemplateColumns: "minmax(80px,140px) minmax(0,1fr)", gap: "6px 12px", alignItems: "center" }}>
                              {" "}
                              <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", textTransform: "uppercase", gridRow: "span 2" }}>
                                {I(p.l)}
                              </span>
                              {" "}
                              <span style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 56px", gap: "10px", alignItems: "center" }}>
                                <span style={{ height: "12px", border: "1px solid #16150F", position: "relative", display: "block" }}>
                                  <span style={{ position: "absolute", left: "0", top: "0", bottom: "0", width: p.aw, background: "#2B35F0" }}></span>
                                </span>
                                <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "11.5px", textAlign: "right" }}>
                                  {I(p.av)}
                                </span>
                              </span>
                              {" "}
                              <span style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 56px", gap: "10px", alignItems: "center" }}>
                                <span style={{ height: "12px", border: "1px solid #16150F", position: "relative", display: "block" }}>
                                  <span style={{ position: "absolute", left: "0", top: "0", bottom: "0", width: p.bw, background: "repeating-linear-gradient(135deg,transparent 0 3px,#16150F 3px 4px)" }}></span>
                                </span>
                                <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "11.5px", textAlign: "right" }}>
                                  {I(p.bv)}
                                </span>
                              </span>
                              {" "}
                            </div>
                            {" "}
                          </Fragment>
                        ))}
                        {" "}
                      </div>
                      {" "}
                    </>
                  ) : null}
                  {" "}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px", alignItems: "baseline", justifyContent: "space-between" }}>
                    {" "}
                    <span style={{ fontSize: "13.5px", lineHeight: "1.45", color: "#57534A", flex: "1 1 300px" }}>
                      {I(v.mm.note)}
                    </span>
                    {" "}
                    <button onClick={v.mm.openSrc} style={{ background: "transparent", border: "0", borderBottom: "1px solid #2B35F0", padding: "2px 0", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", color: "#2B35F0" }}>
                      {"↗ "}{I(v.mm.src)}
                    </button>
                    {" "}
                  </div>
                  {" "}
                </div>
                {" "}
                <div style={{ background: "#16150F", color: "#F0ECE3", padding: "18px 20px", display: "flex", flexDirection: "column", gap: "8px" }}>
                  {" "}
                  <span style={{ display: "flex", gap: "8px", alignItems: "center", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", letterSpacing: ".04em", textTransform: "uppercase" }}>
                    <span style={{ width: "10px", height: "10px", background: "#FF5520", display: "inline-block" }}></span>
                    {I(v.t.models.f.limit)}
                  </span>
                  {" "}
                  <p style={{ margin: "0", fontSize: "clamp(17px,1.5vw,21px)", lineHeight: "1.4", textWrap: "pretty" }}>
                    {I(v.mm.limit)}
                  </p>
                  {" "}
                </div>
                {" "}
              </article>
              {" "}
            </div>
            {" "}
          </div>
          {" "}
        </section>
        {" "}
        <section id="pilares" style={{ position: "relative", pointerEvents: "auto", background: "#16150F", color: "#F0ECE3", padding: "clamp(64px,11vh,128px) clamp(16px,4vw,56px)", scrollMarginTop: "56px" }}>
          {" "}
          <div style={{ maxWidth: "1320px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "20px" }}>
            {" "}
            <p style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", letterSpacing: ".04em", textTransform: "uppercase", margin: "0", display: "flex", gap: "10px", alignItems: "center" }}>
              <span style={{ width: "8px", height: "8px", background: "#FF5520", display: "inline-block" }}></span>
              {I(v.t.pillars.kicker)}
            </p>
            {" "}
            <h2 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".86", margin: "0 0 24px", fontSize: "clamp(52px,8.6vw,138px)" }}>
              {I(v.t.pillars.title)}
            </h2>
            {" "}
            <article style={{ display: "flex", flexWrap: "wrap", gap: "28px clamp(24px,4vw,64px)", padding: "44px 0", borderTop: "1px solid #57534A" }}>
              {" "}
              <div style={{ flex: "1 1 380px", display: "flex", flexDirection: "column", gap: "14px" }}>
                {" "}
                <div style={{ display: "flex", gap: "16px", alignItems: "baseline" }}>
                  <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "clamp(64px,8vw,120px)", lineHeight: ".8", color: "#FF5520" }}>
                    {"01"}
                  </span>
                  <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".9", margin: "0", fontSize: "clamp(34px,3.6vw,56px)" }}>
                    {I(v.P0.n)}
                  </h3>
                </div>
                {" "}
                <p style={{ fontSize: "clamp(18px,1.6vw,23px)", lineHeight: "1.35", margin: "0", textWrap: "pretty" }}>
                  {I(v.P0.claim)}
                </p>
                {" "}
                <ul style={{ listStyle: "none", margin: "0", padding: "0", display: "flex", flexDirection: "column", borderTop: "1px solid #57534A" }}>
                  {" "}
                  {v.P0.proofs.map((p, i0) => (
                    <Fragment key={i0}>
                      <li style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", justifyContent: "space-between", alignItems: "baseline", padding: "11px 0", borderBottom: "1px solid #3A382F", fontSize: "14.5px", lineHeight: "1.45" }}>
                        <span style={{ flex: "1 1 260px" }}>
                          {I(p.txt)}
                        </span>
                        <button onClick={p.open} style={{ background: "transparent", border: "1px solid #F0ECE3", color: "#F0ECE3", padding: "3px 7px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px" }} className="dc-h7">
                          {"↗ "}{I(p.s)}
                        </button>
                      </li>
                    </Fragment>
                  ))}
                  {" "}
                </ul>
                {" "}
              </div>
              {" "}
              <div style={{ flex: "1 1 460px", minWidth: "0", background: "#F7F4EC", color: "#16150F", display: "flex", flexDirection: "column" }}>
                {" "}
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "9px 16px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
                  <span>
                    {I(v.t.pillars.obs.title)}
                  </span>
                  <span style={{ color: "#57534A" }}>
                    {I(v.t.ui.illustrative)}
                  </span>
                </div>
                {" "}
                <div style={{ padding: "18px", display: "flex", flexDirection: "column", gap: "12px" }}>
                  {" "}
                  <button onClick={v.toggleObs} style={{ alignSelf: "flex-start", background: "#2B35F0", color: "#fff", border: "0", padding: "10px 14px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "12px" }} className="dc-h8">
                    {"X-Request-ID: c1f4e2a9-7b0d ↓"}
                  </button>
                  {" "}
                  <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", color: "#57534A", textTransform: "uppercase" }}>
                    {I(v.t.pillars.obs.hint)}
                  </span>
                  {" "}
                  {v.obsRows.map((r, i0) => (
                    <Fragment key={i0}>
                      {" "}
                      <div style={{ display: "flex", flexDirection: "column", gap: "4px", padding: "10px 12px", border: "1px solid #16150F", background: r.bg, opacity: r.op, transition: "opacity .4s,background-color .4s" }}>
                        {" "}
                        <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "9.5px", textTransform: "uppercase", color: "#2B35F0" }}>
                          {I(r.k)}
                        </span>
                        {" "}
                        <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", lineHeight: "1.55", overflowWrap: "anywhere" }}>
                          {I(r.v)}
                        </span>
                        {" "}
                      </div>
                      {" "}
                    </Fragment>
                  ))}
                  {" "}
                  <p style={{ margin: "0", fontSize: "13px", lineHeight: "1.45", color: "#57534A" }}>
                    {I(v.t.pillars.obs.note)}
                  </p>
                  {" "}
                </div>
                {" "}
              </div>
              {" "}
            </article>
            {" "}
            <article style={{ display: "flex", flexWrap: "wrap", gap: "28px clamp(24px,4vw,64px)", padding: "44px 0", borderTop: "1px solid #57534A" }}>
              {" "}
              <div style={{ flex: "1 1 380px", display: "flex", flexDirection: "column", gap: "14px" }}>
                {" "}
                <div style={{ display: "flex", gap: "16px", alignItems: "baseline" }}>
                  <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "clamp(64px,8vw,120px)", lineHeight: ".8", color: "#FF5520" }}>
                    {"02"}
                  </span>
                  <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".9", margin: "0", fontSize: "clamp(34px,3.6vw,56px)" }}>
                    {I(v.P1.n)}
                  </h3>
                </div>
                {" "}
                <p style={{ fontSize: "clamp(18px,1.6vw,23px)", lineHeight: "1.35", margin: "0", textWrap: "pretty" }}>
                  {I(v.P1.claim)}
                </p>
                {" "}
                <ul style={{ listStyle: "none", margin: "0", padding: "0", display: "flex", flexDirection: "column", borderTop: "1px solid #57534A" }}>
                  {" "}
                  {v.P1.proofs.map((p, i0) => (
                    <Fragment key={i0}>
                      <li style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", justifyContent: "space-between", alignItems: "baseline", padding: "11px 0", borderBottom: "1px solid #3A382F", fontSize: "14.5px", lineHeight: "1.45" }}>
                        <span style={{ flex: "1 1 260px" }}>
                          {I(p.txt)}
                        </span>
                        <button onClick={p.open} style={{ background: "transparent", border: "1px solid #F0ECE3", color: "#F0ECE3", padding: "3px 7px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px" }} className="dc-h7">
                          {"↗ "}{I(p.s)}
                        </button>
                      </li>
                    </Fragment>
                  ))}
                  {" "}
                </ul>
                {" "}
              </div>
              {" "}
              <div style={{ flex: "1 1 460px", minWidth: "0", display: "flex", flexDirection: "column", gap: "16px" }}>
                {" "}
                <div style={{ background: "#F7F4EC", color: "#16150F", display: "flex", flexDirection: "column" }}>
                  {" "}
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "9px 16px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
                    <span>
                      {I(v.t.pillars.conf.title)}
                    </span>
                    <span style={{ color: "#57534A" }}>
                      {I(v.t.ui.illustrative)}
                    </span>
                  </div>
                  {" "}
                  <div style={{ padding: "18px", display: "flex", flexDirection: "column", gap: "12px" }}>
                    {" "}
                    <div style={{ background: "#FFFDF7", border: "1px solid #16150F", padding: "14px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "12px", lineHeight: "1.8", overflowX: "auto", whiteSpace: "pre" }}>
                      <span style={{ color: "#57534A" }}>
                        {"# politica.py"}
                      </span>
                      <span>
                        {"def dentro_do_limite(valor_usd):"}
                      </span>
                      <span>
                        {"    return valor_usd "}
                      </span>
                      <span style={{ background: v.opBg, padding: "1px 4px", fontWeight: "700" }}>
                        {I(v.op)}
                      </span>
                      <span>
                        {" LIMITE_USD  # 5.000"}
                      </span>
                    </div>
                    {" "}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", alignItems: "center", justifyContent: "space-between", border: "1px solid #16150F", padding: "10px 12px" }}>
                      {" "}
                      <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px" }}>
                        {"test_contestacao_no_limite_exato · 5000.00"}
                      </span>
                      {" "}
                      <span style={{ background: v.testBg, color: v.testFg, padding: "4px 8px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", fontWeight: "600", textTransform: "uppercase" }}>
                        {I(v.testLabel)}
                      </span>
                      {" "}
                    </div>
                    {" "}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center", justifyContent: "space-between" }}>
                      {" "}
                      <button onClick={v.togglePlant} style={{ background: "#16150F", color: "#F0ECE3", border: "0", padding: "10px 14px", fontWeight: "600", fontSize: "14px" }} className="dc-h9">
                        {I(v.plantLabel)}
                      </button>
                      {" "}
                      <span style={{ fontSize: "12.5px", color: "#57534A", flex: "1 1 200px", textAlign: "right" }}>
                        {I(v.t.pillars.conf.note)}
                      </span>
                      {" "}
                    </div>
                    {" "}
                  </div>
                  {" "}
                </div>
                {" "}
                <div style={{ border: "1px solid #57534A", padding: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
                  {" "}
                  <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
                    {I(v.t.pillars.conf.failTitle)}
                  </span>
                  {" "}
                  {v.fails.map((f, i0) => (
                    <Fragment key={i0}>
                      {" "}
                      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.3fr) 44px minmax(0,1.2fr)", gap: "10px", fontSize: "13px", padding: "6px 0", borderTop: "1px solid #3A382F" }}>
                        <span>
                          {I(f.a)}
                        </span>
                        <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "11px" }}>
                          {I(f.b)}
                        </span>
                        <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", textAlign: "right" }}>
                          {I(f.c)}
                        </span>
                      </div>
                      {" "}
                    </Fragment>
                  ))}
                  {" "}
                </div>
                {" "}
              </div>
              {" "}
            </article>
            {" "}
            <article style={{ display: "flex", flexWrap: "wrap", gap: "28px clamp(24px,4vw,64px)", padding: "44px 0", borderTop: "1px solid #57534A" }}>
              {" "}
              <div style={{ flex: "1 1 380px", display: "flex", flexDirection: "column", gap: "14px" }}>
                {" "}
                <div style={{ display: "flex", gap: "16px", alignItems: "baseline" }}>
                  <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "clamp(64px,8vw,120px)", lineHeight: ".8", color: "#FF5520" }}>
                    {"03"}
                  </span>
                  <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".9", margin: "0", fontSize: "clamp(34px,3.6vw,56px)" }}>
                    {I(v.P2.n)}
                  </h3>
                </div>
                {" "}
                <p style={{ fontSize: "clamp(18px,1.6vw,23px)", lineHeight: "1.35", margin: "0", textWrap: "pretty" }}>
                  {I(v.P2.claim)}
                </p>
                {" "}
                <ul style={{ listStyle: "none", margin: "0", padding: "0", display: "flex", flexDirection: "column", borderTop: "1px solid #57534A" }}>
                  {" "}
                  {v.P2.proofs.map((p, i0) => (
                    <Fragment key={i0}>
                      <li style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", justifyContent: "space-between", alignItems: "baseline", padding: "11px 0", borderBottom: "1px solid #3A382F", fontSize: "14.5px", lineHeight: "1.45" }}>
                        <span style={{ flex: "1 1 260px" }}>
                          {I(p.txt)}
                        </span>
                        <button onClick={p.open} style={{ background: "transparent", border: "1px solid #F0ECE3", color: "#F0ECE3", padding: "3px 7px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px" }} className="dc-h7">
                          {"↗ "}{I(p.s)}
                        </button>
                      </li>
                    </Fragment>
                  ))}
                  {" "}
                </ul>
                {" "}
              </div>
              {" "}
              <div style={{ flex: "1 1 460px", minWidth: "0", display: "flex", flexDirection: "column", gap: "16px" }}>
                {" "}
                <div style={{ background: "#F7F4EC", color: "#16150F", display: "flex", flexDirection: "column" }}>
                  {" "}
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "9px 16px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
                    <span>
                      {I(v.t.pillars.seg.title)}
                    </span>
                    <span style={{ color: "#2B35F0" }}>
                      {"INJ-01"}
                    </span>
                  </div>
                  {" "}
                  <div style={{ padding: "18px", display: "flex", flexDirection: "column", gap: "12px" }}>
                    {" "}
                    <div style={{ background: "#FFFDF7", border: "1px solid #16150F", padding: "12px 14px", display: "flex", flexDirection: "column", gap: "6px" }}>
                      <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "9.5px", textTransform: "uppercase", color: "#57534A" }}>
                        {I(v.t.intro.who)}
                      </span>
                      <span style={{ fontSize: "16px", lineHeight: "1.4", fontWeight: "500" }}>
                        {"“"}{I(v.injMsg)}{"”"}
                      </span>
                    </div>
                    {" "}
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", border: "1px solid #16150F" }}>
                      {" "}
                      {v.injRes.map((r, i0) => (
                        <Fragment key={i0}>
                          <div style={{ padding: "10px 12px", borderRight: "1px solid #CFC7B8", display: "flex", flexDirection: "column", gap: "4px" }}>
                            <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "9.5px", textTransform: "uppercase", color: "#57534A" }}>
                              {I(r.k)}
                            </span>
                            <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "12px", fontWeight: "600" }}>
                              {I(r.v)}
                            </span>
                          </div>
                        </Fragment>
                      ))}
                      {" "}
                    </div>
                    {" "}
                    <p style={{ margin: "0", fontSize: "13.5px", lineHeight: "1.45" }}>
                      {I(v.t.pillars.seg.note)}
                    </p>
                    {" "}
                    <button onClick={v.sendInj} style={{ alignSelf: "flex-start", background: "#16150F", color: "#F0ECE3", border: "0", padding: "10px 14px", fontWeight: "600", fontSize: "14px" }} className="dc-h10">
                      {I(v.t.pillars.seg.send)}{" →"}
                    </button>
                    {" "}
                  </div>
                  {" "}
                </div>
                {" "}
                <button onClick={v.openHonest} style={{ textAlign: "left", background: "transparent", color: "#F0ECE3", border: "1px solid #FF5520", padding: "16px 18px", display: "flex", flexWrap: "wrap", gap: "8px 18px", alignItems: "center" }} className="dc-h11">
                  {" "}
                  <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "clamp(56px,6vw,84px)", lineHeight: ".85", color: "#FF5520" }}>
                    {I(v.t.pillars.seg.honest.v)}
                  </span>
                  {" "}
                  <span style={{ flex: "1 1 240px", fontSize: "14px", lineHeight: "1.45" }}>
                    {I(v.t.pillars.seg.honest.l)}{" "}
                    <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "10px", whiteSpace: "nowrap" }}>
                      {"↗ NOV-13"}
                    </span>
                  </span>
                  {" "}
                </button>
                {" "}
              </div>
              {" "}
            </article>
            {" "}
            <article style={{ display: "flex", flexWrap: "wrap", gap: "28px clamp(24px,4vw,64px)", padding: "44px 0", borderTop: "1px solid #57534A" }}>
              {" "}
              <div style={{ flex: "1 1 380px", display: "flex", flexDirection: "column", gap: "14px" }}>
                {" "}
                <div style={{ display: "flex", gap: "16px", alignItems: "baseline" }}>
                  <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "clamp(64px,8vw,120px)", lineHeight: ".8", color: "#FF5520" }}>
                    {"04"}
                  </span>
                  <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".9", margin: "0", fontSize: "clamp(34px,3.6vw,56px)" }}>
                    {I(v.P3.n)}
                  </h3>
                </div>
                {" "}
                <p style={{ fontSize: "clamp(18px,1.6vw,23px)", lineHeight: "1.35", margin: "0", textWrap: "pretty" }}>
                  {I(v.P3.claim)}
                </p>
                {" "}
                <ul style={{ listStyle: "none", margin: "0", padding: "0", display: "flex", flexDirection: "column", borderTop: "1px solid #57534A" }}>
                  {" "}
                  {v.P3.proofs.map((p, i0) => (
                    <Fragment key={i0}>
                      <li style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", justifyContent: "space-between", alignItems: "baseline", padding: "11px 0", borderBottom: "1px solid #3A382F", fontSize: "14.5px", lineHeight: "1.45" }}>
                        <span style={{ flex: "1 1 260px" }}>
                          {I(p.txt)}
                        </span>
                        <button onClick={p.open} style={{ background: "transparent", border: "1px solid #F0ECE3", color: "#F0ECE3", padding: "3px 7px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px" }} className="dc-h7">
                          {"↗ "}{I(p.s)}
                        </button>
                      </li>
                    </Fragment>
                  ))}
                  {" "}
                </ul>
                {" "}
              </div>
              {" "}
              <div style={{ flex: "1 1 460px", minWidth: "0", background: "#F7F4EC", color: "#16150F", display: "flex", flexDirection: "column" }}>
                {" "}
                <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "9px 16px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
                  <span>
                    {I(v.t.pillars.rep.title)}
                  </span>
                  <span style={{ color: "#2B35F0" }}>
                    {"EV-053"}
                  </span>
                </div>
                {" "}
                <div style={{ padding: "18px", display: "flex", flexDirection: "column", gap: "12px" }}>
                  {" "}
                  <div style={{ background: "#16150F", color: "#F0ECE3", padding: "16px", minHeight: "240px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "12px", lineHeight: "1.85", display: "flex", flexDirection: "column" }}>
                    {" "}
                    {v.reproLines.map((l, i0) => (
                      <Fragment key={i0}>
                        <span style={{ color: l.c, fontWeight: l.w }}>
                          {I(l.t)}
                        </span>
                      </Fragment>
                    ))}
                    {" "}
                    <span style={{ color: "#8F8A7E" }}>
                      {I(v.reproCursor)}
                    </span>
                    {" "}
                  </div>
                  {" "}
                  <button onClick={v.runRepro} style={{ alignSelf: "flex-start", background: "#2B35F0", color: "#fff", border: "0", padding: "10px 14px", fontWeight: "600", fontSize: "14px" }} className="dc-h8">
                    {I(v.t.pillars.rep.run)}{" · make repro"}
                  </button>
                  {" "}
                </div>
                {" "}
              </div>
              {" "}
            </article>
            {" "}
          </div>
          {" "}
        </section>
        {" "}
        <section id="resultados" style={{ position: "relative", pointerEvents: "auto", background: "#F0ECE3", padding: "clamp(64px,11vh,128px) clamp(16px,4vw,56px)", scrollMarginTop: "56px" }}>
          {" "}
          <div style={{ maxWidth: "1320px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "28px" }}>
            {" "}
            <p style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", letterSpacing: ".04em", textTransform: "uppercase", margin: "0", display: "flex", gap: "10px", alignItems: "center" }}>
              <span style={{ width: "8px", height: "8px", background: "#2B35F0", display: "inline-block" }}></span>
              {I(v.t.results.kicker)}{" · VAL-019"}
            </p>
            {" "}
            <h2 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".88", margin: "0", fontSize: "clamp(44px,6.4vw,104px)", maxWidth: "1100px", textWrap: "balance" }}>
              {I(v.t.results.title)}
            </h2>
            {" "}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "14px 28px", alignItems: "flex-start" }}>
              {" "}
              <div style={{ display: "flex", gap: "10px", alignItems: "center", border: "1px solid #16150F", padding: "10px 14px", background: "#F7F4EC" }}>
                <span style={{ width: "10px", height: "10px", background: "#FF5520" }}></span>
                <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", textTransform: "uppercase", fontWeight: "600" }}>
                  {I(v.t.results.status)}
                </span>
              </div>
              {" "}
              <p style={{ flex: "1 1 420px", margin: "0", fontSize: "16px", lineHeight: "1.5", maxWidth: "640px" }}>
                {I(v.t.results.statusNote)}
              </p>
              {" "}
            </div>
            {" "}
            <ul style={{ listStyle: "none", margin: "0", padding: "0", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: "0", borderTop: "1px solid #16150F" }}>
              {" "}
              {v.t.results.setup.map((x, i0) => (
                <Fragment key={i0}>
                  <li style={{ padding: "14px 16px 14px 0", borderBottom: "1px solid #CFC7B8", fontSize: "14px", lineHeight: "1.45" }}>
                    {I(x)}
                  </li>
                </Fragment>
              ))}
              {" "}
            </ul>
            {" "}
            <div style={{ overflowX: "auto", border: "1px solid #16150F", background: "#F7F4EC" }}>
              {" "}
              <div style={{ minWidth: "1080px", display: "grid", gridTemplateColumns: "200px repeat(9,minmax(0,1fr))" }}>
                {" "}
                <div style={{ padding: "12px 14px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontSize: "10px", textTransform: "uppercase", color: "#57534A" }}>
                  {"ES + PT · n = 80"}
                </div>
                {" "}
                {v.t.results.cols.map((c, i0) => (
                  <Fragment key={i0}>
                    <div style={{ padding: "12px 10px", borderBottom: "1px solid #16150F", borderLeft: "1px solid #CFC7B8", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "9.5px", lineHeight: "1.35", textTransform: "uppercase" }}>
                      {I(c)}
                    </div>
                  </Fragment>
                ))}
                {" "}
                {v.resRows.map((r, i0) => (
                  <Fragment key={i0}>
                    {" "}
                    <div style={{ padding: "16px 14px", borderBottom: "1px solid #CFC7B8", fontSize: "13.5px", fontWeight: "600" }}>
                      {I(r.l)}
                    </div>
                    {" "}
                    {r.cells.map((c, i1) => (
                      <Fragment key={i1}>
                        <div style={{ padding: "16px 10px", borderBottom: "1px solid #CFC7B8", borderLeft: "1px solid #CFC7B8", fontFamily: "'Martian Mono',monospace", fontSize: "12px", color: "#57534A", background: "repeating-linear-gradient(135deg,transparent 0 7px,rgba(22,21,15,.06) 7px 8px)" }}>
                          {I(c)}
                        </div>
                      </Fragment>
                    ))}
                    {" "}
                  </Fragment>
                ))}
                {" "}
              </div>
              {" "}
            </div>
            {" "}
            <p style={{ margin: "0", fontSize: "14px", lineHeight: "1.5", color: "#57534A", maxWidth: "860px" }}>
              {I(v.t.results.t2)}{" "}
              <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "10.5px", color: "#2B35F0" }}>
                {"VAL-019a"}
              </span>
            </p>
            {" "}
            <div style={{ display: "flex", flexDirection: "column", gap: "14px", marginTop: "18px" }}>
              {" "}
              <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".9", margin: "0", fontSize: "clamp(32px,3.4vw,52px)" }}>
                {I(v.t.results.outTitle)}
              </h3>
              {" "}
              <p style={{ margin: "0", fontSize: "15px", lineHeight: "1.5", maxWidth: "640px" }}>
                {I(v.t.results.outIntro)}
              </p>
              {" "}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: "12px" }}>
                {" "}
                {v.outItems.map((o, i0) => (
                  <Fragment key={i0}>
                    {" "}
                    <button onClick={o.open} style={{ textAlign: "left", background: "#F7F4EC", border: "1px solid #16150F", borderStyle: o.bs, padding: "16px", display: "flex", flexDirection: "column", gap: "10px" }} className="dc-h12">
                      {" "}
                      <span style={{ display: "flex", justifyContent: "space-between", gap: "8px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
                        <span style={{ color: "#2B35F0" }}>
                          {"↗ "}{I(o.id)}
                        </span>
                        <span>
                          {I(o.tag)}
                        </span>
                      </span>
                      {" "}
                      <span style={{ fontSize: "14.5px", lineHeight: "1.45" }}>
                        {I(o.txt)}
                      </span>
                      {" "}
                    </button>
                    {" "}
                  </Fragment>
                ))}
                {" "}
              </div>
              {" "}
            </div>
            {" "}
          </div>
          {" "}
        </section>
        {" "}
        <footer style={{ position: "relative", pointerEvents: "auto", background: "#2B35F0", color: "#fff", padding: "clamp(64px,11vh,128px) clamp(16px,4vw,56px) 120px" }}>
          {" "}
          <div style={{ maxWidth: "1320px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "36px" }}>
            {" "}
            <blockquote style={{ margin: "0", display: "flex", flexDirection: "column", gap: "14px" }}>
              {" "}
              <p style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".86", margin: "0", fontSize: "clamp(50px,8.4vw,136px)", textWrap: "balance" }}>
                {"“"}{I(v.t.footer.quote)}{"”"}
              </p>
              {" "}
              <cite style={{ fontStyle: "normal", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", textTransform: "uppercase" }}>
                {I(v.t.footer.cite)}
              </cite>
              {" "}
            </blockquote>
            {" "}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "center" }}>
              {" "}
              <a href={v.appUrl} target="_blank" rel="noopener" style={{ background: "#F0ECE3", color: "#16150F", textDecoration: "none", fontWeight: "700", fontSize: "17px", padding: "16px 22px" }} className="dc-h13">
                {I(v.t.ui.app)}{" ↗"}
              </a>
              {" "}
              <a href={v.guideUrl} target="_blank" rel="noopener" style={{ color: "#fff", textDecoration: "none", fontWeight: "600", fontSize: "15px", padding: "15px 18px", border: "1px solid #fff", display: "flex", flexDirection: "column", gap: "2px" }} className="dc-h14">
                <span>
                  {I(v.t.footer.guide)}{" ↗"}
                </span>
                <span style={{ fontSize: "12px", fontWeight: "400" }}>
                  {I(v.t.footer.guideSub)}
                </span>
              </a>
              {" "}
            </div>
            {" "}
            <p style={{ margin: "0", fontSize: "15px", lineHeight: "1.5", maxWidth: "620px" }}>
              {I(v.t.footer.note)}
            </p>
            {" "}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "24px 48px", borderTop: "1px solid rgba(255,255,255,.5)", paddingTop: "22px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", lineHeight: "1.8" }}>
              {" "}
              <div style={{ display: "flex", flexDirection: "column", gap: "2px", flex: "1 1 320px" }}>
                <span style={{ textTransform: "uppercase" }}>
                  {I(v.t.footer.srcTitle)}
                </span>
                {v.t.footer.srcs.map((x, i0) => (
                  <Fragment key={i0}>
                    <span>
                      {I(x)}
                    </span>
                  </Fragment>
                ))}
              </div>
              {" "}
              <div style={{ display: "flex", flexDirection: "column", gap: "10px", flex: "0 1 360px" }}>
                <span>
                  {I(v.t.footer.proto)}
                </span>
                <button onClick={v.toggleMotion} style={{ alignSelf: "flex-start", background: "transparent", border: "1px solid #fff", color: "#fff", padding: "6px 10px", fontFamily: "'Martian Mono',monospace", fontSize: "10px", textTransform: "uppercase" }}>
                  {I(v.t.ui.motion)}{" · "}{I(v.motionLabel)}
                </button>
              </div>
              {" "}
            </div>
            {" "}
          </div>
          {" "}
        </footer>
      </main>
      {v.hasDrawer ? (
        <>
          {" "}
          <aside role="dialog" aria-label={v.dw.title} style={{ position: "fixed", top: "56px", right: "0", bottom: "0", zIndex: "65", width: "min(460px,100vw)", background: "#F7F4EC", borderLeft: "1px solid #16150F", overflowY: "auto", display: "flex", flexDirection: "column" }}>
            {" "}
            <div style={{ position: "sticky", top: "0", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", padding: "10px 16px", borderBottom: "1px solid #16150F", background: "#F7F4EC", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
              <span style={{ color: "#2B35F0" }}>
                {I(v.dw.kicker)}
              </span>
              <button onClick={v.closeDrawer} style={{ background: "#16150F", color: "#F0ECE3", border: "0", padding: "6px 10px", fontFamily: "'Martian Mono',monospace", fontSize: "10px", textTransform: "uppercase" }}>
                {I(v.t.ui.close)}{" ✕"}
              </button>
            </div>
            {" "}
            <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "16px" }}>
              {" "}
              <h3 style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", textTransform: "uppercase", lineHeight: ".9", margin: "0", fontSize: "44px" }}>
                {I(v.dw.title)}
              </h3>
              {" "}
              {v.dw.isNode ? (
                <>
                  {" "}
                  <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                    {" "}
                    <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", color: "#57534A" }}>
                      {I(v.dw.sub)}
                    </span>
                    {" "}
                    {v.dw.planned ? (
                      <>
                        <span style={{ alignSelf: "flex-start", border: "1px dashed #16150F", padding: "6px 10px", fontFamily: "'Martian Mono',monospace", fontSize: "10px", textTransform: "uppercase" }}>
                          {I(v.t.ui.planned)}{" · DEV-042"}
                        </span>
                      </>
                    ) : null}
                    {" "}
                    <p style={{ margin: "0", fontSize: "15.5px", lineHeight: "1.5" }}>
                      {I(v.dw.does)}
                    </p>
                    {" "}
                    <ul style={{ listStyle: "none", margin: "0", padding: "0", display: "flex", flexDirection: "column", gap: "7px" }}>
                      {v.dw.protects.map((p, i0) => (
                        <Fragment key={i0}>
                          <li style={{ display: "grid", gridTemplateColumns: "12px 1fr", gap: "8px", fontSize: "14px", lineHeight: "1.45" }}>
                            <span style={{ width: "6px", height: "6px", background: "#16150F", marginTop: "7px" }}></span>
                            <span>
                              {I(p)}
                            </span>
                          </li>
                        </Fragment>
                      ))}
                    </ul>
                    {" "}
                    {v.dw.hasStat ? (
                      <>
                        {" "}
                        <button onClick={v.dw.openStat} style={{ textAlign: "left", background: "transparent", border: "0", borderTop: "1px solid #16150F", padding: "14px 0 0", display: "flex", flexDirection: "column", gap: "6px" }}>
                          <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "56px", lineHeight: ".9", color: "#2B35F0" }}>
                            {I(v.dw.statV)}
                          </span>
                          <span style={{ fontSize: "13.5px" }}>
                            {I(v.dw.statL)}
                          </span>
                          <span style={{ fontFamily: "'Martian Mono',monospace", fontSize: "10px", color: "#2B35F0" }}>
                            {"↗ "}{I(v.dw.statS)}
                          </span>
                        </button>
                        {" "}
                      </>
                    ) : null}
                    {" "}
                    {v.dw.hasModel ? (
                      <>
                        <button onClick={v.dw.goModel} style={{ alignSelf: "flex-start", background: "#16150F", color: "#F0ECE3", border: "0", padding: "9px 13px", fontWeight: "600", fontSize: "13.5px" }}>
                          {I(v.dw.modelLbl)}{" →"}
                        </button>
                      </>
                    ) : null}
                    {" "}
                  </div>
                  {" "}
                </>
              ) : null}
              {" "}
              {v.dw.isRules ? (
                <>
                  {" "}
                  <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                    {" "}
                    <p style={{ margin: "0", fontSize: "14.5px", lineHeight: "1.5" }}>
                      {I(v.t.rules.sub)}
                    </p>
                    {" "}
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 12px" }}>
                      {v.ruleCats.map((c, i0) => (
                        <Fragment key={i0}>
                          <span style={{ display: "flex", gap: "6px", alignItems: "center", fontSize: "12px" }}>
                            <span style={{ width: "12px", height: "12px", background: c.bg, border: "1px solid #16150F", borderStyle: c.bs }}></span>
                            {I(c.l)}
                          </span>
                        </Fragment>
                      ))}
                    </div>
                    {" "}
                    <div style={{ display: "flex", flexDirection: "column", borderTop: "1px solid #16150F" }}>
                      {" "}
                      {v.ruleRows.map((r, i0) => (
                        <Fragment key={i0}>
                          {" "}
                          <div style={{ display: "grid", gridTemplateColumns: "118px 1fr", gap: "10px", padding: "9px 0", borderBottom: "1px solid #CFC7B8", alignItems: "start" }}>
                            {" "}
                            <span style={{ alignSelf: "start", justifySelf: "start", padding: "3px 6px", background: r.bg, color: r.fg, border: "1px solid #16150F", borderStyle: r.bs, fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", fontWeight: "600" }}>
                              {I(r.id)}
                            </span>
                            {" "}
                            <span style={{ fontSize: "13.5px", lineHeight: "1.45" }}>
                              {I(r.d)}
                            </span>
                            {" "}
                          </div>
                          {" "}
                        </Fragment>
                      ))}
                      {" "}
                    </div>
                    {" "}
                  </div>
                  {" "}
                </>
              ) : null}
              {" "}
            </div>
            {" "}
          </aside>
        </>
      ) : null}
      {v.hasSrc ? (
        <>
          {" "}
          <div role="dialog" aria-label={v.t.ui.source} style={{ position: "fixed", left: "16px", bottom: "84px", zIndex: "70", width: "min(360px,calc(100vw - 32px))", background: "#FFFDF7", border: "1px solid #16150F", boxShadow: "0 20px 40px -24px rgba(22,21,15,.5)", display: "flex", flexDirection: "column" }}>
            {" "}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "10px", padding: "9px 14px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
              <span>
                {I(v.t.ui.source)}
              </span>
              <button onClick={v.closeSrc} style={{ background: "transparent", border: "0", fontFamily: "'Martian Mono',monospace", fontSize: "11px" }}>
                {"✕"}
              </button>
            </div>
            {" "}
            <div style={{ padding: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
              {" "}
              <span style={{ fontFamily: "'Archivo',sans-serif", fontStretch: "62%", fontWeight: "800", fontSize: "36px", lineHeight: ".9", color: "#2B35F0" }}>
                {I(v.sv.id)}
              </span>
              {" "}
              <span style={{ alignSelf: "flex-start", background: v.sv.bg, color: v.sv.fg, border: "1px solid #16150F", borderStyle: v.sv.bs, padding: "4px 8px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", textTransform: "uppercase" }}>
                {I(v.sv.kind)}
              </span>
              {" "}
              <span style={{ fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "11px", overflowWrap: "anywhere" }}>
                {I(v.sv.where)}
              </span>
              {" "}
              <p style={{ margin: "0", fontSize: "13.5px", lineHeight: "1.45", color: "#57534A" }}>
                {I(v.sv.note)}
              </p>
              {" "}
            </div>
            {" "}
          </div>
        </>
      ) : null}
      {v.dockOpen ? (
        <>
          {" "}
          <div role="dialog" aria-label={v.t.dock.title} style={{ position: "fixed", right: "clamp(8px,2vw,20px)", bottom: "76px", zIndex: "60", width: "min(430px,calc(100vw - 16px))", maxHeight: "calc(100vh - 150px)", background: "#F7F4EC", border: "1px solid #16150F", display: "flex", flexDirection: "column", boxShadow: "0 24px 48px -28px rgba(22,21,15,.55)" }}>
            {" "}
            <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "9px 12px", borderBottom: "1px solid #16150F", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", textTransform: "uppercase" }}>
              {" "}
              <span style={{ marginRight: "auto" }}>
                {I(v.t.dock.title)}
              </span>
              {" "}
              <div style={{ display: "flex", border: "1px solid #16150F" }}>
                {v.convLangs.map((l, i0) => (
                  <Fragment key={i0}>
                    <button onClick={l.pick} style={{ border: "0", padding: "4px 7px", fontFamily: "'Martian Mono',monospace", fontSize: "10px", background: l.bg, color: l.fg }}>
                      {I(l.code)}
                    </button>
                  </Fragment>
                ))}
              </div>
              {" "}
              <button onClick={v.newConv} style={{ background: "transparent", border: "1px solid #16150F", padding: "4px 7px", fontFamily: "'Martian Mono',monospace", fontSize: "10px", textTransform: "uppercase" }}>
                {I(v.t.dock.newConv)}
              </button>
              {" "}
              <button onClick={v.toggleDock} aria-label={v.t.ui.close} style={{ background: "#16150F", color: "#F0ECE3", border: "0", padding: "4px 8px", fontFamily: "'Martian Mono',monospace", fontSize: "11px" }}>
                {"✕"}
              </button>
              {" "}
            </div>
            {" "}
            <div ref={v.convRef} style={{ flex: "1 1 auto", overflowY: "auto", padding: "14px 12px", display: "flex", flexDirection: "column", gap: "10px", minHeight: "120px" }}>
              {" "}
              {v.convItems.map((m, i0) => (
                <Fragment key={i0}>
                  {" "}
                  {m.isC ? (
                    <>
                      <div style={{ alignSelf: "flex-end", maxWidth: "84%", background: "#16150F", color: "#F0ECE3", padding: "9px 12px", fontSize: "14px", lineHeight: "1.4" }}>
                        {I(m.text)}
                      </div>
                    </>
                  ) : null}
                  {" "}
                  {m.isS ? (
                    <>
                      {" "}
                      <div style={{ alignSelf: "flex-start", maxWidth: "92%", display: "flex", flexDirection: "column", gap: "6px" }}>
                        {" "}
                        <div style={{ background: "#FFFDF7", border: "1px solid #16150F", borderColor: m.bc, padding: "10px 12px", fontSize: "14px", lineHeight: "1.45", display: "flex", flexDirection: "column", gap: "6px" }}>
                          {" "}
                          {m.human ? (
                            <>
                              <span style={{ alignSelf: "flex-start", background: "#FF5520", color: "#16150F", padding: "2px 6px", fontFamily: "'Martian Mono',monospace", fontSize: "9.5px", textTransform: "uppercase", fontWeight: "600" }}>
                                {I(m.humanL)}
                              </span>
                            </>
                          ) : null}
                          {" "}
                          <span>
                            {I(m.text)}
                          </span>
                          {" "}
                        </div>
                        {" "}
                        {m.hasOpts ? (
                          <>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
                              {m.opts.map((o, i1) => (
                                <Fragment key={i1}>
                                  <button onClick={o.pick} style={{ border: "1px solid #2B35F0", background: "#FFFDF7", color: "#2B35F0", padding: "7px 10px", fontSize: "13px", fontWeight: "600", textAlign: "left" }} className="dc-h10">
                                    {I(o.l)}
                                  </button>
                                </Fragment>
                              ))}
                            </div>
                          </>
                        ) : null}
                        {" "}
                        {/* O aviso de falha da API não tem "Por que esta resposta?" (não houve turno). */}
                        {m.whyL ? (
                          <button onClick={m.toggleWhy} style={{ alignSelf: "flex-start", background: "transparent", border: "0", borderBottom: "1px solid #2B35F0", padding: "1px 0", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10px", color: "#2B35F0", textTransform: "uppercase" }}>
                            {I(m.whyL)}{" "}{I(m.whyArrow)}
                          </button>
                        ) : null}
                        {" "}
                        {m.whyOpen ? (
                          <>
                            {" "}
                            <div style={{ background: "#FFFDF7", border: "1px dashed #16150F", padding: "10px 12px", display: "grid", gridTemplateColumns: "auto 1fr", columnGap: "12px", rowGap: "3px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "10.5px", lineHeight: "1.5" }}>
                              {" "}
                              {m.rows.map((r, i1) => (
                                <Fragment key={i1}>
                                  <span style={{ color: "#57534A", textTransform: "uppercase", fontSize: "9.5px" }}>
                                    {I(r.k)}
                                  </span>
                                  {/* Os valores da API de verdade podem ser longos e sem espaço (o arquivo do
                                      recibo): quebram em qualquer ponto, em vez de empurrar a grade. */}
                                  <span style={{ textAlign: "right", overflowWrap: "anywhere" }}>
                                    {I(r.v)}
                                  </span>
                                </Fragment>
                              ))}
                              {" "}
                            </div>
                            {" "}
                          </>
                        ) : null}
                        {" "}
                      </div>
                      {" "}
                    </>
                  ) : null}
                  {" "}
                </Fragment>
              ))}
              {" "}
              {v.convEmpty ? (
                <>
                  <p style={{ margin: "0", fontSize: "13.5px", lineHeight: "1.45", color: "#57534A" }}>
                    {I(v.t.map.body)}
                  </p>
                </>
              ) : null}
              {" "}
            </div>
            {" "}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", padding: "10px 12px", borderTop: "1px solid #CFC7B8" }}>
              {" "}
              {v.chips.map((c, i0) => (
                <Fragment key={i0}>
                  <button onClick={c.go} style={{ border: "1px solid #16150F", background: "#FFFDF7", padding: "5px 8px", fontSize: "12px" }} className="dc-h6">
                    {I(c.l)}
                  </button>
                </Fragment>
              ))}
              {" "}
            </div>
            {" "}
            <div style={{ display: "flex", gap: "6px", padding: "0 12px 10px" }}>
              {" "}
              <input value={v.draft} onChange={v.onDraft} onKeyDown={v.onKey} placeholder={v.t.dock.placeholder} aria-label={v.t.dock.placeholder} style={{ flex: "1 1 auto", minWidth: "0", border: "1px solid #16150F", background: "#FFFDF7", padding: "10px 12px", fontFamily: "'Archivo',sans-serif", fontSize: "14px", color: "#16150F", outline: "none" }} />
              {" "}
              <button onClick={v.onSend} style={{ background: "#2B35F0", color: "#fff", border: "0", padding: "0 14px", fontWeight: "600", fontSize: "14px" }}>
                {I(v.t.dock.send)}
              </button>
              {" "}
            </div>
            {" "}
            <p style={{ margin: "0", padding: "0 12px 10px", fontFamily: "'Martian Mono',monospace", fontStretch: "87.5%", fontSize: "9.5px", lineHeight: "1.5", color: "#57534A" }}>
              {I(v.t.dock.note)}
            </p>
            {" "}
          </div>
        </>
      ) : null}
      <div style={{ position: "fixed", left: "50%", bottom: "14px", transform: "translateX(-50%)", zIndex: "60", display: "flex", gap: "6px", pointerEvents: "auto" }}>
        {" "}
        <button onClick={v.toggleDock} aria-expanded={v.dockOpen} style={{ display: "flex", alignItems: "center", gap: "10px", background: "#16150F", color: "#F0ECE3", border: "1px solid #57534A", padding: "12px 18px", fontWeight: "600", fontSize: "14.5px", whiteSpace: "nowrap" }} className="dc-h5">
          <span style={{ width: "8px", height: "8px", background: "#FF5520", display: "inline-block" }}></span>
          {I(v.t.dock.open)}
        </button>
        {" "}
        <a href={v.appUrl} target="_blank" rel="noopener" style={{ display: "flex", alignItems: "center", background: "#2B35F0", color: "#fff", textDecoration: "none", padding: "12px 16px", fontWeight: "600", fontSize: "14.5px", border: "1px solid #2B35F0", whiteSpace: "nowrap" }} className="dc-h15">
          {I(v.appShort)}{" ↗"}
        </a>
      </div>
    </div>
    );
  }
}
