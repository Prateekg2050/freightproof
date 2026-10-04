# Architecture

```text
RAW    -> what each source system actually reported (immutable evidence)
CORE   -> canonical entities, source-to-canonical mappings, inventory claims, orders
TRUST  -> business definitions, trust contracts, evaluations, evidence
APP    -> views used by the application and agent
```

Planned:
- `SEMANTIC`: Snowflake Semantic View (shared entities, relationships, metrics)
- Agent layer: Cortex Agent that uses trust status before answering
- UI: Streamlit app

## Trust statuses
`VERIFIED`, `CONFLICTED`, `STALE`, `INSUFFICIENT_EVIDENCE`, `UNMAPPED`, `ERROR`

## Core rule
If the data behind a decision is not `VERIFIED`, the system must not present it as fact. It reports the conflict and the exact source records instead.
