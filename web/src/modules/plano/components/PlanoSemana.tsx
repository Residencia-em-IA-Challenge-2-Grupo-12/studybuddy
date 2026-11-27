"use client";

import { useEffect, useState } from "react";

import { useFluxo } from "@/modules/fluxo/FluxoProvider";
import { carregarPlano, confirmarPlano } from "@/modules/fluxo/service";
import type { BlocoEstudo, PlanoResposta } from "@/modules/fluxo/types";

import { Markdown } from "../Markdown";

const DIAS_CURTOS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

/** Sete dias a partir de `semana_inicio`, em UTC para não depender do fuso de quem renderiza. */
function diasDaSemana(inicio: string): string[] {
  const base = new Date(`${inicio}T00:00:00Z`).getTime();
  if (Number.isNaN(base)) return [];
  return Array.from({ length: 7 }, (_, i) => new Date(base + i * 86_400_000).toISOString().slice(0, 10));
}

function rotuloDoDia(dia: string): string {
  const data = new Date(`${dia}T00:00:00Z`);
  const curto = DIAS_CURTOS[data.getUTCDay()] ?? "";
  const dd = String(data.getUTCDate()).padStart(2, "0");
  const mm = String(data.getUTCMonth() + 1).padStart(2, "0");
  return `${curto} ${dd}/${mm}`;
}

type Estado = { tipo: "carregando" } | { tipo: "erro"; mensagem: string } | { tipo: "pronto"; dados: PlanoResposta };

export function PlanoSemana() {
  const { materiais } = useFluxo();
  const [estado, setEstado] = useState<Estado>({ tipo: "carregando" });
  const [sincronizado, setSincronizado] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  useEffect(() => {
    let ativo = true;
    carregarPlano()
      .then((dados) => {
        if (ativo) setEstado({ tipo: "pronto", dados });
      })
      .catch((exc) => {
        if (ativo)
          setEstado({
            tipo: "erro",
            mensagem: exc instanceof Error ? exc.message : "Falha ao montar o plano.",
          });
      });
    return () => {
      ativo = false;
    };
  }, []);

  if (estado.tipo === "carregando") {
    return (
      <p className="secundario" role="status">
        Montando a sua semana.
      </p>
    );
  }

  if (estado.tipo === "erro") {
    return (
      <p className="falha" role="alert">
        {estado.mensagem}
      </p>
    );
  }

  const { proposta, validacao, mensagem } = estado.dados;
  const reprovado = validacao.status === "REPROVADO";
  const dias = diasDaSemana(proposta.semana_inicio);
  const porDia = new Map<string, BlocoEstudo[]>();
  for (const bloco of proposta.blocos) {
    porDia.set(bloco.dia, [...(porDia.get(bloco.dia) ?? []), bloco]);
  }

  const tituloDoMaterial = (id: string) => materiais?.find((material) => material.id === id)?.titulo ?? id;

  async function confirmar() {
    if (reprovado || confirmando) return;
    setConfirmando(true);
    try {
      const resultado = await confirmarPlano();
      setSincronizado(resultado.sincronizado);
    } catch {
      setConfirmando(false);
    }
  }

  return (
    <div className="plano">
      {mensagem ? (
        <section className="plano__mensagem" aria-labelledby="titulo-mensagem">
          <h2 id="titulo-mensagem" className="plano__subtitulo">
            Mensagem do mentor
          </h2>
          <div className="prosa mensagem">
            <Markdown texto={mensagem.markdown} />
          </div>
          <p className="texto-menor secundario">tom: {mensagem.tom}</p>
        </section>
      ) : null}

      <section aria-labelledby="titulo-grade">
        <h2 id="titulo-grade" className="plano__subtitulo">
          Semana de {rotuloDoDia(proposta.semana_inicio)}
        </h2>
        <p className="texto-menor secundario">
          {proposta.blocos.length} blocos
          {proposta.modo === "reducao_danos" ? " · modo redução de danos" : ""}
        </p>

        <div className="grade">
          {dias.map((dia) => {
            const blocos = porDia.get(dia) ?? [];
            return (
              <section key={dia} className="grade__dia">
                <h3 className="grade__rotulo">{rotuloDoDia(dia)}</h3>
                {blocos.length === 0 ? (
                  <p className="texto-menor secundario grade__vazio">—</p>
                ) : (
                  <ul className="grade__blocos">
                    {blocos.map((bloco) => (
                      <li key={bloco.id} className="bloco">
                        <p className="bloco__hora">
                          {bloco.inicio}–{bloco.fim}
                        </p>
                        <p className="bloco__disciplina">{bloco.disciplina}</p>
                        <p className="bloco__tecnica texto-menor secundario">{bloco.tecnica}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      </section>

      {proposta.fora_da_grade.length > 0 ? (
        <section aria-labelledby="titulo-fora">
          <h2 id="titulo-fora" className="plano__subtitulo">
            Ficaram fora da grade
          </h2>
          <ul className="lista-simples">
            {proposta.fora_da_grade.map((id) => (
              <li key={id}>{tituloDoMaterial(id)}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {reprovado ? (
        <section className="violacoes" aria-labelledby="titulo-violacoes">
          <h2 id="titulo-violacoes" className="plano__subtitulo">
            O plano precisa de ajuste
          </h2>
          <ul className="lista-simples">
            {validacao.violacoes.map((violacao, indice) => (
              <li key={indice}>
                {violacao.mensagem}
                {typeof violacao.excesso_min === "number" && violacao.excesso_min > 0
                  ? ` Cortar ${violacao.excesso_min} min.`
                  : ""}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="acoes">
        {sincronizado ? (
          <p className="texto-menor" role="status">
            Plano confirmado e sincronizado (simulado neste modo).
          </p>
        ) : (
          <button
            type="button"
            className="botao botao--principal"
            disabled={reprovado || confirmando}
            onClick={confirmar}
          >
            {confirmando ? "Sincronizando…" : "Confirmar e sincronizar"}
          </button>
        )}
      </div>
    </div>
  );
}
