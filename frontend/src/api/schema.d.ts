export interface paths {
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Liveness
         * @description Processo vivo; não consulta dependências.
         */
        get: operations["liveness_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readiness */
        get: operations["readiness_health_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/dados/qualidade": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Relatorio De Qualidade
         * @description Relatório da última carga, na ordem de dependência dos contratos.
         */
        get: operations["relatorio_de_qualidade_dados_qualidade_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/dados/eda": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Indicadores Da Eda
         * @description Indicadores da EDA calculados na hora sobre a carga atual, cada um com sua consulta.
         */
        get: operations["indicadores_da_eda_dados_eda_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/personas": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Listar Personas
         * @description Personas de demonstração (acesso de teste explícito, só com MODO_DEMO ligado).
         */
        get: operations["listar_personas_personas_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessoes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Abrir Sessao */
        post: operations["abrir_sessao_sessoes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/sessao": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Sessao Atual
         * @description Quem está na sessão (o nome vem da persona provisionada).
         */
        get: operations["sessao_atual_sessao_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/minhas/transacoes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Minhas Transacoes */
        get: operations["minhas_transacoes_minhas_transacoes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/minhas/transacoes/{transaction_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Minha Transacao */
        get: operations["minha_transacao_minhas_transacoes__transaction_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/minhas/transacoes/{transaction_id}/situacao": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Situacao
         * @description Fatos da transação e a decisão da política para uma consulta sobre ela (POL-CON-*).
         */
        get: operations["situacao_minhas_transacoes__transaction_id__situacao_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/minhas/transacoes/{transaction_id}/contestacao": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Avaliar Contestacao
         * @description Avalia, sem criar nada, se uma contestação desta transação pode virar pré-caso.
         */
        get: operations["avaliar_contestacao_minhas_transacoes__transaction_id__contestacao_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/minhas/transacoes/{transaction_id}/contestacao/proposta": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Propor
         * @description Avalia a contestação e, se a política permitir, cria uma proposta a confirmar.
         */
        post: operations["propor_minhas_transacoes__transaction_id__contestacao_proposta_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/minhas/propostas/{proposta_id}/confirmacao": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Confirmar
         * @description Confirma a proposta: grava o pré-caso sem duplicar e só responde depois de relê-lo.
         */
        post: operations["confirmar_minhas_propostas__proposta_id__confirmacao_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/minhas/pre-casos": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Meus Pre Casos
         * @description Acompanhamento: pré-casos do cliente da sessão, mais recentes primeiro.
         */
        get: operations["meus_pre_casos_minhas_pre_casos_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AvaliacaoDeContestacao */
        AvaliacaoDeContestacao: {
            decisao: components["schemas"]["DecisaoDaPolitica"];
            proposta: components["schemas"]["Proposta"] | null;
        };
        /** DatasetInfo */
        DatasetInfo: {
            /** Version */
            version: string;
            /** Source */
            source: string;
            /**
             * Loaded At
             * Format: date-time
             */
            loaded_at: string;
        };
        /** DecisaoDaPolitica */
        DecisaoDaPolitica: {
            /** Regra */
            regra: string;
            /** Acao */
            acao: string;
            /** Detalhe */
            detalhe: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** Linha */
        Linha: {
            /** Grupo */
            grupo: string;
            /** Contagem */
            contagem: number;
            /** Base */
            base: number;
            /** Proporcao */
            proporcao: number | null;
            /** Soma */
            soma: number | null;
            /** Proporcao Soma */
            proporcao_soma: number | null;
        };
        /** Liveness */
        Liveness: {
            /**
             * Status
             * @constant
             */
            status: "ok";
            /** Version */
            version: string;
        };
        /** PedidoDeSessao */
        PedidoDeSessao: {
            /** Customer Id */
            customer_id: string;
        };
        /** Persona */
        Persona: {
            /** Customer Id */
            customer_id: string;
            /** Nome */
            nome: string;
        };
        /** PreCaso */
        PreCaso: {
            /** Protocolo */
            protocolo: string;
            /** Transaction Id */
            transaction_id: string;
            /** Estado */
            estado: string;
            /**
             * Criado Em
             * Format: date-time
             */
            criado_em: string;
        };
        /** Proposta */
        Proposta: {
            /** Id */
            id: string;
            /** Transaction Id */
            transaction_id: string;
            /**
             * Expira Em
             * Format: date-time
             */
            expira_em: string;
        };
        /** QualidadeTabela */
        QualidadeTabela: {
            /** Tabela */
            tabela: string;
            /** Raw */
            raw: number;
            /** Curado */
            curado: number;
            /** Quarentena */
            quarentena: number;
            /** Copias Descartadas */
            copias_descartadas: number;
            /** Motivos */
            motivos: {
                [key: string]: number;
            };
            /** Anulacoes */
            anulacoes: {
                [key: string]: number;
            };
            /** Normalizacoes */
            normalizacoes: {
                [key: string]: number;
            };
        };
        /** Readiness */
        Readiness: {
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "unavailable";
            /**
             * Database
             * @enum {string}
             */
            database: "ok" | "unreachable" | "not_migrated";
            dataset: components["schemas"]["DatasetInfo"] | null;
        };
        /** Resultado */
        Resultado: {
            /** Id */
            id: string;
            /** Pergunta */
            pergunta: string;
            /**
             * Tipo
             * @enum {string}
             */
            tipo: "distribuicao" | "taxa";
            /** Consulta */
            consulta: string;
            /** Unidade Soma */
            unidade_soma: string | null;
            /** Linhas */
            linhas: components["schemas"]["Linha"][];
        };
        /** SessaoAberta */
        SessaoAberta: {
            /** Token */
            token: string;
            /**
             * Expira Em
             * Format: date-time
             */
            expira_em: string;
            cliente: components["schemas"]["Persona"];
        };
        /** Situacao */
        Situacao: {
            transacao: components["schemas"]["Transacao"];
            decisao: components["schemas"]["DecisaoDaPolitica"];
        };
        /** Transacao */
        Transacao: {
            /** Transaction Id */
            transaction_id: string;
            /**
             * Transaction Date
             * Format: date-time
             */
            transaction_date: string;
            /** Amount */
            amount: string;
            /** Currency */
            currency: string;
            /** Transaction Status */
            transaction_status: string;
            /** Response Code */
            response_code: string | null;
            /** Transaction Type */
            transaction_type: string | null;
            /** Merchant Name */
            merchant_name: string | null;
            /** Channel */
            channel: string | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    liveness_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Liveness"];
                };
            };
        };
    };
    readiness_health_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Readiness"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Readiness"];
                };
            };
        };
    };
    relatorio_de_qualidade_dados_qualidade_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["QualidadeTabela"][];
                };
            };
        };
    };
    indicadores_da_eda_dados_eda_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Resultado"][];
                };
            };
        };
    };
    listar_personas_personas_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Persona"][];
                };
            };
            /** @description Modo demo desligado ou persona não provisionada */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    abrir_sessao_sessoes_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PedidoDeSessao"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessaoAberta"];
                };
            };
            /** @description Corpo ilegível (não é JSON UTF-8) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Modo demo desligado ou persona não provisionada */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    sessao_atual_sessao_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Persona"];
                };
            };
            /** @description Sessão ausente, inválida ou expirada */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    minhas_transacoes_minhas_transacoes_get: {
        parameters: {
            query?: {
                limite?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Transacao"][];
                };
            };
            /** @description Sessão ausente, inválida ou expirada */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    minha_transacao_minhas_transacoes__transaction_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transaction_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Transacao"];
                };
            };
            /** @description Sessão ausente, inválida ou expirada */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Transação não encontrada */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    situacao_minhas_transacoes__transaction_id__situacao_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transaction_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Situacao"];
                };
            };
            /** @description Sessão ausente, inválida ou expirada */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Transação não encontrada */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    avaliar_contestacao_minhas_transacoes__transaction_id__contestacao_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transaction_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DecisaoDaPolitica"];
                };
            };
            /** @description Sessão ausente, inválida ou expirada */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Transação não encontrada */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    propor_minhas_transacoes__transaction_id__contestacao_proposta_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transaction_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AvaliacaoDeContestacao"];
                };
            };
            /** @description Created */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AvaliacaoDeContestacao"];
                };
            };
            /** @description Sessão ausente, inválida ou expirada */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Transação não encontrada */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    confirmar_minhas_propostas__proposta_id__confirmacao_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                proposta_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Já confirmado antes: mesmo protocolo */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreCaso"];
                };
            };
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreCaso"];
                };
            };
            /** @description Sessão ausente, inválida ou expirada */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Proposta não encontrada */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Proposta vencida ou situação da transação mudou */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Pré-caso não registrado; nada foi criado */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    meus_pre_casos_minhas_pre_casos_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreCaso"][];
                };
            };
            /** @description Sessão ausente, inválida ou expirada */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
}
