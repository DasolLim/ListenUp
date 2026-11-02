# ListenUp — frontend

Next.js 16 (App Router) + TypeScript + Tailwind v4. Setup, environment and the
full check loop are in the [root README](../README.md); UI work follows
[`docs/design/DESIGN_SYSTEM.md`](../docs/design/DESIGN_SYSTEM.md).

```bash
npm run dev        # http://localhost:3000
npm run check      # typecheck + lint + verify
npm run e2e        # Playwright: a11y, contrast, layout
```

| Folder | Holds |
|---|---|
| `app/` | Routes. `(marketing)` is the public site, `(app)` the signed-in tools. |
| `components/` | By feature (`captions`, `translate`, `speech`, `billing`, …). `shell/` is app chrome, `ui/` the design-system primitives. |
| `lib/` | Pure logic with no React import. Keep it flat: `scripts/lib/harness.mjs` loads these files in node by rewriting `@/lib/x` to a sibling file. |
| `lib/hooks/` | React hooks and `SpeechProvider`. |
| `scripts/` | Node checks run by `npm run verify`. |
| `e2e/` | Playwright browser checks. |

`proxy.ts`, `instrumentation*.ts` and the config files stay at this root because
Next.js looks for them here.
