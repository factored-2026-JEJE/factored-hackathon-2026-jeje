// Textos da aba do cliente que o design não tem (DEV-032b), no tom e nas três línguas dele: os estados
// que o produto tem de verdade (carregando, sem resposta da API, conversa encerrada pela recarga, sessão
// expirada, protocolo recebido). Os do design ficam em app/conteudo.ts, só para leitura.
import { E } from "../../app/conteudo";

export const CLIENTE = {
  expirou: E("Your session expired. Enter again.", "Tu sesión expiró. Entra de nuevo.", "Sua sessão expirou. Entre de novo."),
  carregandoPersonas: E("Loading demo customers…", "Cargando clientes de demostración…", "Carregando clientes de demonstração…"),
  semPersonas: E("No demo customers available.", "No hay clientes de demostración.", "Não há clientes de demonstração."),
  carregandoConversa: E("Loading the conversation…", "Cargando la conversación…", "Carregando a conversa…"),
  semTransacoes: E("No transactions found.", "No se encontraron transacciones.", "Nenhuma transação encontrada."),
  carregandoTransacoes: E("Loading transactions…", "Cargando transacciones…", "Carregando transações…"),
  transacoesIndisponiveis: E("Transactions unavailable", "Transacciones no disponibles", "Transações indisponíveis"),
  semCartoes: E("No cards found.", "No se encontraron tarjetas.", "Nenhum cartão encontrado."),
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
