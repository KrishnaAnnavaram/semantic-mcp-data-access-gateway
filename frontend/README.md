# Vantage

Semantic Financial Data & Risk Intelligence — the React frontend for the
semantic-mcp-data-access-gateway. Grounded answers on U.S. Treasury rates,
every figure cited. Replaces the earlier Streamlit app; talks to the FastAPI
backend over the same `/chat` contract.

## Run

```bash
npm install
cp .env.example .env     # defaults to mock mode
npm run dev              # http://localhost:5173
```

Set `VITE_AGENT_BACKEND=rest` in `.env` to talk to the real backend
(`python -m backend.api.service`, on `:8000` by default). The backend also
needs this app's origin in `CORS_ALLOWED_ORIGINS` — see the root
`.env.example`; the default already covers `http://localhost:5173`.

## Test and build

```bash
npm test          # vitest — pure logic + a full-app smoke test, run once
npm run build      # type-checks (tsc -b) then produces dist/
npm run preview     # serve the production build locally
```

## Stack

Vite + React 18 + TypeScript, Tailwind CSS, Zustand for chat/session state,
`react-markdown` + `remark-gfm` for answer rendering, Lucide icons. See
`CLAUDE.md` in this directory for the project conventions and the
configuration traps worth knowing before you debug a blank/mock UI.
