"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useFluxo } from "@/modules/fluxo/FluxoProvider";
import { EscolhaUnica } from "@/modules/fluxo/components/EscolhaUnica";
import { carregarContexto } from "@/modules/fluxo/service";
import type { Cronotipo } from "@/modules/fluxo/types";

const CRONOTIPOS: { valor: Cronotipo; rotulo: string }[] = [
  { valor: "matutino", rotulo: "Matutino" },
  { valor: "vespertino", rotulo: "Vespertino" },
  { valor: "noturno", rotulo: "Noturno" },
];

export function OnboardingForm() {
  const { definir } = useFluxo();
  const router = useRouter();

  const [cronotipo, setCronotipo] = useState<Cronotipo | null>(null);
  const [dormir, setDormir] = useState("");
  const [acordar, setAcordar] = useState("");
  const [cafe, setCafe] = useState("");
  const [almoco, setAlmoco] = useState("");
  const [jantar, setJantar] = useState("");
  const [agenda, setAgenda] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const horarios = [dormir, acordar, cafe, almoco, jantar];
  const pronto = cronotipo !== null && horarios.every((horario) => horario !== "") && dormir !== acordar;

  async function enviar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!pronto || cronotipo === null || enviando) return;

    setEnviando(true);
    setErro(null);
    try {
      // A tela manda horários, não datas: quem distribui pelos dias da semana é o Research.
      const contexto = await carregarContexto({
        cronotipo,
        sono: { inicio: dormir, fim: acordar },
        refeicoes: { cafe, almoco, jantar },
        agendaConectada: agenda,
      });
      definir({ contexto });
      router.push("/check-in");
    } catch (exc) {
      setErro(exc instanceof Error ? exc.message : "Não foi possível carregar o contexto.");
      setEnviando(false);
    }
  }

  return (
    <form className="formulario" onSubmit={enviar}>
      <EscolhaUnica rotulo="Cronotipo" valor={cronotipo} opcoes={CRONOTIPOS} aoMudar={setCronotipo} />

      <fieldset className="campo campo--grupo">
        <legend className="campo__rotulo">Sono</legend>
        <div className="campo__linha">
          <label className="campo__etiqueta">
            Dorme às
            <input
              type="time"
              className="entrada"
              value={dormir}
              onChange={(evento) => setDormir(evento.target.value)}
              required
            />
          </label>
          <label className="campo__etiqueta">
            Acorda às
            <input
              type="time"
              className="entrada"
              value={acordar}
              onChange={(evento) => setAcordar(evento.target.value)}
              required
            />
          </label>
        </div>
      </fieldset>

      <fieldset className="campo campo--grupo">
        <legend className="campo__rotulo">Refeições</legend>
        <div className="campo__linha">
          <label className="campo__etiqueta">
            Café
            <input
              type="time"
              className="entrada"
              value={cafe}
              onChange={(evento) => setCafe(evento.target.value)}
              required
            />
          </label>
          <label className="campo__etiqueta">
            Almoço
            <input
              type="time"
              className="entrada"
              value={almoco}
              onChange={(evento) => setAlmoco(evento.target.value)}
              required
            />
          </label>
          <label className="campo__etiqueta">
            Jantar
            <input
              type="time"
              className="entrada"
              value={jantar}
              onChange={(evento) => setJantar(evento.target.value)}
              required
            />
          </label>
        </div>
      </fieldset>

      <div className="campo">
        <button
          type="button"
          className="botao botao--secundario"
          aria-pressed={agenda}
          onClick={() => setAgenda((conectada) => !conectada)}
        >
          {agenda ? "Desconectar Google Calendar" : "Conectar Google Calendar"}
        </button>
        <p className="texto-menor secundario" role="status">
          {agenda
            ? "Agenda conectada (simulada neste modo): nada é lido do seu calendário."
            : "Nenhuma agenda conectada."}
        </p>
      </div>

      {erro ? (
        <p className="falha" role="alert">
          {erro}
        </p>
      ) : null}

      <div className="acoes">
        <button type="submit" className="botao botao--principal" disabled={!pronto || enviando}>
          {enviando ? "Carregando o contexto…" : "Continuar para o check-in"}
        </button>
      </div>
    </form>
  );
}
