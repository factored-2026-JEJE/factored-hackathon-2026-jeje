// O que cada área do app recebe da casca (DEV-032b). A língua e os textos do design vêm do
// useLingua() (app/LinguaDoApp.tsx), e a sessão de teste, do useSessao() (app/sessao.tsx).
export interface PropsDaArea {
  /** Muda a cada efeito da conversa (pré-caso, encaminhamento, bloqueio): a área relê o que mostra. */
  readonly versao: number;
  /** A conversa criou algo: as outras áreas se atualizam. */
  readonly aoMudar: () => void;
  /** O "Try in ES/PT" do design: garante a sessão, vai à aba do cliente e manda a frase à conversa. */
  readonly experimentar: (frase: string) => void;
}
