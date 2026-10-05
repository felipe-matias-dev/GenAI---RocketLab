import os

# A suíte não usa rede: o app.main monta o orchestrator na importação, e a
# checagem do catálogo do OpenRouter faria uma chamada HTTP real. Definido
# antes de qualquer `import app...` (o conftest carrega primeiro), então o
# load_dotenv de app/config.py não sobrescreve.
os.environ["MODEL_CATALOG_CHECK"] = "off"
