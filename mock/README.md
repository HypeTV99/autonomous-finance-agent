# Yire frontend redesign — interactive mock (preview only)

Preview-only mock for the `autonomous-finance-agent` frontend redesign.
Nothing here is wired to the backend; all data is fake and lives inside each page.

## Static mock (no build step)

Serve the `mock/` folder statically, e.g. `python -m http.server 8000 --directory mock`:

| Page | File | Mirrors backend route |
|---|---|---|
| Bills | `index.html` | `/`, `/dashboard` (`static/dag.html`) |
| Sellers | `sellers.html` | `/vendors` (`static/vendor_intel.html`) |
| Records | `records.html` | `/audit` (`static/auditor_suite.html`) |
| Controls | `controls.html` | new — no backend route yet |

Stack: Tailwind CDN + vanilla JS. Design: Stripe ledger theme
(indigo `#533afd`, 4px cards, pill buttons, Inter Tight, tabular numerals).

## React demo (Amicro components)

`react/` is a Vite + React + Tailwind v4 app rendering the real Amicro
`MonoRoundedSankeyChart`, `DownloadButton` (morph), and a `PipelineSteps` rail:

```sh
cd react
npm install
npm run dev -- --port 5174
```

Peers: `motion`, `lucide-react`. Note: the published
`@subhanhq/amicro` npm package (v1.0.1) ships no CLI, so `npx ... add ...`
cannot run — the two Amicro sources here were vendored from the Amicro
GitHub repo by hand (`src/components/amicro/`).
