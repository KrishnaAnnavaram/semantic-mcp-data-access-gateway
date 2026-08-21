# frontend/ — SMCP Gateway UI

React + TypeScript + Tailwind, replacing the earlier Streamlit app. This is
the only thing a human sees, and it talks to the backend over exactly one
contract:

```
POST /chat       {query, session_id}
  -> {answer, sources, trace, awaiting_clarification, elicitation, route,
      tables, data_plan, negotiation, catalogue, calculation, langsmith_url}
POST /summarise   {messages} -> {title}
GET  /health
```

Do not add a second channel to the backend, and do not reach past `/chat`
into a provider or the MCP layer — the frontend is thin on purpose. See
`backend/src/backend/api/service.py` for the authoritative shape; keep
`src/types/chat.ts` in lockstep with it.

## Structure

```
src/
  api/client.ts        REST + mock transport, one AgentClientError type
  config.ts             reads VITE_-prefixed env vars
  types/chat.ts          mirrors ChatResponse exactly
  store/chatStore.ts     zustand — chats, activeChatId, openArtifact
  hooks/useSend.ts        send/regenerate/auto-title orchestration
  lib/                    pure, tested logic (elicitation dedupe, artifact summary)
  components/             Header, Sidebar, ChatWindow, MessageBubble,
                          ElicitationPrompt, ArtifactCard, ArtifactPanel, ...
```

`lib/` holds anything worth unit-testing without mounting a component.
`App.test.tsx` is the smoke test — it mounts the whole tree in mock mode and
drives it through sending a question, opening a new chat, and switching back.
Prefer extending that test over adding a parallel one when the change touches
how components compose, not just a pure function.

## Configuration traps that cost an afternoon each

- **`VITE_AGENT_BACKEND=rest` must be set** in `frontend/.env`, or the UI
  silently serves canned mock answers forever. It looks like a working app
  giving wrong numbers, which is worse than an error. The header shows a
  "Mock backend" badge when this is the case — check it before debugging
  anything else.
- **Raise `VITE_AGENT_TIMEOUT_SECONDS`.** One turn runs several MCP round
  trips behind an Opus loop; a short timeout expires mid-answer.
- **CORS.** The backend must list this app's origin in `CORS_ALLOWED_ORIGINS`
  (see root `.env.example`) — defaults already cover Vite's `:5173`. Without
  it the browser blocks the response even though the request reached the
  service; this looks identical to a network failure in the browser console.
- Vite only exposes env vars prefixed `VITE_` to client code. An unprefixed
  var in `.env` is silently invisible to `import.meta.env`.

## Rendering rules

- **Never present synthetic data as real.** The demo book arrives labelled
  `SYNTHETIC_DEMO` and the curve `REAL_MARKET_DATA`. Both labels must be
  visible in the UI (the `ArtifactCard`/`ArtifactPanel` badges), not stripped
  for tidiness.
- **Show the quoting basis** wherever a rate is displayed — the Source tab
  renders it from `table.provenance.quote_basis`. A bill discount rate and a
  par yield look identical on a chart and are different quantities.
- **A clarifying question is a first-class state**, not an error. When
  `awaiting_clarification` is set, `ElicitationPrompt` renders the question
  and the same `session_id` (the chat's own id) carries into the next turn.
- The Data plan and Discussion tabs are the project's claim to being
  auditable — keep citations and the domain-expert/mcp-agent negotiation
  visible, not collapsed away for cleanliness.
- Charts, if added, follow the `dataviz` skill: read it before writing chart
  code.

## Run and test

```bash
cd frontend
npm install
npm run dev            # :5173
npm test                # vitest, run once
npm run build            # tsc -b && vite build
```

The backend must be up first (`python -m backend.api.service`). If the UI
shows answers while `/health` is failing, you are looking at the mock
backend — check `VITE_AGENT_BACKEND` before debugging anything else.

Report what you actually ran. If a check fails, say so with its output.
