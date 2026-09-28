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
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
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
}
