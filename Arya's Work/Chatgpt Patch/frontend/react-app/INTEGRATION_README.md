# Frontend integration — what's real, what your app shell still needs to provide

This replaces the mock data layer your `inspection-app.tsx` shipped with, with
real calls to the backend built earlier in this project. The visual design,
animations, and premium feel are untouched — I changed data plumbing and
added missing functionality, not the look.

**Verified, not just written**: every file in `src/lib/` and
`src/components/InspectionApp.tsx` type-checks cleanly (`tsc --noEmit`,
zero errors) against the real `lucide-react` and React type definitions —
I installed them and ran the compiler, this isn't a claim I'm making from
reading the code.

## Update — auth + real multi-surface capture (this revision)

Checked against the actual current backend (not the version this was
originally built against) and found two real gaps, now fixed:

### 1. Every endpoint except `/health` now requires a Bearer token
Confirmed by reading `main.py`: `/scan`, `/inspections`, `/sessions/*` — all
of it — now sits behind `Depends(auth.require_inspector)` or stricter.
Without auth, every single call in the previous revision of this file would
have 401'd. Added:
- `login()`, `register()`, token storage (`localStorage`), and automatic
  `Authorization: Bearer` header injection in `api-client.ts`'s `request()`.
- A real `LoginView` that gates the entire app — `InspectionApp` renders it
  instead of the dashboard when there's no stored token.
- 401 handling: any authenticated call that comes back 401 clears the
  session and drops the user back to login, instead of failing silently or
  looping.
- `ProfileView` now shows the real signed-in username/role and has a working
  sign-out button.

`/auth/login` uses FastAPI's `OAuth2PasswordRequestForm` — that's a real
backend constraint, not a style choice: it needs
`application/x-www-form-urlencoded` with fields named exactly `username`
and `password`, not JSON. `login()` sends it that way.

### 2. Real multi-surface capture sessions now exist — wired in
The previous revision captured multiple photos in the UI but only ever sent
the *first* one to `/scan`, discarding the rest as inert "supplementary
evidence" — an honestly-disclosed limitation at the time because no
multi-image endpoint existed. It does now (`POST /sessions`,
`POST /sessions/{id}/captures`, `POST /sessions/{id}/finalize`), confirmed
by reading the current backend. Replaced the workaround:
`runScanSession()` in `InspectionApp.tsx` now opens a session, uploads
every captured photo as its own surface (first = FRONT, second = BACK, rest
= SIDE), and finalizes once — the legal engine runs against the union of
every photo, not just the first.

Also added the `/scan`/session request fields the current backend accepts
that the original form didn't collect: `pdp_area_cm2`, `is_export_only`,
`retail_bundle_count`, `is_imported` (added to the `ScanDetails` type and
`createSession`'s request — not yet surfaced as extra form inputs in
`ScanDetailsView`, since most demo scans won't need them; add inputs there
if your demo products do).

**Verified the same way as before** — real `tsc --noEmit` against real
installed `lucide-react`/React types, zero errors, after every change above.
I did not run this against a live instance of your actual backend (still no
`package.json`/build scaffold in this handoff) — the request/response
shapes are transcribed exactly from reading the current `main.py`, not
assumed, but the literal browser-to-server round trip has still never fired.

## What I changed and why (original integration)

### 1. Real backend integration (`src/lib/api-client.ts`)
Replaces `mock-services.ts`. Every function does a real `fetch()` against
your FastAPI backend (`/scan`, `/inspections`, `/inspections/{id}`,
`/inspections/{id}/review`, `/products/{id}/history`, `/health`). Configure
the backend URL via `VITE_API_BASE_URL` (defaults to
`http://localhost:8000`, matching `SETUP.md`). Network failures and HTTP
errors both surface as a typed `ApiError` with a message the UI can show
directly — no more infinite spinners on a dead backend.

### 2. Real types (`src/lib/types.ts`) + adapter layer (`src/lib/adapters.ts`)
Your original `demo-data.ts` had 3 status values (COMPLIANT/VIOLATION/
UNCERTAIN). The real backend has 4 — **EXEMPT** (a product outside these
rules' scope entirely, e.g. an industrial-only sale) is a legitimate,
common outcome, not an error state. I added it everywhere: status badges,
filters, the declarations table, report copy, home-screen metrics. If your
design system has a specific color/icon intended for "exempt," swap
`statusStyles.EXEMPT` in `InspectionApp.tsx` — right now it reuses the
brand color.

`adapters.ts` is the one place that converts backend field names/shapes
into what the UI expects. If the backend contract changes, this is what
needs updating — not every component.

### 3. Auxiliary AI signals are no longer mixed into legal declarations
The rule engine emits some fields prefixed `__` (e.g.
`__possible_alteration__`) that are CV/AI signals, not real legal
declarations — mixing them into the "Extracted information" table would
misrepresent a heuristic sticker-detection guess as a legal finding. They're
filtered out of `declarations` and shown instead in a new **AI signals**
section on the result screen, explicitly labeled as advisory.

### 4. New: pre-scan details form (`ScanDetailsView`)
The real `/scan` endpoint needs product ID, sale type, category, net
quantity, and optionally MRP — the original mock flow never collected any
of this. Added a details screen between capture and processing, styled to
match the existing card/input patterns already in the file. This is a
missing-feature gap I filled, not a design change.

### 5. New: multi-photo capture
`ScanView` now lets you capture/upload more than one photo (front + back)
before continuing, with a thumbnail strip and per-photo remove. **Honest
caveat**: only the first photo is currently sent to `/scan` for compliance
analysis (that's what the backend endpoint accepts today — see
`handoff/01_capture_and_extraction.md` if a later session added true
multi-surface support, in which case `runScan()` in `InspectionApp.tsx` is
the one place to extend). Extra photos are captured in the UI and kept
client-side as supplementary evidence; they are not silently discarded, but
they're also not yet analyzed — the capture caption says exactly this.

### 6. Fixed a real bug class before it happened: evidence region positioning
The original `EvidenceView` used made-up percentage positions tied to fixed
mock data. The real backend's `bbox` is in **raw pixel coordinates** of the
original image. Converting pixel → percent requires the image's actual
natural dimensions, which you only know once the `<img>` has loaded. I wired
that via `onLoad`, so overlay markers land in the right place regardless of
photo resolution — this would have silently misplaced every marker if
ported over unchanged.

### 7. New: Review Queue
Backend has a real `review_required` concept (low-confidence OCR, sticker
suspicion, ambiguous exemption). Added a 5th nav destination surfacing
exactly this queue — it didn't exist in the original nav at all.

### 8. Real async processing with proper error handling
The original `ProcessingView` ran a fixed 3.5s animation, independent of
whatever the (mock) service was doing, then fired the "real" call after.
Now the step animation runs *concurrently* with the actual API call
(minimum 1.4s display so it never flashes by, but never blocks on a slow
network beyond what's real). A genuine network/API failure now shows a
proper error screen with retry — not a hang or a silent wrong result.

### 9. Report PDF: checked before offering it
`/inspections/{id}/report.pdf` may or may not exist depending on whether
that backend workstream has landed. The download button does a `HEAD`
check first and shows an honest "not available yet" state instead of
opening a broken link.

### 10. Removed fake padding numbers
The original home screen added `+8`/`+6`/`+1`/`+1` to every metric to make
the empty demo look populated. Now that the data is real, those are gone —
metrics are exactly what the backend returns, including zero when you
haven't scanned anything yet (with an honest empty state, not a lie).

## What I did NOT touch

- Every existing Tailwind class name, layout, spacing, and animation
  (`.scan-line`, `.breathe`, `.safe-bottom`, `.hide-scrollbar`) — these are
  referenced exactly as before. I don't have your `tailwind.config`/global
  CSS in this handoff, so I couldn't verify they're still defined — if this
  file lived in a project that had them, it still needs them.
- `@tanstack/react-router` — the original imported `useNavigate`/`Link` but
  never actually called either (confirmed by grep, not assumption); this
  app's real navigation is internal view-state, not router-driven. If your
  shell app wraps this in real routes, `InspectionApp` still works
  unchanged as a mounted component — nothing here assumes exclusive control
  of the URL.
- Any shadcn/ui or other design-system primitives your app shell might
  provide via `@/components/ui/*` — this file was self-contained (its own
  `Button`, etc.) in the version you gave me, so I kept it that way.

## What you still need to supply

1. The rest of your Vite/React project scaffold (this handoff is 5 files:
   4 in `src/lib/`, 1 in `src/components/`) — `package.json`, Tailwind
   config, global CSS with the custom classes referenced above, and
   whatever mounts `<InspectionApp />`.
2. `VITE_API_BASE_URL` pointed at wherever your backend actually runs for
   the demo (localhost for a live demo, or a deployed URL).
3. A decision on `ScanDetailsView`'s category/unit dropdown options — I
   used a reasonable default list; narrow it to what your actual demo
   products need.

## Files in this handoff

```
frontend/react-app/
├── tsconfig.json                    # verified config used for the type-check
└── src/
    ├── lib/
    │   ├── types.ts                 # Inspection/Declaration types + EXEMPT status
    │   ├── api-client.ts            # real fetch calls to the FastAPI backend
    │   ├── adapters.ts              # backend response -> UI Inspection shape
    │   └── data-url.ts              # captured photo -> Blob for upload
    └── components/
        └── InspectionApp.tsx        # the integrated app (was inspection-app.tsx)
```
