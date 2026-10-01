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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> dict:
    try:
        return _orchestrator.ask(request.question, session_id=request.session_id)
    except AllModelsFailedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
