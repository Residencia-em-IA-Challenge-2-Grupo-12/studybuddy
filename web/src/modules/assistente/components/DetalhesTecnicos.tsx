"use client";

import type { Resposta } from "../types";
import { bloqueou } from "../veredito";

/** Equivalente ao _NAO_DITO de api/app/modules/agentes/triagem.py:69. O filtro existe só no Python;
 *  o JSON traz o valor cru, então a tela precisa repetir a regra ou mostra "não especificado" como restrição. */
const NAO_DITO =
  /^(n[aã]o (especificad|mencionad|informad|dit|se aplica)\w*|nenhum\w*|n\/?a|-|desconhecid\w*)\.?$/;

const ROTULOS: Record<string, string> = {
  tempo_disponivel: "Tempo disponível",
  prazo: "Prazo",
  contexto: "Contexto",
};

function restricoesDitas(restricoes: Record<string, string> | undefined): [string, string][] {
  if (!restricoes) return [];
  return Object.entries(restricoes)
    .map(([chave, valor]) => [chave, valor.trim()] as [string, string])
    .filter(([, valor]) => valor.length > 0 && !NAO_DITO.test(valor.toLowerCase()));
}

const numero = (valor: number, casas: number) => valor.toFixed(casas).replace(".", ",");

export function DetalhesTecnicos({ resposta }: { resposta: Resposta }) {
  const { diagnostico, verificacao, rastro, veredito } = resposta;
  const recusada =
    resposta.barrada_pelo_porteiro || verificacao?.recusa === true || bloqueou(veredito);
  const ditas = restricoesDitas(diagnostico?.restricoes);

  return (
    <details className="detalhes">
      <summary className="detalhes__resumo">Detalhes técnicos</summary>

      <div className="detalhes__corpo">
        <section>
          <h3>Métricas</h3>
          <dl className="detalhes__lista">
            <div>
              <dt>Latência</dt>
              <dd>{numero(resposta.latencia_s, 1)} s</dd>
            </div>
            <div>
              <dt>Chamadas ao LLM</dt>
              <dd>{resposta.chamadas_llm}</dd>
            </div>
            <div>
              <dt>d1 (distância do primeiro trecho)</dt>
              <dd>{resposta.d1 === null ? "—" : numero(resposta.d1, 3)}</dd>
            </div>
            {veredito ? (
              <div>
                <dt>Guardrail</dt>
                <dd>
                  {bloqueou(veredito)
                    ? `bloqueou a pergunta (${veredito.categoria ?? "categoria não informada"})${
                        veredito.motivos?.length ? `: ${veredito.motivos.join(", ")}` : ""
                      }`
                    : "liberou a pergunta"}
                </dd>
              </div>
            ) : null}
          </dl>
        </section>

        {diagnostico ? (
          <section>
            <h3>Diagnóstico da triagem</h3>
            <dl className="detalhes__lista">
              {diagnostico.problema_principal ? (
                <div>
                  <dt>Problema principal</dt>
                  <dd>{diagnostico.problema_principal.replace(/_/g, " ")}</dd>
                </div>
              ) : null}
              {diagnostico.objetivo ? (
                <div>
                  <dt>Objetivo</dt>
                  <dd>{diagnostico.objetivo}</dd>
                </div>
              ) : null}
              {ditas.map(([chave, valor]) => (
                <div key={chave}>
                  <dt>{ROTULOS[chave] ?? chave}</dt>
                  <dd>{valor}</dd>
                </div>
              ))}
              {diagnostico.tipo_resposta ? (
                <div>
                  <dt>Tipo de resposta</dt>
                  <dd>{diagnostico.tipo_resposta === "plano" ? "plano" : "explicação"}</dd>
                </div>
              ) : null}
              {diagnostico.consultas?.length ? (
                <div>
                  <dt>Consultas à base</dt>
                  <dd>
                    <ul className="detalhes__consultas">
                      {diagnostico.consultas.map((consulta) => (
                        <li key={consulta}>{consulta}</li>
                      ))}
                    </ul>
                  </dd>
                </div>
              ) : null}
            </dl>
            {diagnostico.falhou ? (
              <p className="aviso texto-menor">
                A Triagem devolveu um diagnóstico neutro: o JSON do modelo veio inválido.
              </p>
            ) : null}
          </section>
        ) : null}

        {verificacao && !recusada ? (
          <section>
            <h3>Verificação de citações</h3>
            <dl className="detalhes__lista">
              <div>
                <dt>Citadas</dt>
                <dd>{verificacao.citadas?.length ? verificacao.citadas.join(", ") : "nenhuma"}</dd>
              </div>
              <div>
                <dt>Removidas</dt>
                <dd>{verificacao.fora_do_contexto?.length ? verificacao.fora_do_contexto.join(", ") : "nenhuma"}</dd>
              </div>
              <div>
                <dt>Sem citação</dt>
                <dd>{verificacao.sem_citacao ? "sim" : "não"}</dd>
              </div>
            </dl>
          </section>
        ) : null}

        {rastro.length > 0 ? (
          <section>
            <h3>Rastro por agente</h3>
            <ol className="rastro">
              {rastro.map((evento, indice) => (
                <li key={indice} className="rastro__item">
                  <p className="rastro__linha">
                    <span className="rastro__agente">{evento.agente}</span> · {evento.acao} ·{" "}
                    {numero(evento.segundos, 2)} s
                  </p>
                  {evento.detalhe ? <p className="rastro__detalhe texto-menor secundario">{evento.detalhe}</p> : null}
                </li>
              ))}
            </ol>
          </section>
        ) : null}
      </div>
    </details>
  );
}
