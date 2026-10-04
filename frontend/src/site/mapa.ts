// O mapa da arquitetura do site (DEV-032a): os componentes, as ligações, o caminho de uma mensagem e o
// dos dados, e os quadros da câmera presos à rolagem. Igual ao design (04-solucao/design-do-site no
// vault), com as mesmas contas na mesma ordem, para a câmera e o caminho caírem no mesmo lugar.

export type IdDoNo =
  | "navegador"
  | "caddy"
  | "portao"
  | "sessao"
  | "regras"
  | "leitor"
  | "llm"
  | "etapas"
  | "qual"
  | "politica"
  | "acoes"
  | "banco"
  | "bucket"
  | "manifesto"
  | "raw"
  | "curada";

/** Forma do componente: tela, caixa, portão, banco, bucket ou folhas empilhadas. */
export type FormaDoNo = "screen" | "box" | "gate" | "db" | "bucket" | "sheet";

export interface No {
  readonly x: number;
  readonly y: number;
  readonly k: FormaDoNo;
  readonly h?: number;
  readonly w?: number;
  /** Planejado: desenhado tracejado e transparente. */
  readonly plan?: 1;
}

export const NOS: Readonly<Record<IdDoNo, No>> = {
  navegador: { x: 0, y: 0, k: "screen" },
  caddy: { x: 2.1, y: 0, k: "box", h: 0.5 },
  portao: { x: 4.2, y: 0, k: "gate" },
  sessao: { x: 6.2, y: 0, k: "box", h: 0.5 },
  regras: { x: 8.2, y: 0, k: "box", h: 0.55 },
  leitor: { x: 8.2, y: 1.7, k: "box", h: 0.4, w: 0.7 },
  llm: { x: 8.2, y: 3.2, k: "box", h: 0.4, w: 0.7, plan: 1 },
  etapas: { x: 10.2, y: 0, k: "box", h: 0.5 },
  qual: { x: 12.2, y: 0, k: "box", h: 0.5 },
  politica: { x: 14.2, y: 0, k: "box", h: 0.95, w: 0.95 },
  acoes: { x: 16.2, y: 0, k: "box", h: 0.6 },
  banco: { x: 16.2, y: 5.6, k: "db" },
  bucket: { x: 6.2, y: 5.6, k: "bucket" },
  manifesto: { x: 8.7, y: 5.6, k: "sheet" },
  raw: { x: 11.2, y: 5.6, k: "sheet" },
  curada: { x: 13.7, y: 5.6, k: "sheet" },
};

/** A ordem de criação dos rótulos e dos objetos é a das chaves de NOS. */
export const IDS_DOS_NOS = Object.keys(NOS) as IdDoNo[];

/**
 * m: caminho da mensagem; d: caminho dos dados; c: cascata da leitura; p: planejado; l: a cascata até
 * o LLM, que o design desenhou planejada e o main já tem (fatos.ts).
 */
export type TipoDeLigacao = "m" | "c" | "p" | "d" | "l";

export const LIGACOES: readonly (readonly [IdDoNo, IdDoNo, number, TipoDeLigacao])[] = [
  ["navegador", "caddy", 0, "m"],
  ["caddy", "portao", 0, "m"],
  ["portao", "sessao", 0, "m"],
  ["sessao", "regras", 0, "m"],
  ["regras", "etapas", 0, "m"],
  ["etapas", "qual", 0, "m"],
  ["qual", "politica", 0, "m"],
  ["politica", "acoes", 0, "m"],
  ["acoes", "banco", 0, "m"],
  ["regras", "leitor", 0, "c"],
  ["leitor", "llm", 0, "p"],
  ["leitor", "etapas", 0.5, "c"],
  ["llm", "etapas", 0.9, "p"],
  ["bucket", "manifesto", 0, "d"],
  ["manifesto", "raw", 0, "d"],
  ["raw", "curada", 0, "d"],
  ["curada", "banco", 0, "d"],
];

/** Os componentes e as ligações de um mapa: o do design ou o do main (fatos.ts). */
export interface Mapa {
  readonly nos: Readonly<Record<IdDoNo, No>>;
  readonly ligacoes: readonly (readonly [IdDoNo, IdDoNo, number, TipoDeLigacao])[];
}

export const MAPA_DO_DESIGN: Mapa = { nos: NOS, ligacoes: LIGACOES };

/** O caminho de uma mensagem e o caminho dos dados. */
export const MENSAGEM: readonly IdDoNo[] = [
  "navegador",
  "caddy",
  "portao",
  "sessao",
  "regras",
  "etapas",
  "qual",
  "politica",
  "acoes",
  "banco",
];
export const DADOS: readonly IdDoNo[] = ["bucket", "manifesto", "raw", "curada", "banco"];

/** Um quadro da câmera por bloco da rolagem (f: o foco; r: a distância; th e ph: os ângulos). */
export interface QuadroDoDesign {
  readonly f: "center" | IdDoNo | readonly [number, number, number];
  readonly ty?: number;
  readonly r: number | "fit";
  readonly th: number;
  readonly ph: number;
  readonly ox?: number;
  readonly oy?: number;
  readonly m: IdDoNo;
  readonly d?: IdDoNo;
}

export const QUADROS: readonly QuadroDoDesign[] = [
  { f: "center", ty: 1.4, r: 27, th: -26, ph: 22, ox: -0.06, oy: -0.26, m: "navegador" },
  { f: "center", r: 22, th: -10, ph: 40, ox: -0.22, m: "navegador" },
  { f: "navegador", r: 6.2, th: -28, ph: 26, m: "navegador" },
  { f: "portao", r: 7.4, th: -16, ph: 30, m: "portao" },
  { f: "sessao", r: 6, th: 18, ph: 34, m: "sessao" },
  { f: [8.4, 0.3, 1.5], r: 8.2, th: -32, ph: 44, m: "regras" },
  { f: "etapas", r: 6, th: 20, ph: 30, m: "etapas" },
  { f: "qual", r: 6, th: -16, ph: 34, m: "qual" },
  { f: "politica", r: 6.6, th: 24, ph: 24, m: "politica" },
  { f: "acoes", r: 6, th: -20, ph: 32, m: "acoes" },
  { f: "banco", r: 7.4, th: 18, ph: 34, ox: -0.36, m: "banco" },
  { f: "bucket", r: 7, th: -20, ph: 36, m: "banco", d: "bucket" },
  { f: "manifesto", r: 6, th: 14, ph: 32, m: "banco", d: "manifesto" },
  { f: "raw", r: 6, th: -14, ph: 34, m: "banco", d: "raw" },
  { f: "curada", r: 6, th: 16, ph: 32, m: "banco", d: "curada" },
  { f: "banco", r: 7.4, th: -22, ph: 36, m: "banco", d: "banco" },
  { f: "center", r: "fit", th: 0, ph: 58, m: "banco", d: "banco" },
];

export type Ponto = [number, number, number];

export interface Ligacao {
  readonly a: IdDoNo;
  readonly b: IdDoNo;
  readonly ty: TipoDeLigacao;
  readonly pts: Ponto[];
  /** Comprimento em 3D e projetado no chão (o do traço no mapa 2D). */
  readonly len: number;
  readonly len2: number;
}

export interface Caminho {
  readonly pts: Ponto[];
  readonly cum: number[];
  readonly total: number;
  /** Onde cada componente fica no caminho, de 0 a 1. */
  readonly par: Partial<Record<IdDoNo, number>>;
  readonly ids: readonly IdDoNo[];
}

const comprimento = (pts: Ponto[]): number => {
  let l = 0;
  for (let i = 1; i < pts.length; i++) {
    const a = ponto(pts, i - 1);
    const b = ponto(pts, i);
    l += Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
  }
  return l;
};

function ponto(pts: readonly Ponto[], i: number): Ponto {
  const p = pts[i];
  if (!p) throw new RangeError(`ponto ${i} fora do caminho`);
  return p;
}

/** As ligações como curvas de Bézier quadráticas, com 29 pontos, arqueadas no caminho principal. */
export function construirLigacoes(mapa: Mapa): Ligacao[] {
  return mapa.ligacoes.map(([a, b, bend, ty]) => {
    const A = mapa.nos[a];
    const B = mapa.nos[b];
    const dx = B.x - A.x;
    const dy = B.y - A.y;
    const L = Math.hypot(dx, dy) || 1;
    const cx = (A.x + B.x) / 2 + (-dy / L) * bend * L * 0.5;
    const cy = (A.y + B.y) / 2 + (dx / L) * bend * L * 0.5;
    const pts: Ponto[] = [];
    for (let i = 0; i <= 28; i++) {
      const u = i / 28;
      const x = (1 - u) * (1 - u) * A.x + 2 * (1 - u) * u * cx + u * u * B.x;
      const y = (1 - u) * (1 - u) * A.y + 2 * (1 - u) * u * cy + u * u * B.y;
      const h = ty === "m" || ty === "d" ? 0.3 + 0.22 * Math.sin(Math.PI * u) : 0.3;
      pts.push([x, h, y]);
    }
    let l2 = 0;
    for (let i = 1; i < pts.length; i++) {
      const p = ponto(pts, i);
      const q = ponto(pts, i - 1);
      l2 += Math.hypot(p[0] - q[0], p[2] - q[2]);
    }
    return { a, b, ty, pts, len: comprimento(pts), len2: l2 };
  });
}

/** O caminho contínuo por uma sequência de componentes, com a posição de cada um de 0 a 1. */
export function caminho(ligacoes: readonly Ligacao[], ids: readonly IdDoNo[]): Caminho {
  const pts: Ponto[] = [];
  const marcas: Partial<Record<IdDoNo, number>> = {};
  ids.forEach((id, i) => {
    if (i === 0) {
      marcas[id] = 0;
      return;
    }
    const e = ligacoes.find((l) => l.a === ids[i - 1] && l.b === id);
    if (!e) throw new Error(`sem ligação de ${String(ids[i - 1])} para ${id}`);
    e.pts.forEach((p, j) => {
      if (j === 0 && pts.length) return;
      pts.push(p);
    });
    marcas[id] = pts.length - 1;
  });
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    const a = ponto(pts, i - 1);
    const b = ponto(pts, i);
    cum.push((cum[i - 1] ?? 0) + Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]));
  }
  const total = cum[cum.length - 1] ?? 0;
  const par: Partial<Record<IdDoNo, number>> = {};
  for (const k of Object.keys(marcas) as IdDoNo[]) par[k] = (cum[marcas[k] ?? 0] ?? 0) / total;
  return { pts, cum, total, par, ids };
}

/** O ponto do caminho em u (de 0 a 1) e a direção dele. */
export function pontoNoCaminho(R: Caminho, u: number): { p: Ponto; d: Ponto } {
  const L = Math.max(0, Math.min(1, u)) * R.total;
  let lo = 0;
  let hi = R.cum.length - 1;
  while (hi - lo > 1) {
    const m = (lo + hi) >> 1;
    if ((R.cum[m] ?? 0) <= L) lo = m;
    else hi = m;
  }
  const a = ponto(R.pts, lo);
  const b = ponto(R.pts, hi);
  const cLo = R.cum[lo] ?? 0;
  const seg = (R.cum[hi] ?? 0) - cLo || 1;
  const f = Math.max(0, Math.min(1, (L - cLo) / seg));
  return {
    p: [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f],
    d: [b[0] - a[0], b[1] - a[1], b[2] - a[2]],
  };
}

/** Curva da transição entre dois quadros (cúbica, entra e sai devagar). */
export function suavizar(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

export interface QuadroCalculado {
  tg: readonly [number, number, number];
  r: number;
  th: number;
  ph: number;
  ox: number;
  oy: number;
  mu: number;
  du: number;
  node: IdDoNo | null;
}

/**
 * O que a página mede para a câmera (design de 03/10): o retângulo livre do mapa (sem o cartão do mapa,
 * a barra do dock, o painel e a gaveta), a borda direita livre e a borda direita do conteúdo de cada
 * bloco. Sem DOM, os padrões do design: a tela menos as margens e o conteúdo até o meio da tela.
 */
export interface Medidas {
  readonly livre?: { readonly l: number; readonly t: number; readonly r: number; readonly b: number };
  readonly direita?: number;
  readonly bordaDoBloco?: readonly number[];
}

/** O quadro i da câmera para a janela W×H; no celular, mais longe e centrado. */
export function quadro(
  i: number,
  W: number,
  H: number,
  msg: Caminho,
  dados: Caminho,
  nos: Mapa["nos"] = NOS,
  medidas: Medidas = {},
): QuadroCalculado {
  const K = QUADROS[i];
  if (!K) throw new RangeError(`quadro ${i} inexistente`);
  const mob = W < 760;
  let tg: readonly [number, number, number];
  if (K.f === "center") tg = [8.1, K.ty || 0.2, 2.6];
  else if (Array.isArray(K.f)) tg = K.f as readonly [number, number, number];
  else {
    const n = nos[K.f as IdDoNo];
    tg = [n.x, 0.35, n.y];
  }
  let r = K.r;
  let th = K.th;
  let ox = K.ox != null ? K.ox : -0.17;
  let oy = K.oy || 0;
  if (r === "fit") {
    // O mapa inteiro cabe no retângulo livre; deitado ou em pé, o que der o raio menor.
    const sr = medidas.livre ?? { l: 16, t: 70, r: mob ? W - 16 : W - 24, b: H - 16 };
    const sw = Math.max(140, sr.r - sr.l);
    const sh = Math.max(140, sr.b - sr.t);
    const tv = Math.tan((16 * Math.PI) / 180);
    const tz = (tv * W) / H;
    const fit = (hx: number, hy: number) => Math.max(hx / ((tz * sw) / W), hy / ((tv * sh) / H)) * 1.05;
    const rl = fit(9.3, 4.3);
    const rp = fit(4.9, 8.6);
    const port = rp < rl * 0.9;
    r = port ? rp : rl;
    th = port ? 90 : 0;
    ox = (W / 2 - (sr.l + sw / 2)) / W;
    oy = (H / 2 - (sr.t + sh / 2)) / H;
  } else if (mob) {
    ox = 0;
    oy = i === 0 ? -0.12 : 0.2;
    if (i > 1) r *= 1.35;
    else r *= 1.5;
  } else if (i >= 1) {
    // No computador, o foco fica no meio do espaço entre o conteúdo do bloco e a borda direita livre.
    const esquerda = Math.min((medidas.bordaDoBloco?.[i] || W * 0.5) + 24, W - 300);
    const direita = medidas.direita ?? W - 24;
    ox = (W / 2 - (esquerda + direita) / 2) / W;
  }
  const node = typeof K.f === "string" && K.f !== "center" ? K.f : i === 5 ? "regras" : null;
  return {
    tg,
    r,
    th,
    ph: K.ph,
    ox,
    oy,
    mu: K.m ? (msg.par[K.m] ?? 0) : 0,
    du: K.d ? (dados.par[K.d] ?? 0) : 0,
    node,
  };
}

/** Que caminho acende num turno da conversa (full: todos; ask: sem a ação; act: sem o "qual"…). */
export type TipoDeRota = "full" | "read" | "ask" | "act" | "noact" | "reader";

export function nosDaRota(tipo: TipoDeRota, id: string): readonly IdDoNo[] {
  const todos = MENSAGEM;
  const menos = (a: readonly IdDoNo[]) => todos.filter((x) => !a.includes(x));
  const kind: TipoDeRota = id === "desbloq" ? "noact" : tipo;
  const rotas: Record<TipoDeRota, readonly IdDoNo[]> = {
    full: todos,
    read: todos,
    ask: menos(["acoes"]),
    act: menos(["qual"]),
    noact: menos(["qual", "acoes"]),
    reader: menos(["qual", "acoes"]).concat(["leitor"]),
  };
  return rotas[kind];
}
