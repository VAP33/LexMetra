# LexMetra Isolated Product Compliance Checking Engine

This project contains the isolated, deterministic rule evaluation engine for the Legal Metrology (Packaged Commodities) Rules, 2011 (LMPC).

## Features
- **Deterministic Evaluation**: Pure Python standard library implementation with zero third-party/database/network dependencies.
- **Kleene K3 Tri-State Logic**: Strict preservation of `TRUE`, `FALSE`, and `UNKNOWN`. Missing evidence is never converted into failure.
- **Canonical Product Facts Layer**: Bridges nested (`product.quantity.value`, `product.quantity.unit`) and flat representations with explicit presence semantics (`KNOWN`, `EXPLICITLY_ABSENT`, `UNKNOWN`).
- **Tabular Schedules Engine**: First Schedule (MPE), Second Schedule (Standard pack sizes), Third Schedule (SI units), Seventh Schedule (PDP numeral heights).
- **Audit & Provenance**: Full evaluation trace, statutory provision references, condition steps, and calculation records.

---

## Local Test UI Server

A lightweight, zero-dependency testing interface is provided to manually test and inspect the engine's evaluation pipeline in your browser.

### How to Run

From the project root:

```bash
python server.py 8080
```

Then open your browser to:
[http://localhost:8080/](http://localhost:8080/)

### What the UI Provides
1. **Product Input Form & Raw JSON Tab**:
   - Form fields for common canonical facts (name, manufacturer, net quantity, unit, MRP, USP, mfg date, consumer care, import status, exemption state).
   - Raw JSON editor for testing arbitrary product shapes.
2. **Preset Product Buttons**:
   - **Complete (PASS)**: Fully compliant retail commodity pack.
   - **Missing Qty (UNCERTAIN)**: Demonstrates that omitted fields produce `UNKNOWN` rather than `FAIL`.
   - **Absent Mfr (FAIL)**: Demonstrates explicit absence detection (`present=False`) leading to deterministic violation.
   - **Small Pack (EXEMPT)**: Demonstrates statutory exemption handling under Rule 26.
   - **Exemption (UNKNOWN)**: Demonstrates unresolved exemption uncertainty halting at `UNCERTAIN`.
   - **Imported (Origin Check)**: Demonstrates conditional rules triggered by import flags.
3. **Real Engine Outcome Banner**:
   - Displays actual overall status (`PASS`, `FAIL`, `UNKNOWN`, `EXEMPT`, `NOT_APPLICABLE`, `ENGINE_ERROR`) and engine rule count breakdown.
4. **Interactive Rule Results Table**:
   - Rule ID, Legal Provision, Applicability, Exemption Decision, Compliance Decision, Status, and Reason.
   - Filtering by status (`ALL`, `PASS`, `FAIL`, `UNKNOWN`, `EXEMPT`, `NOT_APPLICABLE`, `ENGINE_ERROR`).
5. **Detailed Inspection Panel (Click Any Rule)**:
   - Full statutory citation, effective version, explanation, cited evidence, confidence, provenance, and condition trace.
6. **Raw JSON & Clipboard Export**:
   - Formatted JSON output of the entire `EngineReport` with a "Copy JSON" button for audit inspection.

---

## Running Automated Tests

Run the complete test suite:

```bash
python backend/engine/tests/run_tests.py
```

All 117 tests execute in < 2 seconds.
