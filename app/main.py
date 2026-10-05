from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import BASE_DIR
from app.factory import build_orchestrator
from app.orchestrator import AllModelsFailedError

STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="CineData Analytics — Agente Text-to-SQL")

_orchestrator = build_orchestrator()


class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sql_used: list[str]
    data: Optional[list[dict]] = None
    model_used: str
    confidence: Optional[float] = None
    reasoning: Optional[str] = None
    schema_link: Optional[dict] = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/models")
def models() -> dict:
    """Cadeia de modelos em uso, na ordem de tentativa, já sem os modelos que
    a checagem do catálogo do OpenRouter descartou ao iniciar."""
    return {"model_chain": _orchestrator.model_chain}


_OPTIONAL_FIELDS_OMITTED_WHEN_NONE = ("confidence", "reasoning", "schema_link")


@app.post("/ask")
def ask(request: AskRequest) -> dict:
    """Validamos contra `AskResponse` manualmente (abaixo) em vez de usar
    `response_model=AskResponse` no decorator: o `response_model` do
    FastAPI reaplicaria a serialização padrão (preenchendo de volta os
    campos ausentes com `None`) por cima de qualquer dict que a função
    devolvesse, anulando a omissão seletiva feita aqui."""
    try:
        result = _orchestrator.ask(request.question, session_id=request.session_id)
    except AllModelsFailedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Omitimos apenas os 3 campos novos quando ausentes (para o payload
    # antigo continuar idêntico) — response_model_exclude_none faria isso
    # para QUALQUER campo None, o que faria `data` (que legitimamente pode
    # ser null) desaparecer do JSON em vez de aparecer como `null`.
    validated = AskResponse(**result)
    payload = validated.model_dump(exclude=set(_OPTIONAL_FIELDS_OMITTED_WHEN_NONE))
    for field in _OPTIONAL_FIELDS_OMITTED_WHEN_NONE:
        value = getattr(validated, field)
        if value is not None:
            payload[field] = value
    return payload


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
