FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# torch só para CPU: o pacote padrão do PyPI para Linux puxa as bibliotecas
# CUDA (pacotes nvidia-*), inúteis aqui — os embeddings das sinopses rodam em CPU. Instalado antes do requirements para o
# sentence-transformers reaproveitá-lo em vez de baixar a versão com CUDA.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ app/
COPY eval/ eval/
COPY static/ static/

# Usuário sem privilégios; data/ (banco, cache, índice de embeddings) e o cache
# do modelo de embeddings vêm de volumes (ver docker-compose.yml).
RUN useradd --create-home --uid 1000 app && mkdir -p data && chown app:app data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
