# CORTEX Phase A2 — Memory Foundation

**Completed:** Early build
**Tests:** Covered by holistic test suite
**Technical depth:** [phase_a2_architecture.md](usr/knowledge/cortex_main/main/phase_a2_architecture.md)

---

## What Phase A2 Built

Phase A2 is the local memory layer — the foundation that exists before the cloud consciousness (Phase B). Everything here persists across sessions without requiring external services. CORTEX can function with zero internet connectivity using only A2 capabilities.

### 1. L1 Memory: FAISS (Agent Zero built-in, extended)

Agent Zero ships with FAISS vector storage built in. CORTEX extends it:
- **Per-session entity recall** — entities and facts extracted by `cortex_knowledge_extractor.py` (Phase A1) are stored in FAISS via Agent Zero's `_50_memorize_fragments.py` and `_51_memorize_solutions.py` extension hooks
- **Fast recall at message loop start** — `_15_temporal_memory.py` pulls relevant FAISS memories for each new message and injects them as context
- **<10ms lookup** — local vectors, no network latency

### 2. JSON Persistence Layer

All Phase A1 behavioral models persist to JSON in `usr/memory/cortex_main/`:

| File | Module | Contents |
|------|--------|----------|
| `cortex_trust.json` | TrustEngine | 6-domain trust scores |
| `cortex_personality.json` | PersonalityModel | 6-dimension model + observations |
| `cortex_commitments.json` | CommitmentTracker | Active + completed commitments |
| `cortex_self_model.json` | CortexSelfModel | Capability registry, knowledge map, learning trajectory |

All use the same pattern: `load(agent)` reads on startup, `save(agent)` writes after each update. Errors never crash the agent — if the file is corrupt or missing, a default instance is returned.

### 3. Self-Model

`cortex_self_model.py` — CORTEX's structured model of its own capabilities.

| Section | Contents |
|---------|---------|
| `capability_registry.tools` | Per-tool: confidence, last_used, success_rate, uses |
| `capability_registry.knowledge_domains` | Domains and coverage depth |
| `knowledge_map` | FAISS entity count, SurfSense doc count, spaces populated, ventures tracked, last topics |
| `knowledge_gaps` | Identified gaps from struggle_detect |
| `learning_trajectory` | Session count, growth rate, personality stability, trust trend |
| `performance_history` | Approaches that worked/failed, calibration score |

Self-model is loaded at `monologue_start/_05_self_model_load.py` and injected as context. CORTEX reads it to understand what it currently knows and doesn't know — prerequisite for Phase G self-improvement reasoning.

### 4. Knowledge Base — CORTEX Self-Reads

`usr/knowledge/cortex_main/main/` — markdown files CORTEX reads during `monologue_start` via the Tier 0 index. This is where:
- Tool registries live (`tools/tool_registry_core.md`, etc.)
- Venture pack definitions live
- Architecture files live (the files in this series)
- Decision logs are referenced

The knowledge base is CORTEX's long-term structured knowledge. It differs from memory (dynamic, per-session) — the knowledge base contains stable architectural facts that CORTEX should always have access to.

### 5. Memory Injection Extensions

| Extension | Hook | Purpose |
|-----------|------|---------|
| `monologue_start/_05_self_model_load.py` | `monologue_start` | Load self-model + knowledge index |
| `message_loop_prompts_after/_15_temporal_memory.py` | `message_loop_prompts_after` | FAISS recall — inject relevant entities/facts |
| `agent_init/_20_cortex_memory_sync.py` | `agent_init` | Sync memory state on agent initialization |

---

## Key Design Decisions

| Decision | What was decided | Why |
|----------|-----------------|-----|
| JSON not SQLite for behavioral state | Simple, human-readable, directly inspectable | These are small single-value stores; SQL overhead unwarranted |
| FAISS via Agent Zero built-in | Don't rebuild what's already there | D-001 compliance; FAISS is well-integrated |
| Self-model as structured JSON | Explicit capability registry over implicit assumptions | Phase G requires structured access to what CORTEX knows/doesn't know |
| Knowledge base in `usr/knowledge/` | Separate from memory (dynamic) | Facts vs. experience — different access patterns |
| Error-silent loads | `try/except → return default` everywhere | Memory failures must never crash the agent loop |

---

## Relationship to Phase B

Phase A2 is local-only memory. Phase B (SurfSense + Graphiti) extends this to cloud consciousness. A2 works without B; B adds cross-device access, temporal graph, and semantic search across sessions. The two layers are independent — A2 memory doesn't require B to function.
