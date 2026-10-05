// Textos da aba do cliente que o design não tem (DEV-032b), no tom e nas três línguas dele: os estados
// que o produto tem de verdade (carregando, sem resposta da API, conversa encerrada pela recarga, sessão
// expirada, protocolo recebido). Os do design ficam em app/conteudo.ts, só para leitura.
import { E } from "../../app/conteudo";

export const CLIENTE = {
  // ACH-167: o produto do cartão vem da base em espanhol; na tela, na língua da interface.
  credito: E("Credit card", "Tarjeta de crédito", "Cartão de crédito"),
  debito: E("Debit card", "Tarjeta de débito", "Cartão de débito"),
  // ACH-167: quem leu e a regra do "não entendi", na língua da interface (a API os manda em português).
  semPalavra: E("no known word", "sin palabra conocida", "sem palavra conhecida"),
  ajuda: E("HELP", "AYUDA", "AJUDA"),
  expirou: E("Your session expired. Enter again.", "Tu sesión expiró. Entra de nuevo.", "Sua sessão expirou. Entre de novo."),
  carregandoPersonas: E("Loading demo customers…", "Cargando clientes de demostración…", "Carregando clientes de demonstração…"),
  semPersonas: E("No demo customers available.", "No hay clientes de demostración.", "Não há clientes de demonstração."),
  carregandoConversa: E("Loading the conversation…", "Cargando la conversación…", "Carregando a conversa…"),
  semTransacoes: E("No transactions found.", "No se encontraron transacciones.", "Nenhuma transação encontrada."),
  carregandoTransacoes: E("Loading transactions…", "Cargando transacciones…", "Carregando transações…"),
  transacoesIndisponiveis: E("Transactions unavailable", "Transacciones no disponibles", "Transações indisponíveis"),
  semCartoes: E("No cards found.", "No se encontraron tarjetas.", "Nenhum cartão encontrado."),
  cartoesIndisponiveis: E("Cards unavailable right now.", "Tarjetas no disponibles por ahora.", "Cartões indisponíveis agora."),
  naoAbriu: E("Could not open the conversation. Try again.", "No se pudo abrir la conversación. Inténtalo de nuevo.", "Não foi possível abrir a conversa. Tente de novo."),
  semResposta: E(
    "No answer from the server. Sending again is safe: the chat does not repeat effects.",
    "Sin respuesta del servidor. Reenviar es seguro: la conversación no repite efectos.",
    "Sem resposta do servidor. Reenviar é seguro: a conversa não repete efeitos.",
  ),
  reenviar: E("Send again", "Reenviar", "Reenviar"),
  encerrada: E(
    "Conversation closed: the data was reloaded. Start a new conversation.",
    "Conversación cerrada: los datos se recargaron. Abre una nueva conversación.",
    "Conversa encerrada: os dados foram atualizados. Abra uma nova conversa.",
  ),
  recebido: E("pre-case received", "pre-caso recibido", "pré-caso recebido"),
  opcoes: E("Options", "Opciones", "Opções"),
  atalhos: E("Shortcuts", "Atajos", "Atalhos"),
} as const;

// Os atalhos do design mandam a frase deles, menos a que as regras não entendem (conferido contra a API
// da fixture em 03/10): o rótulo segue o do design, e vai a frase que o produto entende. Em português,
// "pedido" sozinho é ambíguo para as regras (fazer um pedido); o registrado é o "pedido de revisão".
export const FRASE_DO_ATALHO: Readonly<Record<string, string>> = {
  "Como está meu pedido?": "Como está meu pedido de revisão?",
};

// A avaliação do time (AvaliarConversa, só no modo de demonstração), que o design não tem.
export const AVALIACAO = {
  titulo: E("Rate this conversation", "Evalúa esta conversación", "Avaliar esta conversa"),
  quem: E("Who is testing", "Quién está probando", "Quem está testando"),
  escolha: E("Choose", "Elige", "Escolha"),
  nota: E("Score", "Nota", "Nota"),
  resolveu: E("Did the assistant solve it?", "¿El asistente lo resolvió?", "O assistente resolveu?"),
  sim: E("Solved", "Resuelto", "Resolveu"),
  parcial: E("Partly", "En parte", "Em parte"),
  nao: E("Not solved", "No resuelto", "Não resolveu"),
  comentario: E("What went wrong, or how it should have gone", "Qué salió mal o cómo debería haber sido", "O que deu errado ou como deveria ter sido"),
  registrar: E("Submit review", "Registrar evaluación", "Registrar avaliação"),
  enviada: E("Review sent, thank you.", "Evaluación enviada, gracias.", "Review enviada, obrigado."),
  issue: E("See the issue", "Ver el issue", "Ver a Issue"),
  falhou: E("Could not send the review. Try again.", "No se pudo enviar la evaluación. Inténtalo de nuevo.", "Não foi possível enviar a review. Tente de novo."),
} as const;
