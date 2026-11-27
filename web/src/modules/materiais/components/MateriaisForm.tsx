"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useFluxo } from "@/modules/fluxo/FluxoProvider";
import { EscolhaUnica } from "@/modules/fluxo/components/EscolhaUnica";
import { enviarMateriais } from "@/modules/fluxo/service";
import type { CargaCognitiva, Material } from "@/modules/fluxo/types";

import { montarMaterial, prazoCurto, type CamposMaterial } from "../montagem";

const CARGAS: { valor: CargaCognitiva; rotulo: string }[] = [
  { valor: "alta", rotulo: "Alta" },
  { valor: "baixa", rotulo: "Baixa" },
];

const DIFICULDADES = [1, 2, 3, 4, 5].map((nota) => ({ valor: nota, rotulo: String(nota) }));

export function MateriaisForm() {
  const { materiais, definir } = useFluxo();
  const router = useRouter();

  const [itens, setItens] = useState<Material[]>(materiais ?? []);
  const [editando, setEditando] = useState<string | null>(null);

  const [disciplina, setDisciplina] = useState("");
  const [titulo, setTitulo] = useState("");
  const [carga, setCarga] = useState<CargaCognitiva | null>(null);
  const [horas, setHoras] = useState("");
  const [dificuldade, setDificuldade] = useState<number | null>(null);
  const [prazo, setPrazo] = useState("");

  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const horasNumero = Number(horas);
  const horasOk = horas !== "" && Number.isFinite(horasNumero) && horasNumero > 0 && horasNumero <= 100;
  const podeSalvar =
    disciplina.trim() !== "" && titulo.trim() !== "" && carga !== null && horasOk && dificuldade !== null;

  function limpar() {
    setEditando(null);
    setDisciplina("");
    setTitulo("");
    setCarga(null);
    setHoras("");
    setDificuldade(null);
    setPrazo("");
  }

  function salvar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!podeSalvar || carga === null || dificuldade === null) return;

    const campos: CamposMaterial = {
      disciplina,
      titulo,
      carga,
      horas: horasNumero,
      dificuldade,
      prazo,
    };

    if (editando) {
      setItens((atual) => atual.map((item) => (item.id === editando ? montarMaterial(campos, editando) : item)));
    } else {
      setItens((atual) => [...atual, montarMaterial(campos, crypto.randomUUID())]);
    }
    limpar();
  }

  function editar(item: Material) {
    setEditando(item.id);
    setDisciplina(item.disciplina);
    setTitulo(item.titulo);
    setCarga(item.carga);
    setHoras(String(item.horas_estimadas));
    setDificuldade(item.dificuldade);
    setPrazo(item.prazo ?? "");
  }

  function remover(id: string) {
    setItens((atual) => atual.filter((item) => item.id !== id));
    if (editando === id) limpar();
  }

  async function continuar() {
    if (itens.length === 0 || enviando) return;
    setEnviando(true);
    setErro(null);
    try {
      const devolvido = await enviarMateriais(itens);
      definir({ materiais: devolvido });
      router.push("/plano");
    } catch (exc) {
      setErro(exc instanceof Error ? exc.message : "Não foi possível salvar os materiais.");
      setEnviando(false);
    }
  }

  return (
    <div className="materiais">
      <form className="formulario" onSubmit={salvar}>
        <div className="campo__linha">
          <label className="campo__etiqueta">
            Disciplina
            <input
              className="entrada"
              value={disciplina}
              onChange={(evento) => setDisciplina(evento.target.value)}
              required
            />
          </label>
          <label className="campo__etiqueta campo__etiqueta--larga">
            Título do material
            <input
              className="entrada"
              value={titulo}
              onChange={(evento) => setTitulo(evento.target.value)}
              required
            />
          </label>
        </div>

        <EscolhaUnica rotulo="Carga cognitiva" valor={carga} opcoes={CARGAS} aoMudar={setCarga} />
        <EscolhaUnica
          rotulo="Dificuldade"
          valor={dificuldade}
          opcoes={DIFICULDADES}
          aoMudar={setDificuldade}
          ajuda="1 = tranquilo, 5 = muito difícil"
        />

        <div className="campo__linha">
          <label className="campo__etiqueta">
            Horas estimadas
            <input
              type="number"
              className="entrada entrada--horas"
              min={0.5}
              max={100}
              step={0.5}
              value={horas}
              onChange={(evento) => setHoras(evento.target.value)}
              required
            />
          </label>
          <label className="campo__etiqueta">
            Prazo (opcional)
            <input
              type="date"
              className="entrada"
              value={prazo}
              onChange={(evento) => setPrazo(evento.target.value)}
            />
          </label>
        </div>

        <div className="acoes">
          <button type="submit" className="botao botao--secundario" disabled={!podeSalvar}>
            {editando ? "Salvar alteração" : "Adicionar material"}
          </button>
          {editando ? (
            <button type="button" className="botao botao--secundario" onClick={limpar}>
              Cancelar edição
            </button>
          ) : null}
        </div>
      </form>

      <section className="materiais__lista-area" aria-labelledby="titulo-lista">
        <h2 id="titulo-lista">Materiais cadastrados</h2>
        {itens.length === 0 ? (
          <p className="texto-menor secundario">Adicione ao menos um material para montar o plano.</p>
        ) : (
          <ul className="materiais__lista">
            {itens.map((item) => (
              <li key={item.id} className="material">
                <p className="material__titulo">{item.titulo}</p>
                <p className="material__meta texto-menor secundario">
                  {item.disciplina} · carga {item.carga} · {item.horas_estimadas} h · dificuldade{" "}
                  {item.dificuldade}/5
                  {item.prazo ? ` · prazo ${prazoCurto(item.prazo)}` : ""}
                </p>
                <div className="material__acoes">
                  <button type="button" className="botao botao--secundario" onClick={() => editar(item)}>
                    Editar
                  </button>
                  <button
                    type="button"
                    className="botao botao--secundario"
                    data-acao="remover"
                    onClick={() => remover(item.id)}
                  >
                    Remover
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {erro ? (
        <p className="falha" role="alert">
          {erro}
        </p>
      ) : null}

      <div className="acoes">
        <button
          type="button"
          className="botao botao--principal"
          disabled={itens.length === 0 || enviando}
          onClick={continuar}
        >
          {enviando ? "Salvando…" : "Continuar para o plano"}
        </button>
      </div>
    </div>
  );
}
