"""Plugin do Research Agent na harness de experimentação de modelos locais ([2.0] Issue #55).

Onde o Research usa modelo: sintetizar as evidências científicas recuperadas no ChromaDB para o
perfil circadiano, check-in e acervo de materiais do estudante (`SaidaResearchLLM`).

Os casos saem das 7 fixtures canônicas da [0.2] (`api/tests/fixtures/contexto/`) + 3 variações de
perfil/personas (Lucas CLT com privação de sono, Lisa com overplanning/alta demanda, Bob com
edital extenso), totalizando 10 casos padronizados.

Métricas do agente (além de `json_valido`, `fidelidade`, `segundos`, `tokens_s` e `ram_gb` da harness):
  - `citacao_valida`: sobrou ao menos uma citação de artigo recebido depois do verificador;
  - `citacoes_mantidas`: fração das citações feitas que o verificador manteve (precisão ALCE);
  - `aderencia_cronotipo`: a orientação circadiana e o foco recomendado respeitam o cronotipo
    (`matutino`, `vespertino`, `noturno`) e o estado do check-in (`alta_energia`, `normal`, `fadiga`).
"""

from __future__ import annotations

import unicodedata

from langchain_core.documents import Document

from ..rodar import API_DIR, Caso, Config  # garante api/ no sys.path

from app.modules.agentes.contratos import CheckIn, ContextoEstudante
from app.modules.agentes.research import (
    AgenteResearch,
    SaidaResearchLLM,
    carregar_e_segmentar_acervo,
    classificar_estado_capacidade,
    montar_prompt_research,
)
from app.modules.rag.fontes import formatar_trechos, nome_fonte
from app.modules.rag.verificador import verificar

FIXTURES = API_DIR / "tests" / "fixtures" / "contexto"

PISTAS_CRONOTIPO = {
    "matutino": ("matutin", "manha", "08:00", "06:00", "cedo"),
    "vespertino": ("vespertin", "tarde", "15:30", "18:30"),
    "noturno": ("noturn", "noite", "19:30", "22:30"),
}

PISTAS_ESTADO = {
    "fadiga": ("fadiga", "25", "pausa", "sono", "leve", "reduz", "curto", "descanso"),
    "alta_energia": ("alta", "50", "profundo", "deep", "pico", "estendid", "foco"),
    "normal": ("normal", "25", "sustent", "equilibr", "ciclo", "pico", "pomodoro"),
}


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def aderencia_cronotipo_e_estado(
    saida: SaidaResearchLLM,
    cronotipo: str,
    estado_capacidade: str,
) -> bool:
    """Verifica se a saída do modelo aborda o cronotipo/horários de pico e o estado do check-in."""
    texto_orient = _sem_acento(f"{saida.orientacao_circadiana} {saida.foco_recomendado}")
    acertou_crono = any(p in texto_orient for p in PISTAS_CRONOTIPO.get(cronotipo, ()))
    acertou_estado = any(p in texto_orient for p in PISTAS_ESTADO.get(estado_capacidade, ()))
    return acertou_crono and acertou_estado


def contexto_do_juiz_research(prompt: str, trechos: list[Document]) -> str:
    """Contexto factual entregue ao LLM-juiz: perfil/estado do estudante + trechos científicos."""
    ini = prompt.index("PERFIL E ESTADO DO ESTUDANTE:")
    fim = prompt.index("TRECHOS DA BASE CIENTÍFICA:")
    return f"{prompt[ini:fim].strip()}\n\nTRECHOS DA BASE CIENTÍFICA:\n{formatar_trechos(trechos)}"


def _buscador_deterministico_offline():
    """Buscador por sobreposição lexical sobre os 49 chunks reais quando o Ollama não está ativo na montagem."""
    chunks = [c for c in carregar_e_segmentar_acervo() if c.metadata.get("tipo_chunk") != "cabecalho"]
    stopwords = {
        "como", "para", "devo", "meus", "minha", "quando", "quais", "posso", "uma", "dos", "das",
        "por", "dia", "que", "nao", "mais", "sem", "nos", "nas", "com", "sobre", "forma", "tudo",
        "vez", "horas", "sinto", "consigo", "perco", "sempre", "surge", "meu",
    }

    def _tokens(txt: str) -> set[str]:
        import re

        palavras = re.findall(r"[a-z0-9]+", _sem_acento(txt))
        out: set[str] = set()
        for p in palavras:
            if len(p) > 2 and p not in stopwords:
                out.add(p)
                if len(p) >= 6:
                    out.add(p[:6])
        return out

    def buscar(consulta: str, k: int) -> list[tuple[Document, float]]:
        termos = _tokens(consulta)
        pontuados: list[tuple[Document, float]] = []
        for doc in chunks:
            corpo_tokens = _tokens(
                f"{doc.page_content} {doc.metadata.get('tecnica_principal', '')} {doc.metadata.get('arquivo', '')}"
            )
            hits = len(termos & corpo_tokens)
            dist = round(max(0.20, 0.88 - 0.08 * hits), 4)
            pontuados.append((doc, dist))
        pontuados.sort(key=lambda item: (item[1], item[0].metadata.get("chunk_id", 0)))
        return pontuados[:k]

    return buscar


class AgenteResearchExperimento:
    """Adaptador do Research Agent para `pesquisa/experimentos/modelos/rodar.py`."""

    nome = "research"
    contrato = SaidaResearchLLM
    configs_padrao = [
        Config("llama3.1:8b"),
        Config("qwen3.5:4b"),
        Config("qwen3:8b"),
        Config("qwen3.5:9b"),
        Config("gemma3:12b"),
        Config("ministral-3:8b"),
        Config("qwen3.5:9b", reasoning=True),
        Config("qwen3.5:9b", temperature=0.7),
        Config("qwen3.5:9b", formato=False),
    ]

    def __init__(self) -> None:
        self._casos: list[Caso] | None = None

    def casos(self) -> list[Caso]:
        if self._casos is None:
            self._casos = self._montar()
        return self._casos

    def _obter_buscador(self):
        try:
            from app.modules.rag import repository as rag_repo

            rag_repo.buscar("teste", k=1)
            return lambda q, k: rag_repo.buscar(q, k=k)
        except Exception:
            return _buscador_deterministico_offline()

    def _montar(self) -> list[Caso]:
        agente = AgenteResearch()
        buscador = self._obter_buscador()

        entradas: list[tuple[str, ContextoEstudante]] = [
            (p.stem, ContextoEstudante.model_validate_json(p.read_text(encoding="utf-8")))
            for p in sorted(FIXTURES.glob("*.json"))
        ]

        # +3 cenários específicos das Personas (Lucas CLT fadiga, Lisa overplanning, Bob edital extenso)
        base_clt = next(c for n, c in entradas if n == "agenda_cheia")
        entradas.append(
            (
                "persona_lucas_clt_fadiga",
                base_clt.model_copy(
                    update={
                        "checkin": CheckIn(energia=2, horas_sono=5.0, estresse=4),
                        "indice_capacidade": 0.35,
                    }
                ),
            )
        )
        base_vesp = next(c for n, c in entradas if n == "vespertino")
        entradas.append(
            (
                "persona_lisa_vespertino_alta",
                base_vesp.model_copy(
                    update={
                        "checkin": CheckIn(energia=5, horas_sono=8.0, estresse=1),
                        "indice_capacidade": 0.9,
                    }
                ),
            )
        )
        base_not = next(c for n, c in entradas if n == "noturno")
        entradas.append(
            (
                "persona_bob_noturno_prazo",
                base_not.model_copy(
                    update={
                        "checkin": CheckIn(energia=4, horas_sono=7.5, estresse=2),
                        "indice_capacidade": 0.74,
                    }
                ),
            )
        )

        casos: list[Caso] = []
        for rotulo, ctx in entradas:
            _, evidencias = agente.pesquisar_evidencias(ctx, buscador=buscador)
            trechos = [
                Document(
                    page_content=e.texto,
                    metadata={"source": f"../api/data/{e.source}", "chunk_id": e.chunk_id},
                )
                for e in evidencias
            ]
            prompt = montar_prompt_research(ctx, trechos)
            estado = classificar_estado_capacidade(ctx.indice_capacidade)
            casos.append(
                Caso(
                    id=rotulo,
                    prompt=prompt,
                    contexto=contexto_do_juiz_research(prompt, trechos),
                    dados={
                        "cronotipo": ctx.cronotipo,
                        "estado_capacidade": estado,
                        "trechos": [
                            {"source": nome_fonte(d.metadata.get("source", "")), "texto": d.page_content}
                            for d in trechos
                        ],
                    },
                )
            )
        return casos

    def avaliar(self, caso: Caso, objeto: SaidaResearchLLM | None) -> dict:
        if objeto is None:
            return {
                "citacao_valida": 0.0,
                "citacoes_mantidas": None,
                "aderencia_cronotipo": 0.0,
            }
        trechos = [
            Document(page_content=t["texto"], metadata={"source": t["source"]})
            for t in caso.dados["trechos"]
        ]
        _, v = verificar(objeto.sintese_evidencias, trechos)
        total = len(v.citadas) + len(v.fora_do_contexto)
        return {
            "citacao_valida": float(bool(v.citadas)),
            "citacoes_mantidas": (len(v.citadas) / total) if total else None,
            "aderencia_cronotipo": float(
                aderencia_cronotipo_e_estado(
                    objeto,
                    caso.dados["cronotipo"],
                    caso.dados["estado_capacidade"],
                )
            ),
        }

    def resposta(self, objeto: SaidaResearchLLM) -> str:
        return f"{objeto.foco_recomendado} {objeto.orientacao_circadiana} {objeto.sintese_evidencias}"

    def metricas(self) -> list[str]:
        return ["citacao_valida", "citacoes_mantidas", "aderencia_cronotipo"]
