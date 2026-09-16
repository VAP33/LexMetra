# HANDOFF — DEVOPS-01
Prepared: 2026-09-16

## Summary for the next agent (or my future self)
CI is in-tree. OpenL is a compose profile, not a speculative always-on service. Env vars match `config.py` for OpenL, OCR languages, consumer scan, and FSSAI flags. DEPENDENCIES/ was not present to archive.

## What I own that is now stable (safe for others to depend on)
- `.github/workflows/pytest.yml`
- `docker-compose.yml` OpenL profile (`openltablets/ws:6.4.0`, repo-zip)
- `.env.example`

## What I own that is still in flux
- Whether `compose up --build` is green on this host
- Physical `DEPENDENCIES/` archive

## Contracts I changed
- Infra only. No frozen pipeline models.

## Open questions
- Should CI also start OpenL and run `test_openl_differential.py` unskipped? Not yet — remaining rules are not migrated.
