# Design decisions index

[中文](README.md)

An ADR (Architecture Decision Record) is one file per decision: **context** (the problem), **options** (with pros and cons), **decision**, **rationale**, and **consequences** (the cost accepted and when to revisit it).
Each row below is one ADR, so every trade-off fits in a 30-second read; click through for details. The ADRs themselves are written in Traditional Chinese.
All numbers come from synthetic data (the fictional Fab-X) and carry a sample size n and a source; decisions without a measurement state the design reason instead.

## Adopted decisions

| ADR | Decision | Chosen vs not chosen | Key evidence |
| --- | --- | --- | --- |
| [0001](0001-identity-injection.md) | How the user's identity reaches agent tools | MCP over HTTP with a short-lived JWT issued by FastAPI and verified at the MCP boundary vs identity in the framework's run config (same process), one MCP process per user | Design reason: if identity were a tool argument the LLM can fill in, a prompt injection could escalate privileges. On the injection test (n=11), all three systems blocked every privilege-read, role-spoofing and exfiltration case ([Phase 2 gate](../gates/phase-2.md)) |
| [0002](0002-permission-model.md) | Permission model | Clearance level + fab + department attributes vs plain RBAC, an external policy engine (OPA, Casbin) | Design reason: covers "enough clearance but wrong fab or department"; one pure function is the single source, the SQL condition is generated from it and a DB test asserts they agree. Agent tool path leaks 0/90 vs 58/90 for a baseline without the permission conditions ([Phase 2 gate](../gates/phase-2.md)) |
| [0003](0003-filtered-vector-search.md) | Combining permission filters with vector search | Apply the permission condition first, then exact search vs HNSW + iterative scan, partitioned indexes per fab or clearance | At 399 chunks retrieval takes about 250 ms per query ([ADR-0009](0009-chinese-lexical-retrieval.md)), so no ANN is needed; retrieval path leaks 0/30 vs 19/30 without the pre-filter ([experiments, 2026-11-09 leak tests](../experiments.md)) |
| [0004](0004-synthetic-data.md) | How synthetic documents are generated | Rule-based skeleton + templates, dirty data injected by rules vs fully LLM-generated; LLM polishing was built but not adopted | Polishing with qwen3:8b passed the fact check on only 100/192 documents, kept 0/26 typo markers and added Simplified Chinese to 8/100 ([experiments, 2026-11-08 polishing](../experiments.md)) |
| [0005](0005-answer-grading.md) | How answers are graded | Code matching for factual questions, an LLM judge only for open questions vs a cloud judge for everything, a local judge for everything | Ground-truth facts come from the skeleton, so code matching is free and reproducible; the open-question judge agreed with human labels on 50/50 questions (strict, n=50) at a total judge cost of US$0.134 ([experiments, 2026-11-10 judge calibration](../experiments.md)) |
| [0006](0006-agent-graph.md) | LangGraph structure of the agent | Custom StateGraph vs prebuilt ReAct agent, multi-agent supervisor | Design reason: approval, the 8-step cap and context trimming are visible, testable nodes; the fixed workflow reuses the same nodes, so the comparison differs only in who picks the next step. That makes a fair three-way test possible: RAG 4/15, fixed 15/15, agent 13/15 (n=15, [Phase 2 gate](../gates/phase-2.md)) |
| [0007](0007-trace-masking.md) | Trace masking | Strict masking (ids, clearance, hashes, lengths only) + a local debug mode vs masking by clearance level, relying on Langfuse access control | Log path leaks 0/30 vs 13/30 unmasked; Langfuse end to end: 12/12 events sent and read back, every field on the allow-list, 0 violations ([experiments, 2026-11-09 and 2026-11-11](../experiments.md)) |
| [0008](0008-model-selection.md) | Model selection | Claude Haiku 5.5 as the main model + a judge from another family (Gemini 3.6 Flash) + Qwen3 8B locally vs all Claude, all OpenAI or Gemini | Phase 3 test: RAG answer accuracy 0.743–0.781 across the three models (n=105), a small gap; agent Sonnet 15/15, Haiku 13/15, qwen3 4/15 (n=15), with Sonnet at 12× Haiku's cost per question ([experiments, 2026-11-11 model comparison](../experiments.md)) |
| [0009](0009-chinese-lexical-retrieval.md) | Chinese lexical retrieval | jieba + BM25 vs bge-m3 sparse | Fused with dense: Recall@5 0.861 vs 0.778 (dev n=54); codes such as tool ids and ticket numbers stay whole tokens |
| [0010](0010-sop-boost-for-disposal-questions.md) | Ranking for "how do I handle…" questions | Multiply SOP chunk scores by 1.2 vs fixed SOP/report quotas, expanding the whole SOP, leaving it to the agent | Disposal steps reach the context in 13/25 → 25/25 cases (quotas at best 23/25); open-question key-point hit rate 0.155 → 0.591 (calibration set, n=110 points, [experiments, 2026-11-10](../experiments.md)) |

## Measured and not adopted

| Approach | Result | Source |
| --- | --- | --- |
| Rerank (bge-reranker-v2-m3, CPU) | No recall gain: hybrid Recall@5 0.861 → 0.815 (dev n=54), about +25 s per query; confirmed not caused by 512-token truncation, and the conclusion held on handwritten questions | [experiments](../experiments.md), 2026-11-08 retrieval comparison, 2026-11-09 rerank re-checks |
| bge-m3 sparse as the lexical channel | Recall@5 0.778 fused with dense, below 0.861 for jieba + BM25 (dev n=54) | [ADR-0009](0009-chinese-lexical-retrieval.md) |
| One chunk per whole document | Answer accuracy 0.883 vs 0.850 (n=60): 2 more correct answers, within dev noise; section chunks give more precise citations | [experiments](../experiments.md), 2026-11-09 chunking |
| Expanding all SOP sections for disposal questions | Escalation conditions reached the context in 25/25 cases, yet key-point hit rate went 0.591 → 0.609 (n=110 points) and dev 0.600 → 0.467 (n=15 points), with +7% input tokens: no clear gain | [ADR-0010 addendum](0010-sop-boost-for-disposal-questions.md), [experiments](../experiments.md), 2026-11-10 |
| Replacing the fixed workflow with the agent | Test: fixed 15/15 vs agent 13/15 (n=15), within noise and the opposite direction from dev; the agent costs about 2.1× | [Phase 2 gate](../gates/phase-2.md) |

How the site design went from v8 to v9, and how I directed an AI and checked its work: [design case study](../case-study-design-lab.en.md).
