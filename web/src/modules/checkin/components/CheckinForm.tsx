"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { BloqueioError } from "@/lib/veredito";
import { useFluxo } from "@/modules/fluxo/FluxoProvider";
import { EscolhaUnica } from "@/modules/fluxo/components/EscolhaUnica";
import { EstadoBloqueio, causaDoBloqueio } from "@/modules/fluxo/components/EstadoBloqueio";
import { enviarCheckin } from "@/modules/fluxo/service";
import type { EscalasCheckIn } from "@/modules/fluxo/types";

import { paraCheckIn } from "../mapeamento";

const NOTAS = [1, 2, 3, 4, 5].map((nota) => ({ valor: nota, rotulo: String(nota) }));
const AJUDA = "1 = muito baixo, 5 = muito alto";

export function CheckinForm() {
  const { definir } = useFluxo();
  const router = useRouter();

  const [humor, setHumor] = useState<number | null>(null);
  const [estresse, setEstresse] = useState<number | null>(null);
  const [sono, setSono] = useState<number | null>(null);
  const [fadiga, setFadiga] = useState<number | null>(null);
  const [horas, setHoras] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [bloqueio, setBloqueio] = useState<BloqueioError | null>(null);

  const horasNumero = Number(horas);
  const horasOk = horas !== "" && Number.isFinite(horasNumero) && horasNumero >= 0 && horasNumero <= 24;
  const escalasOk = humor !== null && estresse !== null && sono !== null && fadiga !== null;
  const pronto = escalasOk && horasOk;

  async function enviar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!pronto || humor === null || estresse === null || sono === null || fadiga === null || enviando) return;

    setEnviando(true);
    setErro(null);
    setBloqueio(null);
    try {
      const escalas: EscalasCheckIn = { humor, estresse, sono, fadiga };
      const checkin = paraCheckIn(escalas, horasNumero);
      const devolvido = await enviarCheckin(checkin);
      definir({ checkin: devolvido, escalas });
      router.push("/materiais");
    } catch (exc) {
      if (exc instanceof BloqueioError) setBloqueio(exc);
      else setErro(exc instanceof Error ? exc.message : "Não foi possível registrar o check-in.");
      setEnviando(false);
    }
  }

  return (
    <form className="formulario" onSubmit={enviar}>
      <EscolhaUnica rotulo="Humor" valor={humor} opcoes={NOTAS} aoMudar={setHumor} ajuda={AJUDA} />
      <EscolhaUnica rotulo="Estresse" valor={estresse} opcoes={NOTAS} aoMudar={setEstresse} ajuda={AJUDA} />
      <EscolhaUnica rotulo="Qualidade do sono" valor={sono} opcoes={NOTAS} aoMudar={setSono} ajuda={AJUDA} />
      <EscolhaUnica rotulo="Fadiga" valor={fadiga} opcoes={NOTAS} aoMudar={setFadiga} ajuda={AJUDA} />

      <div className="campo">
        <label className="campo__etiqueta" htmlFor="horas-sono">
          Horas de sono na última noite
          <input
            id="horas-sono"
            type="number"
            className="entrada entrada--horas"
            min={0}
            max={24}
            step={0.5}
            value={horas}
            onChange={(evento) => setHoras(evento.target.value)}
            required
          />
        </label>
        <p className="texto-menor secundario">
          As horas vão para o contrato do check-in; humor e qualidade do sono ficam guardados aqui.
        </p>
      </div>

      {bloqueio ? (
        <EstadoBloqueio frase={bloqueio.mensagem} causa={causaDoBloqueio(bloqueio.categoria, "pedido")} />
      ) : null}

      {erro ? (
        <p className="falha" role="alert">
          {erro}
        </p>
      ) : null}

      <div className="acoes">
        <button type="submit" className="botao botao--principal" disabled={!pronto || enviando}>
          {enviando ? "Registrando…" : "Continuar para os materiais"}
        </button>
      </div>
    </form>
  );
}
