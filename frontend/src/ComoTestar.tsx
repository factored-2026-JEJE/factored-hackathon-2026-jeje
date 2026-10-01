// "How to test" (PRD-009): o roteiro dos jurados, em inglês (decisão de Jader), com as frases que
// o cliente digitaria em espanhol e em português. Texto fixo: as respostas vêm sempre da API.
export function ComoTestar() {
  return (
    <section aria-label="How to test" className="cartao guia">
      <h2>How to test this demo</h2>
      <p>
        JEJE answers card-transaction questions in Spanish and Portuguese, registers review requests (pre-cases) for
        charges the customer does not recognize, blocks cards and hands cases to a human attendant. Policy decisions
        are made by deterministic rules, never by a language model; card blocks and review requests are simulated, and
        no money moves.
      </p>
      <ol className="passos">
        <li>
          <h3>Pick a customer</h3>
          <p>
            In the <a href="#cliente">Cliente</a> tab, choose the device (<em>novo</em>: new device, so a card block is
            preventive and goes to an attendant; <em>cadastrado</em>: registered device, a full block that the attendant
            sees in the console), click <strong>Entrar como …</strong> and open the conversation in Spanish or
            Portuguese.
          </p>
        </li>
        <li>
          <h3>Normal path: contest a charge</h3>
          <p>
            Click <strong>Perguntar sobre esta</strong> on a row of <em>Minhas transações</em>, or type the amount and
            date of one of the customer&apos;s own purchases: the customer list shows a ready sentence for each customer,
            in Spanish and Portuguese, after <em>para contestar</em>. The assistant finds the transaction and proposes a
            review request, registered only after <q>Sí, confirmo</q> / <q>Sim, confirmo</q>.
          </p>
        </li>
        <li>
          <h3>Ambiguous path</h3>
          <p>
            <q>¿Por qué rechazaron mi compra?</q> / <q>Por que recusaram minha compra?</q>: with more than one declined
            transaction, it lists them and asks which one, then explains the decline code.
          </p>
        </li>
        <li>
          <h3>Human path</h3>
          <p>
            <q>Me robaron la tarjeta</q> / <q>Roubaram meu cartão</q>: the case goes to the attendant at once, with the
            card blocked. With several active cards, it asks which one to block, with the case already in the queue.
            Then open the <a href="#atendente">Atendente</a> tab: the case shows the request, the verified facts, the
            actions taken and what is pending.
          </p>
        </li>
        <li>
          <h3>Card block and undo</h3>
          <p>
            <q>Quiero bloquear mi tarjeta</q> / <q>Quero bloquear meu cartão</q> blocks the card; within 7 days,{" "}
            <q>Quiero desbloquear mi tarjeta</q> undoes it after an explicit <q>sí</q>. After that, only the attendant
            can undo it, in the console.
          </p>
        </li>
        <li>
          <h3>See why and how it runs</h3>
          <p>
            Every reply has <strong>Por que esta resposta?</strong>: the policy rule, the action, its effect, the data
            sources and who read the message (the rules or the e5 reader). The <a href="#operacao">Operação</a> tab shows
            the metrics computed from the turn events, the system and data status, data quality and the analysis
            behind the problem.
          </p>
        </li>
      </ol>
      <h3>Limits</h3>
      <ul>
        <li>The policy limits are simulated (set in the configuration), and so are card blocks: there is no card system.</li>
        <li>The customer list is a demo login; a real bank would authenticate the customer.</li>
        <li>Only Spanish and Portuguese; other languages get the same answers with lower accuracy.</li>
      </ul>
    </section>
  );
}
