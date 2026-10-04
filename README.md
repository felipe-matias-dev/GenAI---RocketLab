# CineData Analytics — Agente Text-to-SQL

Agente em Python que responde perguntas em linguagem natural sobre o
catálogo de filmes da CineData Analytics, convertendo-as em SQL de leitura
contra a camada Gold (`cinerocket.db`, SQLite) e executando-as com
segurança. Feito para a atividade GenAI do Rocket Lab 2026 (Visagio).

## Arquitetura

- **FastAPI** expõe `POST /ask` (e uma UI estática em `/` com painel de
  detalhes técnicos — confiança, SQL final e raciocínio).
- **Loop de tool-calling manual** (sem LangChain) usando o SDK `openai`
  apontado para o OpenRouter (`app/orchestrator.py`), concluído por uma
  tool obrigatória `finalize_answer(answer, confidence, reasoning)` — o
  próprio modelo reporta sua confiança (0.0–1.0) e o raciocínio que levou à
  resposta, em vez de só devolver texto livre.
- **Schema linking leve** (`app/schema_linking.py`): antes do loop
  principal, uma chamada extra ao mesmo client OpenRouter identifica as
  tabelas/colunas provavelmente relevantes para a pergunta. É só uma dica
  injetada no prompt (exposta em `schema_link` na resposta) — nunca uma
  restrição nem uma fronteira de segurança; se falhar, cai para o schema
  completo sem travar a pergunta.
- **Guardrails** (`app/guardrails.py`): só SELECT/WITH/EXPLAIN, uma única
  instrução, LIMIT obrigatório — reforçado por uma conexão SQLite aberta em
  **modo somente-leitura no nível do SO** (`app/db.py`), então mesmo uma
  falha na validação não permitiria escrever no banco. O prompt de sistema
  também instrui o modelo a recusar (via `finalize_answer` com `confidence
  0.0`) pedidos para ignorar instruções, mudar de persona ou sair do
  domínio do catálogo de filmes.
- **Descoberta de valores** (`app/tools.py`/`app/db.py`): a tool
  `get_distinct_values` deixa o modelo checar a grafia exata de valores de
  texto (gênero, diretor, produtora) antes de montar um filtro WHERE, em
  vez de assumir a grafia que o usuário usou.
- **Cache de respostas** (`app/cache.py`): pergunta normalizada → resposta,
  usado apenas para perguntas sem histórico de sessão, para não gastar a
  cota diária do OpenRouter repetindo perguntas.
- **Memória de conversa** (`app/memory.py`): histórico por `session_id`, em
  memória (não sobrevive a um restart do servidor — tradeoff assumido por
  simplicidade).
- **Cadeia de modelos com escalonamento por falha** (`app/llm.py` +
  `app/orchestrator.py`): tenta sempre o modelo padrão primeiro; se a
  chamada falhar por erro de infraestrutura (429/5xx) ou o agente não
  resolver a pergunta dentro do limite de iterações de tool-calling com
  aquele modelo, escala para o próximo modelo gratuito da cadeia. Falhas de
  SQL (ex.: coluna errada) são corrigidas pelo próprio modelo dentro do
  loop de tool-calling antes de qualquer troca de modelo.
- **Agente híbrido** (`app/embeddings.py`): busca semântica sobre as
  sinopses via embeddings locais (`sentence-transformers`), sem custo de
  cota — o LLM escolhe entre `execute_sql` e `semantic_search_synopses`
  conforme o tipo de pergunta.
- **Avaliação** (`eval/`): conjunto de perguntas cobrindo as 5 categorias
  do enunciado + casos de guardrail e busca semântica.

## Pré-requisitos

- Python 3.12
- Uma chave da API do OpenRouter (grátis, sem cartão) — veja
  `openrouter.ai/keys`. **Limite:** 50 requisições/dia compartilhadas entre
  todos os modelos `:free`.
- O arquivo **`cinerocket.db`** (~580MB) — não está neste repositório por
  exceder o limite de tamanho do GitHub. Baixe-o da pasta compartilhada da
  atividade e coloque em `data/cinerocket.db`.

## Passo a passo

```bash
# 1. Clonar e entrar no projeto
git clone <url-do-seu-repositorio>
cd cinedata-agent

# 2. Ambiente virtual
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar variáveis de ambiente
cp .env.example .env
# edite .env e cole sua OPENROUTER_API_KEY

# 5. Colocar o banco de dados
mkdir -p data
# copie cinerocket.db para data/cinerocket.db

# 6. Rodar os testes (não usam rede nem a API — podem rodar sempre)
pytest

# 7. Subir o servidor
uvicorn app.main:app --reload
```

Abra `http://localhost:8000` para a UI mínima, ou use a API diretamente:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Quais os 10 filmes com maior receita em R$?"}'
```

Para uma conversa com memória, reenvie o mesmo `session_id`:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "E os 5 mais populares?", "session_id": "minha-sessao-1"}'
```

Resposta:

```json
{
  "answer": "...",
  "sql_used": ["SELECT ... LIMIT 500"],
  "data": [...],
  "model_used": "nvidia/nemotron-3.5-lightning:free",
  "confidence": 0.9,
  "reasoning": "...",
  "schema_link": {"tables": ["dim_movies"], "columns": ["receita_brl"], "reasoning": "..."}
}
```

`confidence`, `reasoning` e `schema_link` são omitidos da resposta quando
`null` (ex.: no caminho de fallback para um modelo que não chamou
`finalize_answer`, ou quando o schema linking falhou).

## Rodando via CLI

Para perguntar direto no terminal, sem subir o servidor HTTP:

```bash
python -m app.cli
```

Reaproveita a mesma fiação de produção (`app/factory.py`) usada pela API —
útil para testar rapidamente sem abrir o navegador.

## Rodando a avaliação

`eval/run_eval.py` roda um conjunto fixo de ~20 perguntas (cobrindo as 5
categorias do enunciado, mais casos de guardrail/jailbreak, busca
semântica, `EXPLAIN` e `get_distinct_values`) contra o agente real e gera
`eval/results.md` com confiança, raciocínio e schema linking por pergunta.

```bash
python -m eval.run_eval
```

**Atenção:** cada pergunta nova consome cota real do OpenRouter. Perguntas
repetidas entre execuções usam o cache e não gastam cota. Rode com
moderação — não faz parte da suíte `pytest`.

## Sobre a cota de 50 requisições/dia

- Verifique o uso em `openrouter.ai/activity` ou via
  `GET https://openrouter.ai/api/v1/key`.
- O cache de respostas e o índice de embeddings local (busca semântica)
  não consomem cota.
- O escalonamento entre modelos só troca de modelo em caso de erro de
  infraestrutura ou esgotamento do limite de iterações — não dobra o custo
  de toda pergunta.

## Fora de escopo (decisão consciente)

- **Conexão com Databricks**: exigiria infraestrutura própria de outra
  atividade; fora do escopo de tempo deste projeto.
- **Persistência de memória entre reinícios**: a memória de conversa é
  perdida ao reiniciar o servidor (aceitável para o escopo da atividade).

## Estrutura do projeto

```
app/
  main.py          FastAPI: POST /ask, GET /health, serve static/
  cli.py            REPL interativo (python -m app.cli)
  factory.py         monta o Orchestrator de produção
  config.py            variáveis de ambiente e constantes
  db.py                 conexão SQLite somente-leitura + introspecção de schema
  guardrails.py          validação de SQL (SELECT/WITH/EXPLAIN)
  llm.py                   cliente OpenRouter + conversão de erros de infra
  tools.py                  schemas de tools (execute_sql, semantic_search_synopses,
                             get_distinct_values, finalize_answer)
  orchestrator.py            loop de tool-calling, memória, escalonamento por falha
  schema_linking.py           chamada leve de schema linking (dica de tabelas/colunas)
  memory.py                     histórico de conversa por sessão
  cache.py                       cache de resposta por pergunta normalizada
  embeddings.py                   índice local de embeddings sobre as sinopses
static/index.html    UI (pergunta + resposta + gráfico + painel de detalhes técnicos)
eval/                 conjunto de avaliação e gerador de relatório
tests/                suíte pytest (sem rede — roda sempre)
data/                 cinerocket.db + cache/embeddings gerados (gitignored)
```
