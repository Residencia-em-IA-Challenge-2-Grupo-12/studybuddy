"use client";

import { useEffect, useRef, useState } from "react";

import { API_URL, ApiError } from "@/lib/api";
import { PerguntaForm } from "@/modules/assistente/components/PerguntaForm";
import { PipelineToggle } from "@/modules/assistente/components/PipelineToggle";
import { RespostaCard } from "@/modules/assistente/components/RespostaCard";
import { obterInfo, perguntar } from "@/modules/assistente/service";
import type { Pipeline, Resposta } from "@/modules/assistente/types";

// O mesmo comando de api/README.md:15.
const COMANDO_DO_BACKEND = "cd api && uvicorn app.main:app --reload";

/** Um estado por causa (§5 do plano): 503, 504, 422, 500 e API fora do ar não são o mesmo erro. */
type Falha = {
  titulo: string;
  mensagem: string;
  detalhe?: string;
  comando?: string;
  tentarDeNovo: boolean;
};

function descreverErro(erro: unknown): Falha {
  if (erro instanceof ApiError) {
    switch (erro.status) {
      case 503:
        return {
          titulo: "O servidor está sem índice ou o Ollama não está respondendo.",
          mensagem: "A busca nos artigos depende do índice vetorial e dos modelos locais.",
          detalhe: erro.detail,
          tentarDeNovo: true,
        };
      case 504:
        return {
          titulo: "O modelo local demorou demais.",
          mensagem: "A resposta passou do tempo limite configurado no servidor.",
          detalhe: erro.detail,
          tentarDeNovo: true,
        };
      case 422:
        return {
          titulo: "A pergunta não passou na validação.",
          mensagem: erro.detail,
          tentarDeNovo: false,
        };
      default:
        return {
          titulo: "O servidor respondeu com um erro inesperado.",
          mensagem: `A API respondeu ${erro.status}.`,
          detalhe: erro.body || erro.detail,
          tentarDeNovo: true,
        };
    }
  }

  // API fora do ar não é 503: é o fetch que não chega, e o navegador lança TypeError.
  if (erro instanceof TypeError) {
    return {
      titulo: `Não foi possível falar com a API em ${API_URL}.`,
      mensagem: "O assistente responde a partir do backend FastAPI, e ele não respondeu nesse endereço.",
      comando: COMANDO_DO_BACKEND,
      tentarDeNovo: true,
    };
  }

  return {
    titulo: "Algo deu errado.",
    mensagem: erro instanceof Error ? erro.message : "Falha inesperada.",
    tentarDeNovo: true,
  };
}

type Estado = { tipo: "parado" } | { tipo: "esperando" } | { tipo: "erro"; falha: Falha };

export default function Home() {
  const [pipeline, setPipeline] = useState<Pipeline>("classico");
  const [estado, setEstado] = useState<Estado>({ tipo: "parado" });
  const [resposta, setResposta] = useState<Resposta | null>(null);

  // Se o estudante já escolheu o modo, o /info que chega depois não sobrescreve a escolha.
  const escolheuModo = useRef(false);
  const emAndamento = useRef<AbortController | null>(null);
  const ultimaPergunta = useRef("");

  // O /info só define o padrão: nunca bloqueia o formulário.
  useEffect(() => {
    const controle = new AbortController();
    obterInfo(controle.signal)
      .then((info) => {
        if (!escolheuModo.current) setPipeline(info.pipeline);
      })
      .catch(() => {
        /* sem /info, o formulário segue no padrão clássico */
      });
    return () => controle.abort();
  }, []);

  useEffect(() => () => emAndamento.current?.abort(), []);

  function escolherModo(novo: Pipeline) {
    escolheuModo.current = true;
    setPipeline(novo);
  }

  async function enviar(pergunta: string) {
    ultimaPergunta.current = pergunta;
    emAndamento.current?.abort();
    const controle = new AbortController();
    emAndamento.current = controle;

    setResposta(null);
    setEstado({ tipo: "esperando" });

    try {
      const dados = await perguntar(pergunta, pipeline, controle.signal);
      if (controle.signal.aborted) return;
      setResposta(dados);
      setEstado({ tipo: "parado" });
    } catch (erro) {
      if (controle.signal.aborted) {
        setEstado({ tipo: "parado" });
        return;
      }
      setEstado({ tipo: "erro", falha: descreverErro(erro) });
    }
  }

  function repetir() {
    if (ultimaPergunta.current) void enviar(ultimaPergunta.current);
  }

  function cancelar() {
    emAndamento.current?.abort();
    setEstado({ tipo: "parado" });
  }

  return (
    <main className="pagina">
      {/* Região viva: anuncia o começo e o fim da espera sem repetir o resultado inteiro. */}
      <p className="sr-only" aria-live="polite">
        {estado.tipo === "esperando" ? "Consultando os artigos." : resposta ? "Resposta pronta." : ""}
      </p>

      <header className="cabecalho">
        <h1>Pergunte o que travou no seu estudo</h1>
        <p className="cabecalho__linha secundario">
          As respostas saem dos 20 artigos da base e citam a fonte no próprio texto.
        </p>
      </header>

      <div className="assistente">
        <PipelineToggle valor={pipeline} aoMudar={escolherModo} />
        <PerguntaForm carregando={estado.tipo === "esperando"} aoEnviar={enviar} aoCancelar={cancelar} />
      </div>

      {estado.tipo === "erro" && (
        <section className="falha" role="alert" aria-labelledby="titulo-falha">
          <h2 className="falha__titulo" id="titulo-falha">
            {estado.falha.titulo}
          </h2>
          <p className="falha__mensagem">{estado.falha.mensagem}</p>

          {estado.falha.comando ? (
            <pre className="falha__comando">
              <code>{estado.falha.comando}</code>
            </pre>
          ) : null}

          <div className="falha__acoes">
            {estado.falha.tentarDeNovo ? (
              <button type="button" className="botao botao--secundario" onClick={repetir}>
                Tentar de novo
              </button>
            ) : null}

            {estado.falha.detalhe ? (
              <details className="detalhes detalhes--falha">
                <summary className="detalhes__resumo">Detalhes do erro</summary>
                <p className="falha__detalhe texto-menor">{estado.falha.detalhe}</p>
              </details>
            ) : null}
          </div>
        </section>
      )}

      {resposta && <RespostaCard resposta={resposta} />}
    </main>
  );
}
