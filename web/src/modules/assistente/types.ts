/** Contrato de `POST /assistente/perguntar` e `GET /assistente/info`
 *  (api/app/modules/assistente/schemas.py), sem camada de tradução. */

export type Pipeline = "classico" | "agentes";

/** Uma linha do rastro. `detalhe` pode conter quebras de linha (orquestrador.py:54-56). */
export type Evento = {
  agente: string;
  acao: string;
  detalhe: string;
  segundos: number;
};

/** Diagnóstico da Triagem. Vem cru: o modelo pode omitir chaves, e `restricoes` aceita qualquer
 *  chave que ele tenha devolvido (interpretar() filtra só o tipo do valor, não o nome). */
export type Diagnostico = {
  problema_principal?: string;
  objetivo?: string;
  restricoes?: Record<string, string>;
  tipo_resposta?: "plano" | "explicacao";
  consultas?: string[];
  falhou?: boolean;
};

/** O que o verificador encontrou. As listas contêm IDs `artigo_NN`, não nomes de arquivo. */
export type Verificacao = {
  recusa?: boolean;
  citadas?: string[];
  fora_do_contexto?: string[];
  sem_citacao?: boolean;
  alterou?: boolean;
};

/** O veredito dos guardrails mora em `lib/veredito.ts`, porque o fluxo também consome. */
export type { Veredito } from "@/lib/veredito";

import type { Veredito } from "@/lib/veredito";

/** Resultado da barreira de guardrails (ver `lib/veredito.ts`). */

export type Resposta = {
  pipeline: Pipeline;
  pergunta: string;
  resposta: string;
  /** Nomes dos arquivos consultados (`artigo_NN_*.txt`), deduplicados, na ordem de aparição. */
  fontes: string[];
  /** Distância L2 do primeiro trecho. Não finito chega como `null` no JSON. */
  d1: number | null;
  barrada_pelo_porteiro: boolean;
  chamadas_llm: number;
  diagnostico: Diagnostico | null;
  verificacao: Verificacao | null;
  /** Opcional de propósito: um servidor anterior à barreira não manda o campo. */
  veredito?: Veredito | null;
  latencia_s: number;
  rastro: Evento[];
};

export type Info = {
  pipeline: Pipeline;
  llm: string;
  triagem: string | null;
  embedding: string;
  top_k: number;
  porteiro_tau: number | null;
};
