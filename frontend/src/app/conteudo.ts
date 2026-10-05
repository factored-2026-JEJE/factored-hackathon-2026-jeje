// O conteúdo do app (DEV-032b), o mesmo do design (04-solucao/design-do-site/jeje-app-content.js no
// vault), copiado sem mudança: E(en, es, pt) para os textos da interface nos três idiomas; os atalhos,
// as opções, a pergunta sobre uma transação e o significado dos códigos só existem em espanhol e
// português, como a conversa. O motor simulado do design (replies, quality e personas) fica de fora:
// os dados, as respostas, as regras e o porquê vêm sempre da API (fechamento, regra 7).
// Só leitura para os dois agentes: o que o design não tem fica no textos.ts de cada área.

export type Lingua = "en" | "es" | "pt";
export type IdiomaDaConversa = "es" | "pt";

export interface Traducao {
  readonly __e: 1;
  readonly en: string;
  readonly es: string;
  readonly pt: string;
}

export const E = (en: string, es: string, pt: string): Traducao => ({ __e: 1, en, es, pt });

export const UI = {
  tabs: { cliente: E('Customer', 'Cliente', 'Cliente'), atendente: E('Agent', 'Agente', 'Atendente'), operacao: E('Operations', 'Operación', 'Operação'), guia: E('How to test', 'Cómo probar', 'Como testar') },
  top: { demo: E('demo · synthetic data', 'demo · datos sintéticos', 'demo · dados sintéticos'), leave: E('Leave', 'Salir', 'Sair'), device: { reg: E('registered device', 'dispositivo registrado', 'dispositivo cadastrado'), new: E('new device', 'dispositivo nuevo', 'dispositivo novo') } },
  acc: {
    kicker: E('Test access · not a real login', 'Acceso de prueba · no es un login real', 'Acesso de teste · não é login real'),
    title: E('Talk to the bank about your transactions.', 'Habla con el banco sobre tus transacciones.', 'Fale com o banco sobre as suas transações.'),
    body: E('Ask why a purchase was declined, dispute a charge you don’t recognize, block a card or follow your requests, in Spanish or Portuguese. A policy in code decides; the model only reads. Every answer shows why.',
            'Pregunta por qué rechazaron una compra, impugna un cobro que no reconoces, bloquea una tarjeta o sigue tus solicitudes, en español o portugués. Decide una política en código; el modelo solo lee. Cada respuesta muestra por qué.',
            'Pergunte por que uma compra foi recusada, conteste uma cobrança que não reconhece, bloqueie um cartão ou acompanhe seus pedidos, em espanhol ou português. Quem decide é uma política em código; o modelo só lê. Cada resposta mostra o porquê.'),
    note: E('Demo customers are provisioned on the server. Everything here is synthetic.', 'Los clientes de demostración se crean en el servidor. Todo aquí es sintético.', 'Os clientes de demonstração são criados no servidor. Tudo aqui é sintético.'),
    s1: E('1 · Choose a demo customer', '1 · Elige un cliente de demostración', '1 · Escolha um cliente de demonstração'),
    s2: E('2 · Choose the device', '2 · Elige el dispositivo', '2 · Escolha o dispositivo'),
    stats: { cards: E('cards to block', 'tarjetas', 'cartões'), declines: E('declines', 'rechazos', 'recusas'), recent: E('recent requests', 'solicitudes recientes', 'pedidos recentes'), disputable: E('disputable', 'impugnables', 'contestáveis') },
    devReg: E('Registered device', 'Dispositivo registrado', 'Dispositivo cadastrado'), devRegSub: E('A block is full and shows in the agent console.', 'El bloqueo es completo y aparece en la consola del agente.', 'O bloqueio é completo e aparece no console do atendente.'),
    devNew: E('New device', 'Dispositivo nuevo', 'Dispositivo novo'), devNewSub: E('A block is preventive; an agent confirms or undoes it.', 'El bloqueo es preventivo; un agente lo confirma o lo deshace.', 'O bloqueio é preventivo; um atendente confirma ou desfaz.'),
    enter: E('Enter as', 'Entrar como', 'Entrar como'),
    lang: { es: E('Spanish', 'Español', 'Espanhol'), pt: E('Portuguese', 'Portugués', 'Português') }
  },
  conv: {
    title: E('Conversation', 'Conversación', 'Conversa'), newConv: E('New conversation', 'Nueva conversación', 'Nova conversa'),
    steps: [E('1 · Request', '1 · Pedido', '1 · Pedido'), E('2 · Transaction', '2 · Transacción', '2 · Transação'), E('3 · Confirmation', '3 · Confirmación', '3 · Confirmação')],
    reading: E('reading', 'leyendo', 'lendo'), ph: E('Write as the customer, in Spanish or Portuguese', 'Escribe como cliente, en español o portugués', 'Escreva como cliente, em espanhol ou português'),
    send: E('Send', 'Enviar', 'Enviar'), why: E('Why this answer?', '¿Por qué esta respuesta?', 'Por que esta resposta?'),
    empty: E('Write as the customer or use a shortcut. Every answer comes with its receipt.', 'Escribe como el cliente o usa un atajo. Cada respuesta trae su recibo.', 'Escreva como o cliente ou use um atalho. Cada resposta traz o seu recibo.'),
    tryThis: E('Try this customer’s example', 'Prueba el ejemplo de este cliente', 'Experimente o exemplo deste cliente'),
    human: E('Handed to a person', 'Pasado a una persona', 'Passado para uma pessoa'), you: E('You', 'Tú', 'Você')
  },
  side: {
    txns: E('My transactions', 'Mis transacciones', 'Minhas transações'), ask: E('Ask about this one', 'Preguntar por esta', 'Perguntar sobre esta'),
    askNote: E('Sends the row’s clues to the chat, never its identifier.', 'Envía las pistas de la fila al chat, nunca su identificador.', 'Manda as pistas da linha para a conversa, nunca o identificador.'),
    st: { aprovada: E('approved', 'aprobada', 'aprovada'), recusada: E('declined', 'rechazada', 'recusada'), pendente: E('pending', 'pendiente', 'pendente'), estornada: E('reversed', 'revertida', 'estornada') },
    reqs: E('My requests', 'Mis solicitudes', 'Meus pedidos'), reqNone: E('No review requests yet.', 'Aún no hay solicitudes de revisión.', 'Ainda não há pedidos de revisão.'),
    inReview: E('in review', 'en revisión', 'em revisão'), cards: E('Cards', 'Tarjetas', 'Cartões'), active: E('active', 'activa', 'ativo'), closed: E('closed', 'cerrada', 'encerrado'),
    blockedFull: E('blocked · full', 'bloqueada · completo', 'bloqueado · completo'), blockedPrev: E('blocked · preventive', 'bloqueada · preventivo', 'bloqueado · preventivo'),
    undoNote: E('Can be undone in the chat within 7 days.', 'Se puede deshacer por el chat en hasta 7 días.', 'Pode ser desfeito pela conversa em até 7 dias.'),
    prevNote: E('An agent confirms or undoes this block.', 'Un agente confirma o deshace este bloqueo.', 'Um atendente confirma ou desfaz este bloqueio.'),
    panels: [E('Chat', 'Chat', 'Conversa'), E('Transactions', 'Transacciones', 'Transações'), E('Requests · cards', 'Solicitudes · tarjetas', 'Pedidos · cartões')]
  },
  ag: {
    kicker: E('Agent console · #atendente', 'Consola del agente · #atendente', 'Console do atendente · #atendente'),
    title: E('The case arrives ready.', 'El caso llega listo.', 'O caso chega pronto.'),
    sub: E('Each case brings the request, the verified facts, the actions tried and what is pending. Not the transcript: only the new lines, up to 280 characters.', 'Cada caso trae el pedido, los hechos verificados, las acciones intentadas y lo pendiente. No la transcripción: solo las frases nuevas, hasta 280 caracteres.', 'Cada caso traz o pedido, os fatos verificados, as ações tentadas e as pendências. Não a transcrição: só as falas novas, em até 280 caracteres.'),
    queue: E('Queue', 'Fila', 'Fila'), empty: E('The queue is empty.', 'La fila está vacía.', 'A fila está vazia.'), emptyTry: E('In Customer, try one of these:', 'En Cliente, prueba uno de estos:', 'Em Cliente, experimente um destes:'),
    req: E('Request', 'Pedido', 'Pedido'), facts: E('Verified facts', 'Hechos verificados', 'Fatos verificados'), actions: E('Actions tried', 'Acciones intentadas', 'Ações tentadas'), pending: E('Pending', 'Pendiente', 'Pendências'),
    lines: E('New lines · ≤ 280 characters', 'Frases nuevas · ≤ 280 caracteres', 'Falas novas · ≤ 280 caracteres'),
    take: E('Take case', 'Asumir', 'Assumir'), taken: E('Taken by you', 'Asumido por ti', 'Assumido por você'),
    blocks: E('Card blocks', 'Bloqueos de tarjeta', 'Bloqueios de cartão'), blocksNone: E('No blocked cards.', 'Ninguna tarjeta bloqueada.', 'Nenhum cartão bloqueado.'),
    unblock: E('Unblock', 'Desbloquear', 'Desbloquear'), since: E('since', 'desde', 'desde')
  },
  ops: {
    kicker: E('Operations · #operacao', 'Operación · #operacao', 'Operação · #operacao'), title: E('Is it running? Look here.', '¿Está funcionando? Mira aquí.', 'Está funcionando? Veja aqui.'),
    ready: E('Readiness', 'Disponibilidad', 'Prontidão'), db: E('database', 'base', 'banco'), ok: E('ready', 'lista', 'pronto'),
    version: E('data version', 'versión de datos', 'versão dos dados'), loaded: E('loaded at', 'cargada a las', 'carregada às'), rejected: E('rejected version', 'versión rechazada', 'versão recusada'), none: E('none', 'ninguna', 'nenhuma'),
    metrics: E('Metrics · recomputed from events', 'Métricas · recalculadas de los eventos', 'Métricas · recalculadas dos eventos'),
    m: { turns: E('turns', 'turnos', 'turnos'), errors: E('errors', 'errores', 'erros'), convs: E('conversations', 'conversaciones', 'conversas'), handoffs: E('handoffs', 'derivaciones', 'encaminhamentos'), precases: E('pre-cases', 'pre-casos', 'pré-casos'), lat: E('latency p50 / p95', 'latencia p50 / p95', 'latência p50 / p95'), model: E('model calls', 'llamadas al modelo', 'chamadas ao modelo') },
    fresh: E('Fresh instance: every counter starts at zero. Send a message in Customer and watch them move.', 'Instancia nueva: todos los contadores empiezan en cero. Manda un mensaje en Cliente y míralos moverse.', 'Instância nova: todo contador começa em zero. Mande uma mensagem em Cliente e veja os números mudarem.'),
    rules: E('Rules used', 'Reglas usadas', 'Regras usadas'), rulesNone: E('No turns yet.', 'Aún no hay turnos.', 'Ainda não há turnos.'),
    events: E('Last events', 'Últimos eventos', 'Últimos eventos'),
    quality: E('Data quality · synthetic fixture', 'Calidad de datos · fixture sintética', 'Qualidade dos dados · fixture sintética'),
    qcols: [E('table', 'tabla', 'tabela'), E('records', 'registros', 'registros'), E('curated', 'curados', 'curados'), E('quarantine', 'cuarentena', 'quarentena'), E('copies', 'copias', 'cópias'), E('voided refs', 'refs. anuladas', 'refs. anuladas')],
    check: E('raw = curated + quarantine + copies', 'raw = curados + cuarentena + copias', 'raw = curados + quarentena + cópias')
  },
  guide: {
    kicker: E('How to test · #how-to-test', 'Cómo probar · #how-to-test', 'Como testar · #how-to-test'),
    title: E('Three paths, in Spanish and Portuguese.', 'Tres caminos, en español y portugués.', 'Três caminhos, em espanhol e português.'),
    sub: E('Each takes under a minute. Open “Why this answer?” under any reply.', 'Cada uno toma menos de un minuto. Abre «¿Por qué esta respuesta?» debajo de cualquier respuesta.', 'Cada um leva menos de um minuto. Abra “Por que esta resposta?” sob qualquer resposta.'),
    tryEs: E('Try in ES', 'Probar en ES', 'Testar em ES'), tryPt: E('Try in PT', 'Probar en PT', 'Testar em PT'), expect: E('What happens', 'Qué pasa', 'O que acontece'),
    check: E('What to check', 'Qué verificar', 'O que conferir'),
    checks: [E('“Why this answer?” shows the rule, the action, the effect and the receipt of every fact.', '«¿Por qué esta respuesta?» muestra la regla, la acción, el efecto y el recibo de cada hecho.', '“Por que esta resposta?” mostra a regra, a ação, o efeito e o recibo de cada fato.'),
             E('Agent shows the case with its summary, without the transcript.', 'Agente muestra el caso con su resumen, sin la transcripción.', 'Atendente mostra o caso com o resumo, sem a transcrição.'),
             E('Operations counters move with every turn.', 'Los contadores de Operación se mueven con cada turno.', 'Os contadores da Operação mudam a cada turno.')],
    paths: [
      { n: E('Normal: dispute a charge', 'Normal: impugnar un cobro', 'Normal: contestar uma cobrança'), es: 'No reconozco el cobro de 45,90 del 10/03', pt: 'Não reconheço a cobrança de 45,90 do dia 10/03',
        x: E('Finds the transaction, proposes a review request and only records it after “Sí, confirmo”. Returns a protocol.', 'Encuentra la transacción, propone la solicitud y solo la registra tras «Sí, confirmo». Devuelve un protocolo.', 'Acha a transação, propõe o pedido e só registra depois de “Sim, confirmo”. Devolve um protocolo.') },
      { n: E('Ambiguous: a declined purchase', 'Ambiguo: una compra rechazada', 'Ambíguo: uma compra recusada'), es: '¿Por qué rechazaron mi compra?', pt: 'Por que recusaram minha compra?',
        x: E('With more than one decline, it lists them and asks which. Then it explains the ISO 8583 code.', 'Con más de un rechazo, los lista y pregunta cuál. Luego explica el código ISO 8583.', 'Com mais de uma recusa, lista e pergunta qual. Depois explica o código ISO 8583.') },
      { n: E('Human: a stolen card', 'Humano: tarjeta robada', 'Humano: cartão roubado'), es: 'Me robaron la tarjeta', pt: 'Roubaram meu cartão',
        x: E('Goes to an agent at once and the card is blocked (simulated). The case shows in Agent with its summary.', 'Va a un agente de inmediato y la tarjeta se bloquea (simulación). El caso aparece en Agente con su resumen.', 'Vai para um atendente na hora e o cartão é bloqueado (simulação). O caso aparece em Atendente com o resumo.') }
    ]
  },
  rc: { rid: 'X-Request-ID', lang: E('language', 'idioma', 'idioma'), reader: E('read by', 'quién leyó', 'quem leu'), intent: E('intent', 'intención', 'intenção'), txn: E('transaction', 'transacción', 'transação'), rule: E('rule', 'regla', 'regra'), meaning: E('meaning', 'significado', 'significado'), action: E('action', 'acción', 'ação'), effect: E('effect', 'efecto', 'efeito'), protocol: E('protocol', 'protocolo', 'protocolo'), file: E('file', 'archivo', 'arquivo'), line: E('line', 'línea', 'linha'), version: E('data version', 'versión de datos', 'versão dos dados'),
        cordial: E('Greeting or thanks: a polite reply, same step.', 'Saludo o agradecimiento: respuesta cordial, misma etapa.', 'Cumprimento ou agradecimento: resposta cordial, mesma etapa.') },
  rd: { rules: E('rules', 'reglas', 'regras'), below: E('reader below threshold', 'lector bajo el umbral', 'leitor abaixo do limite') },
  tr: { exact: E('exact filter', 'filtro exacto', 'filtro exato'), rank: E('ranking · conformal set {1}', 'ranking · conjunto conformal {1}', 'ranking · conjunto conformal {1}'), cands: E('candidates · asks which', 'posibles · pregunta cuál', 'possíveis · pergunta qual'), chosen: E('chosen by the customer', 'elegida por el cliente', 'escolhida pelo cliente'), last: E('“the last one”', '«la última»', '“a última”'), dup: E('second of 2 identical', 'segunda de 2 iguales', 'segunda de 2 iguais'), proposal: E('the proposed one', 'la de la propuesta', 'a da proposta') },
  int: { consult: E('query', 'consultar', 'consultar'), dispute: E('dispute', 'impugnar', 'contestar'), fraud: E('fraud', 'fraude', 'fraude'), block: E('block card', 'bloquear', 'bloquear'), unblock: E('unblock card', 'desbloquear', 'desbloquear'), status: E('request status', 'seguimiento', 'acompanhar'), agent: E('agent', 'agente', 'atendente'), scope: E('out of scope', 'fuera de alcance', 'fora de escopo'), yes: E('yes', 'sí', 'sim'), no: E('no', 'no', 'não'), greet: E('greeting', 'saludo', 'cumprimento'), scam: E('scam question', 'pregunta sobre estafa', 'pergunta sobre golpe'), stay: E('stay here', 'seguir aquí', 'continuar aqui'), unknown: '—' },
  act: { read: E('answer from the record', 'responder con el registro', 'responder com o registro'), clarify: E('ask which', 'preguntar cuál', 'perguntar qual'), propose: E('propose pre-case', 'proponer pre-caso', 'propor pré-caso'), record: E('record pre-case', 'registrar pre-caso', 'registrar pré-caso'), none: E('none', 'ninguna', 'nenhuma'), block: E('full block (simulated)', 'bloqueo completo (simulado)', 'bloqueio completo (simulado)'), blockPrev: E('preventive block (simulated)', 'bloqueo preventivo (simulado)', 'bloqueio preventivo (simulado)'), askYes: E('ask for an explicit yes', 'pedir un sí explícito', 'pedir um sim explícito'), unblock: E('unblock (simulated)', 'desbloquear (simulado)', 'desbloquear (simulado)'), handoff: E('hand to an agent', 'pasar a un agente', 'passar para um atendente'), fraud: E('agent + block (simulated)', 'agente + bloqueo (simulado)', 'atendente + bloqueio (simulado)'), offer: E('offer an agent', 'ofrecer un agente', 'oferecer um atendente'), again: E('ask again', 'pedir de nuevo', 'pedir de novo'), returnP: E('return the protocol', 'devolver el protocolo', 'devolver o protocolo'), reply: E('polite reply, same step', 'respuesta cordial, misma etapa', 'resposta cordial, mesma etapa') },
  eff: { none: E('none · read only', 'ninguno · solo lectura', 'nenhum · só leitura'), wait: E('proposal · waiting for yes', 'propuesta · esperando el sí', 'proposta · aguardando o sim'), recorded: E('written · re-read from the database', 'grabado · releído en la base', 'gravado · relido no banco'), exists: E('no duplicate', 'sin duplicar', 'sem duplicar'), blocked: E('card blocked · re-read', 'tarjeta bloqueada · releída', 'cartão bloqueado · relido'), queued: E('case queued with summary', 'caso en la fila con resumen', 'caso na fila com resumo'), unblocked: E('card active · re-read', 'tarjeta activa · releída', 'cartão ativo · relido'), nothing: E('nothing recorded', 'nada registrado', 'nada registrado') },
  fk: { cust: E('customer', 'cliente', 'cliente'), device: E('device', 'dispositivo', 'dispositivo'), card: E('card', 'tarjeta', 'cartão'), txn: E('transaction', 'transacción', 'transação'), recent: E('recent pre-cases', 'pre-casos recientes', 'pré-casos recentes') },
  cases: {
    fraud: { req: E('Reports fraud, theft or loss of the card', 'Reporta fraude, robo o pérdida de la tarjeta', 'Relata fraude, roubo ou perda do cartão'), pend: E('Confirm the block and next steps with the customer', 'Confirmar el bloqueo y los próximos pasos', 'Confirmar o bloqueio e os próximos passos') },
    agent: { req: E('Asked for an agent', 'Pidió un agente', 'Pediu um atendente'), pend: E('Understand what the customer needs', 'Entender qué necesita el cliente', 'Entender do que o cliente precisa') },
    scope: { req: E('Out-of-scope request', 'Pedido fuera de alcance', 'Pedido fora de escopo'), pend: E('Route to the right team', 'Derivar al equipo correcto', 'Encaminhar para a equipe certa') },
    tooMany: { req: E('Dispute with several recent pre-cases', 'Impugnación con varios pre-casos recientes', 'Contestação com vários pré-casos recentes'), pend: E('Review the dispute by hand', 'Revisar la impugnación a mano', 'Revisar a contestação manualmente') },
    unblock: { req: E('Unblock outside the window', 'Desbloqueo fuera de plazo', 'Desbloqueio fora do prazo'), pend: E('Verify and decide on the unblock', 'Verificar y decidir el desbloqueo', 'Verificar e decidir o desbloqueio') },
    prev: { req: E('Preventive block from a new device', 'Bloqueo preventivo desde un dispositivo nuevo', 'Bloqueio preventivo por dispositivo novo'), pend: E('Confirm or undo the block', 'Confirmar o deshacer el bloqueo', 'Confirmar ou desfazer o bloqueio') },
    scam: { req: E('Asks how to avoid a scam · no fraud reported', 'Pregunta cómo evitar una estafa · sin fraude', 'Pergunta como evitar golpe · sem fraude'), pend: E('Explain how to stay safe; no block needed', 'Explicar cómo protegerse; sin bloqueo', 'Explicar como se proteger; sem bloqueio') },
    help: { req: E('Clarifications failed', 'Aclaraciones sin éxito', 'Esclarecimentos sem sucesso'), pend: E('Understand what the customer needs', 'Entender qué necesita el cliente', 'Entender do que o cliente precisa') }
  }
};

/** O significado genérico dos códigos de recusa, na língua da conversa. */
export const ISO: Readonly<Record<string, Readonly<Record<IdiomaDaConversa, string>>>> = { '51': { es: 'fondos insuficientes', pt: 'saldo insuficiente' }, '05': { es: 'no aprobada por el emisor', pt: 'não autorizada pelo emissor' }, '54': { es: 'tarjeta vencida', pt: 'cartão vencido' } };

/** Os rótulos das respostas rápidas (o texto enviado é o mesmo do rótulo, exceto no atendente). */
export const OPCOES: Readonly<Record<IdiomaDaConversa, { readonly yes: string; readonly no: string; readonly agent: string; readonly stay: string }>> = { es: { yes: 'Sí, confirmo', no: 'No', agent: 'Hablar con un agente', stay: 'Seguir aquí' }, pt: { yes: 'Sim, confirmo', no: 'Não', agent: 'Falar com um atendente', stay: 'Continuar aqui' } };

/** Os atalhos: [rótulo, frase enviada]. */
export const ATALHOS: Readonly<Record<IdiomaDaConversa, readonly (readonly [string, string])[]>> = {
  es: [['Mi última compra', '¿Qué pasó con mi última compra?'], ['No reconozco un cobro', 'No reconozco un cobro'], ['¿Por qué rechazaron?', '¿Por qué rechazaron mi compra?'], ['Mi solicitud', '¿Cómo va mi solicitud?'], ['Bloquear tarjeta', 'Quiero bloquear mi tarjeta'], ['Hablar con un agente', 'Quiero hablar con un agente']],
  pt: [['Minha última compra', 'O que houve com minha última compra?'], ['Não reconheço', 'Não reconheço uma cobrança'], ['Por que recusaram?', 'Por que recusaram minha compra?'], ['Meu pedido', 'Como está meu pedido?'], ['Bloquear cartão', 'Quero bloquear meu cartão'], ['Falar com atendente', 'Quero falar com um atendente']]
};

/** "Ask about this one": as pistas da linha (valor, dd/mm e comércio), como o cliente escreveria. */
export const PERGUNTA_SOBRE: Readonly<Record<IdiomaDaConversa, (v: { readonly a: string; readonly d: string; readonly m: string }) => string>> = {
  es: (v) => '¿Qué pasó con el cobro de USD ' + v.a + ' del ' + v.d + ' en ' + v.m + '?',
  pt: (v) => 'O que houve com a cobrança de USD ' + v.a + ' do dia ' + v.d + ' em ' + v.m + '?',
};

/** O conteúdo num idioma: cada E vira o texto daquele idioma. */
export type Resolvido<X> = X extends Traducao
  ? string
  : X extends readonly unknown[]
    ? { -readonly [K in keyof X]: Resolvido<X[K]> }
    : X extends object
      ? { -readonly [K in keyof X]: Resolvido<X[K]> }
      : X;

export type Textos = Resolvido<typeof UI>;

const cache = new Map<Lingua, Textos>();

/** Os textos da interface numa língua (o inglês quando falta a tradução, como o ui(l) do design). */
export function textos(lingua: Lingua): Textos {
  const pronto = cache.get(lingua);
  if (pronto) return pronto;
  const r = (o: unknown): unknown => {
    if (o == null || typeof o !== "object") return o;
    if ("__e" in o) {
      const t = o as Traducao;
      return t[lingua] != null ? t[lingua] : t.en;
    }
    if (Array.isArray(o)) return o.map(r);
    const saida: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(o)) saida[k] = r(v);
    return saida;
  };
  // A recursão acima é a definição de Resolvido; o TypeScript não acompanha a recursão sozinho.
  const resolvido = r(UI) as Textos;
  cache.set(lingua, resolvido);
  return resolvido;
}
