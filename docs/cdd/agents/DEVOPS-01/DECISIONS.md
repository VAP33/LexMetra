# DECISIONS — DEVOPS-01

## 2026-09-16 — OpenL compose uses profile `openl`
- Context: RULE-01 unblocked the service, but pulling a JVM image on every default `compose up` would break lightweight backend-only runs.
- Decision: `profiles: ["openl"]`. Start with `podman compose --profile openl up` (or docker compose).
- Why: default path stays Postgres+Redis+backend; OpenL is opt-in until cutover.
- Reversible? Yes — drop the profile key.

## 2026-09-16 — Archive target is `archive/pre-lexmetra`
- Context: ARCH-01 D-05. This checkout had no `DEPENDENCIES/` directory.
- Decision: document the move; do not invent an empty tree.
- Reversible? Yes.
