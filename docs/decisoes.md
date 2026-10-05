# Decisões técnicas

Cada decisão segue o mesmo formato: o problema (com o número que o revelou),
o que foi decidido, as alternativas descartadas quando houve alguma, e o efeito
visível. Os números vêm do `cinerocket.db`, da suíte de testes, da avaliação
(`eval/results.md`) ou das mensagens de commit indicadas entre parênteses.

## Agente

### D1. Loop de tool-calling próprio, encerrado por `finalize_answer`

- **Decisão:** o loop de tool-calling é escrito à mão sobre o SDK `openai`
  (`app/orchestrator.py`), sem framework de agentes. Toda resposta termina
  com a tool obrigatória `finalize_answer(answer, confidence, reasoning)`.
- **Efeito:** a API devolve `confidence` (0.0–1.0) e `reasoning`, reportados
  pelo próprio modelo. A avaliação usa `confidence ≤ 0,2` como critério de
  recusa: `guardrail-01` e `jailbreak-01` passaram com 0 SQL executado e
  confiança 0.0. O mesmo loop decide quando escalar de modelo: por erro de
  infraestrutura ou ao esgotar `MAX_TOOL_ITERATIONS = 6` sem resposta.
- O motivo de não usar um framework não ficou registrado no histórico do
  projeto.

### D2. Regras analíticas medidas no banco, escritas no prompt

- **Problema:** o banco tem armadilhas que levam a respostas plausíveis e
  erradas. 96,5% dos filmes não têm receita (92.272 de 95.645) e 91,7% não têm
  orçamento. O lucro médio por gênero vale US$ 37,6 mi filtrando só receita e
  US$ 61,1 mi exigindo também orçamento. `dim_people` tem 48.210 nomes
  duplicados.
- **Decisão:** o prompt de sistema diz qual filtro usar em cada caso, manda
  agrupar pela chave e não pelo nome, e traz a data de hoje para "últimos N
  anos" (`214c545`).
- **Efeito:** na avaliação, 18 de 18 perguntas com gabarito acertaram,
  incluindo `fin-02` (lucro por gênero) e `cast-01` (ator dos últimos 5 anos).

### D3. Consulta pronta para a dupla ator–diretor

- **Problema:** o JOIN direto entre `dim_people` e `bridge_movie_person`
  (745.450 linhas) não terminava em 90 s.
- **Decisão:** o prompt traz a consulta otimizada: diretores materializados
  num CTE e agrupamento pelas chaves antes de buscar os nomes.
- **Efeito:** a consulta roda em cerca de 12 s, dentro do timeout de SQL de
  30 s (`214c545`). `cast-03` passou na avaliação.

### D4. `data` da resposta é o maior resultado, não o último

- **Problema:** depois do ranking, o modelo costuma rodar um `COUNT` de
  conferência. A API devolvia esse `COUNT` em `data`, e `fin-03` falhou na
  primeira execução real (`2f86822`).
- **Decisão:** `data` passa a ser o resultado com mais linhas; em empate,
  vale o mais recente.
- **Efeito:** `fin-03` passou a acertar, e o gráfico mostra o ranking em vez
  de uma contagem.

### D5. Consulta semântica sempre em inglês

- **Problema:** o modelo de embeddings (`all-MiniLM-L6-v2`) só entende inglês,
  e as sinopses do banco estão em inglês. Medido em 05/10/2026 (5 primeiros
  resultados, palavras-chave do tema conferidas pelo corretor do D13):

  | Consulta | Sinopses no tema |
  |---|---|
  | "viagem no tempo paradoxos temporais" | 1/5 |
  | "time travel paradox" | 5/5 |
  | "inteligência artificial que se rebela contra a humanidade" | 1/5 |
  | "artificial intelligence rebels against humanity" | 5/5 |

- **Decisão:** a descrição da tool `semantic_search_synopses` e o prompt de
  sistema mandam o modelo escrever a consulta em inglês.
- **Alternativa descartada:** trocar por um modelo de embeddings multilíngue.
  Isso exigiria regerar o índice, e a primeira geração levou 722 s nesta
  máquina. A instrução no prompt resolve o mesmo problema sem custo.
- **Efeito:** ainda não medido no agente real. A cota do dia acabou antes da
  nova rodada dos casos `hybrid-01` e `hybrid-02` (ver D11).

## Segurança

### D6. Guardrails em três camadas

- **Problema:** com só a validação por regex, um produto cartesiano com `LIMIT`
  apenas nas subconsultas rodava por mais de 20 s sem interrupção (`37f24ec`).
  A regex também bloqueava títulos como 'Create' e aceitava `LIMIT` dentro de
  uma string (`ea44dfb`).
- **Decisão:** são três camadas:
  1. `validate_sql` percorre o SQL ignorando strings e comentários e exige
     `LIMIT` no nível externo.
  2. `run_query` usa o authorizer do SQLite (só SELECT nas tabelas do
     catálogo; bloqueia `sqlite_master`, `pragma_*` e `load_extension`), tem
     timeout de 30 s e corta em 500 linhas.
  3. A conexão abre com `mode=ro`.
- **Efeito:** uma consulta que fuja do previsto é interrompida em no máximo
  30 s, e nenhuma camada sozinha precisa ser perfeita.

## Modelos e cota

### D7. Timeout de 20 s por chamada ao LLM

- **Problema:** sem timeout explícito, o SDK espera 600 s por chamada. Um
  modelo `:free` congestionado prendia a pergunta por minutos antes de passar
  ao próximo da cadeia (`f006b4f`).
- **Decisão:** `LLM_REQUEST_TIMEOUT_SECONDS = 20`. O timeout cai na mesma
  conversão para `ModelUnavailable` que já tratava 429 e 5xx.
- **Efeito:** a troca de modelo acontece em segundos, não em minutos.

### D8. Modelo aposentado (404) escala na cadeia

- **Problema:** `z-ai/glm-5.2:free` passou a ser pago no meio da avaliação. O
  404 derrubava a pergunta em vez de acionar o próximo modelo (`17817ae`).
- **Decisão:** `NotFoundError` entra nos erros de infraestrutura que escalam.
- **Efeito:** um modelo retirado custa uma chamada, não a pergunta.

### D9. Checagem da cadeia contra o catálogo do OpenRouter ao iniciar

- **Problema:** o D8 só descobre o modelo retirado quando uma pergunta real
  bate nele, gastando uma requisição da cota e o tempo do timeout. Em 05/10/2026
  o catálogo público tinha 464 modelos, e `qwen/qwen3.8-27b:free`, colocado na
  cadeia em `17817ae` um dia antes, já não estava entre os `:free` com suporte
  a tools.
- **Decisão:** ao iniciar, `app/model_catalog.py` consulta
  `GET /api/v1/models`, que é público e não consome cota. Saem da cadeia os
  modelos do OpenRouter ausentes do catálogo ou sem `tools` em
  `supported_parameters`. Se o catálogo não responder, ou se a checagem
  eliminaria todos os modelos, a cadeia configurada segue inteira: a checagem
  nunca deixa o agente sem modelo. `GET /models` mostra a cadeia efetiva.
  `OPENROUTER_MODELS` troca a lista sem mexer no código, e
  `MODEL_CATALOG_CHECK=off` desliga a checagem (a suíte de testes desliga, para
  não usar rede).
- **Efeito:** o qwen foi trocado no padrão por
  `nvidia/nemotron-3-super-120b-a12b:free`, que está no catálogo com suporte a
  tools. Esse modelo ainda não passou pela avaliação.

### D10. Groq como provedor reserva, no fim da cadeia

- **Problema:** a cota gratuita do OpenRouter é de 50 requisições por dia,
  somadas entre todos os modelos `:free`. Em 05/10/2026 ela acabou: as duas
  perguntas da nova rodada da avaliação receberam 429
  (`free-models-per-day`) nos 3 modelos da cadeia, com 6 chamadas por
  pergunta, e só voltam às 21h (horário de Brasília). Nenhum modelo da cadeia
  ajuda nesse cenário, porque a cota é da conta, não do modelo.
- **Decisão:** com `GROQ_API_KEY` no `.env`, os modelos de `GROQ_MODELS`
  (padrão `qwen/qwen3.8-27b`) entram depois dos `:free` do OpenRouter, com o
  prefixo `groq:`. O plano gratuito do Groq tem cota própria, separada da do
  OpenRouter. O 413 (requisição grande demais) também escala, já que repetir
  não muda o tamanho.
- **Erros de geração:** o Groq devolve 400 quando o modelo gera uma tool call
  malformada, nas formas `output_parse_failed` e `tool_use_failed`. A mesma
  chamada é repetida até 2 vezes antes de escalar. Sem esse tratamento, o 400
  subia como 500 na API.
- **Alternativas descartadas:**
  - Pôr o Groq em primeiro lugar: o enunciado sugere o OpenRouter, então o
    Groq entra só quando o OpenRouter não responde.
  - Usar `openai/gpt-oss-120b` como padrão: medido com uma chave real em
    05/10/2026, ele não fechou nenhuma pergunta. Depois do resultado da SQL,
    respondia vazio (4 vezes seguidas, de 18 a 38 s cada) ou com tool call
    malformada. Também falhou com `tool_choice="required"`, com
    `reasoning_effort="low"` e na versão `gpt-oss-20b`.
- **Efeito:** com a chave, "Quantos filmes foram lançados em 2019?" foi
  respondida pelo `qwen/qwen3.8-27b` no Groq em 2,4 s: 13.349 filmes, o mesmo
  número de um `COUNT(*)` direto no banco. Sem chave Groq, nada muda.

### D11. Schema linking desligável

- **Problema:** o schema linking custa exatamente 1 chamada a mais por
  pergunta, cerca de 40% sobre as 2,4 chamadas medidas sem ele.
- **Decisão:** `SCHEMA_LINKING=off` desliga a etapa (`74e9142`). O placar de
  18/18 foi medido com ela desligada.
- **Efeito:** o ganho de acerto do schema linking **não foi medido**. Só existe
  a execução sem ele.

## Avaliação

### D12. Correção por valores, não por nome de coluna

- **Problema:** o agente escolhe os próprios aliases. Dois diretores empatados
  em 9,1875 apareciam em ordem arbitrária, e `cast-02` falhou por isso
  (`2f86822`).
- **Decisão:** `eval/grading.py` procura os valores do gabarito em qualquer
  célula da linha do agente, tolera fração contra percentual e aceita qualquer
  ordem dentro de um grupo empatado.
- **Efeito:** as falhas de `fin-03` e `cast-02` na primeira passada eram
  defeitos reais, corrigidos antes do placar final. Nenhuma foi absorvida pelo
  corretor.

### D13. Veredito automático para os casos de busca semântica

- **Problema:** `hybrid-01` e `hybrid-02` não têm gabarito SQL, porque o
  "certo" é um conjunto aberto de filmes. Eram corrigidos à mão (`MANUAL`), e a
  revisão manual de 05/10 achou palpites fracos no fim das duas listas.
- **Decisão:** o orchestrator passa a registrar `tools_used` e os filmes que a
  busca devolveu (`semantic_hits`). O tipo de checagem `semantic` aprova
  quando três condições valem ao mesmo tempo:
  1. o agente chamou `semantic_search_synopses`;
  2. pelo menos 3 dos 5 primeiros filmes distintos têm uma palavra-chave do
     tema no título ou na sinopse (palavra inteira, plural aceito, sem
     acentos);
  3. a resposta cita pelo menos um desses filmes.
- **Limite conhecido:** é um proxy de precisão do tema, não de "rebelião". Um
  documentário sobre riscos da IA conta como relevante para `hybrid-02`.
- **Efeito:** o critério separa as consultas boas das ruins (tabela do D5:
  1/5 contra 5/5). A nova rodada no agente real ficou pendente pela cota (D10).
  `eval/results.md` ainda mostra os dois casos como `MANUAL`, da execução de
  05/10.

## Interface

### D14. Conversa salva no navegador, com tabela e CSV

- **Problema:** recarregar a página apagava a conversa, que só existia no DOM.
  O gráfico tinha um bug: em "nota média IMDb por ano", sem coluna de texto,
  usava o ano como rótulo e também como valor.
- **Decisão:**
  - A conversa (`session_id`, perguntas e respostas) fica no `localStorage`,
    limitada a 30 perguntas e 200 linhas por resposta. O botão "Nova conversa"
    gera outro `session_id`.
  - Séries por ano viram gráfico de linha, com até 200 pontos. Rankings
    continuam em barras, com até 25 linhas.
  - Cada resposta com dados ganha "ver tabela" (até 100 linhas na tela) e
    "baixar CSV" (todas as linhas).
- **Alternativa descartada:** persistir a memória no servidor. Isso exigiria
  armazenamento novo (hoje é RAM), e o enunciado não pede interface. Se o
  servidor reiniciar, o histórico continua visível, mas a pergunta seguinte
  não herda o contexto.
- **Efeito:** conferido no navegador com respostas do cache. O histórico volta
  depois de recarregar, a nova conversa limpa a tela, o erro 503 aparece e é
  salvo, e não há rolagem horizontal em 390 px.

## Entrega

### D15. CI com uma amostra do banco

- **Problema:** 61 dos 177 testes liam o `cinerocket.db` real (580 MB), que
  não cabe no GitHub. Sem o banco, essa parte da suíte falhava.
- **Decisão:** `scripts/build_sample_db.py` gera
  `tests/fixtures/cinerocket_sample.db` (3,9 MB), com o mesmo DDL e os mesmos
  índices do original. A amostra tem 610 filmes (os 60 mais populares com
  receita e orçamento, mais 550 pouco populares sem receita) e todas as linhas
  ligadas a eles. O CI roda com `DB_PATH` apontando para ela. Um teste que
  comparava com o número fixo 95.645 passou a comparar com um `COUNT(*)`.
- **Alternativa descartada:** marcar esses testes como "pula sem o banco". O
  CI ficaria verde sem testar guardrails, authorizer e gabaritos.
- **Efeito:** a suíte inteira passa nos dois bancos, real e amostra.

### D16. Empacotamento: `pyproject.toml`, Docker e versões fixadas

- **Decisão:** `pyproject.toml` declara as mesmas versões fixadas de
  `requirements.txt`, e `tests/test_packaging.py` falha se as duas listas
  divergirem. O `Dockerfile` instala o torch só para CPU antes do resto.
  `docker-compose.yml` monta `data/` (banco, cache e índice) e o cache do
  modelo de embeddings como volumes, e o contêiner roda com usuário sem
  privilégios.
- **Efeito:** o build da imagem não foi executado nesta máquina, porque o
  Docker Desktop estava parado. O job `docker` do CI faz o build a cada push.

## Fora de escopo

- **Conexão com o Databricks:** exigiria a infraestrutura de outra atividade.
- **Memória de conversa persistente no servidor:** ver D14.
