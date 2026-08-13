---
name: risk-analysis
description: >-
  Conventions for this quant-risk repo — how to author knowledge docs in the
  house format, how the vector retrieval + domain tagging works, and how to
  extend the knowledge base or the agent. Use when adding/editing anything under
  knowledge/, or when working on the KnowledgeBase, VectorStore, or the agents.
---

# Risk-Analysis Repo Conventions

Guidance for working on the knowledge layer and agent in this project.

## Knowledge doc house style
Every file in `knowledge/<domain>/*.md` follows the SAME structure so retrieval
chunks are consistent (chunks are split on markdown headings):

```
# <Metric name> (<abbrev>)

## Definition
Plain-language: what it is and what question it answers.

## Formula (dry) | Method (dry)
The simplest defensible calculation. Keep it "dry" — no derivations.

## Data required
Numbered list. For EACH input, name the risk table it comes from in backticks:
`assets`, `historical_prices`, `portfolio_positions`, `counterparty_exposure`.
This is what lets the agent connect knowledge to data.

## Notes
Caveats, conventions (e.g. losses reported positive), and links to related docs.
```

Rules:
- Concise and accurate over exhaustive. One metric per file.
- Always include the **Data required** section naming the tables — it is load-
  bearing for the agent's "decide what data I need" step.
- File name = snake_case of the metric (`expected_shortfall.md`).

## Domains (desks)
Subfolder name IS the domain tag. Current desks:
`market_risk`, `xva`, `regulatory_capital`, `credit_risk`.
Adding a new desk = new subfolder + docs, then add it to `DOMAINS` in
`DOMAINS` in `backend/src/backend/knowledge/knowledge_base.py`.

## Retrieval
- `KnowledgeBase.retrieve(query, n_results=3, domain=None)` — semantic search,
  optional domain filter (`where={"domain": ...}`).
- Chunks carry metadata: `domain`, `source` (file stem), `heading`.
- Retrieval quality note: heavily-overlapping metrics (e.g. VaR vs ES) can rank
  close; scope with a `domain` for sharper results.

## After editing knowledge
Re-ingest so the vector store reflects the change:
```bash
python -c "import sys; sys.path.insert(0,'src'); from knowledge_base import KnowledgeBase; KnowledgeBase(rebuild=True)"
```
Then sanity-check with a couple of `retrieve()` calls (see the `__main__` block
in `backend/src/backend/knowledge/knowledge_base.py`).

## Swap seams — do not break them
- `KnowledgeBase` uses a **`VectorStore`** interface (`QdrantVectorStore` — embedded for dev, or a Docker Qdrant server via `QDRANT_URL`).
- Data tools use a **`DataProvider`** interface (mock now, MCP/DB later).
- The agent imports interfaces, never concrete engines.

## Model
Default `claude-opus-5` with adaptive thinking. Do not downgrade unasked.
