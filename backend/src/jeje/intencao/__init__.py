"""Portão de intenção de Enzo (R04): TF-IDF que classifica a mensagem num dos fluxos do atendimento.

Incorporado em 01/10 (PRD-009, item 1: o trabalho de Enzo nunca é descartado) a partir da tag
`arquivo/intencao-classificador`, como componente aprendido de comparação ao lado do leitor e5. A
conversa continua lendo pelas regras e pelo leitor; o portão responde nas rotas `/intencao` e entra
na comparação do `make avaliar-leitor`.
"""
