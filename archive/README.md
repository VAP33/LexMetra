# Archive / pre-LexMetra snapshot

ARCH-01 classified the entire `DEPENDENCIES/` tree as NON-CORE
(`docs/cdd/02-DEPENDENCIES-CLASSIFICATION.md`). DEVOPS-01 archives it here
rather than deleting it.

**This working tree (2026-09-16):** `DEPENDENCIES/` was not present at the
repository root when DEVOPS-01 ran (`ls DEPENDENCIES` → no such file). If it
reappears in a checkout that still has it, move it with:

```bash
mkdir -p archive
mv DEPENDENCIES archive/pre-lexmetra
```

Do not `rm -rf`. The 38 MB zip `archives/LMPC_current.zip` stays with the
snapshot if present.

Dataset paths: real images live at `dataset/images dataset/` and
`dataset/real images/`, not under `DEPENDENCIES/`.
