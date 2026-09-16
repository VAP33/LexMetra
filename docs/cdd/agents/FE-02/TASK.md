# CDD Package — FE-02 (Consumer Frontend)

(Verbatim from `CDD/Wave 3.1/FE-02.md`, copied here for persistent context.)

**Agent ID:** FE-02
**Depends on:** CON-01's Consumer Scan Response contract published.

**Purpose:** Build the public-facing surface for CON-01's scan feature and CON-02's complaint reporting — deliberately a **separate** frontend from the Inspector/Authority React app, not a new section of it.

**Why separate (make this explicit, don't just assume it):** the Inspector app is a professional tool behind login, built for people trained to interpret evidence detail. The Consumer surface needs to work for an anonymous member of the public on a phone, in a shop, deciding whether to trust a product — different audience, different information density, likely different auth model entirely (per CON-01's public-access decision). Bundling them risks compromising both.

**You must:**
1. **Recommended default (raise as a lightweight decision with ARCH-01, not a full blocking question):** build this as a Progressive Web App (PWA) — installable without an app store, camera access for scanning without a native app build, works reasonably offline for viewing past scan history. This fits a hackathon/demo timeline far better than native iOS/Android builds, and fits the "consumer scans a product in a shop" use case well.
2. Build the scan flow: camera capture → `POST /consumer/scan` (CON-01) → simplified verdict display, with the `disclaimer` field always visible, and `UNCERTAIN` states shown honestly (not glossed over) per the same invariant every other consumer of `ProductInspection` must respect.
3. Build the reporting flow: from a scan result, or standalone, submit to `POST /consumer/complaints` (CON-02) and show status (`SUBMITTED`, etc.) without exposing internal Authority notes.
4. Keep this visually and technically distinct from the Inspector React app — different repo folder (e.g. `frontend/consumer-app/`), can share a component library or design tokens with the Inspector app if convenient, but should not share auth/routing.

**You must NOT:**
- Fold this into `frontend/react-app/` — that's the Inspector/Authority surface (AUTH-01 extends it for exactly the opposite reason you're building separately here).
- Expose any Inspector/Authority-only data (raw evidence, other users' reports, case assignment) through this surface.

## CONTEXT.md

- `frontend/react-app/` is the Inspector/Authority app (React 18 + TypeScript + Tailwind + Vite) — a fine stack to reuse for this project too, just as a separate app instance, not a shared codebase with shared auth.
- CON-01's public-access decision (rate limiting, consumer identity approach) directly shapes what this frontend needs to handle (e.g. a CAPTCHA step, or a lightweight signup) — coordinate directly rather than guessing.

## CONTRACTS.md

**Contract you consume:** CON-01's Consumer Scan Response shape; CON-02's complaint-record contract and states.
**Contract you produce:** none new — you're the terminal consumer of this chain, not a contract producer for other agents.
