# CORTEX — Vision & Discovery Brief

## How to Use This Document

**This is NOT a "go build" instruction.** This is the beginning of an iterative discovery process. Your job is to:

1. **Analyze** all codebases and repositories listed below — deeply, not surface-level
2. **Explain back to me** what you understand the vision to be
3. **Ask questions** — anything unclear, any assumptions you're making, any gaps you see
4. **Suggest improvements** — based on what you find in the repos, propose capabilities, architectures, integrations I haven't thought of
5. **Iterate** — we go back and forth until the vision is crystal clear and the implementation plan is optimal
6. **Only then** do we build — and we build in phases, validating each one

Do NOT start coding until we've completed the discovery process. I want your genuine analysis, not just execution of orders.

---

## 1. The Vision — What We're Building

### The One-Line Version
A single, unified AI system that serves as an autonomous business partner, venture factory, knowledge engine, and operational workspace — with the personality and aliveness of a real partner, not an assistant.

### The Full Vision

I want to build what I'm calling **CORTEX** — the fusion of multiple AI subsystems into one coherent, "alive"-feeling intelligence. Think of it as an AI that:

**Knows me.** It remembers every conversation, every decision, every preference. It tracks how facts change over time. It understands the context behind my questions because it has a persistent, evolving model of me, my businesses, my goals, and my thinking patterns.

**Runs my businesses.** Not "advises me about" — actually runs them. Each venture I create has its own DNA profile, its own integrations (Google, Gmail, Sheets, Etsy, whatever the venture needs), its own research, its own optimization loops. Ventures range wildly — affiliate marketing, digital art, SaaS products, cold email campaigns, data transformation, automation services. Each needs different tools, different strategies, different APIs. The system adapts to each venture's needs.

**Finds new opportunities.** It scans, researches, discovers new venture opportunities. It asks the right questions during venture creation (not a form — a deep, intelligent conversation). It understands underlying themes, market dynamics, competitive landscapes. It does deep research — not just web search, but genuine multi-source intelligence gathering.

**Acts autonomously.** It makes commitments and keeps them. It schedules tasks. It runs background jobs. It proactively surfaces relevant information when I need it (not just when I ask). It has authority levels — some things it does on its own, some things it asks permission for.

**Learns and self-optimizes.** It improves its own strategies, prompts, and decision-making based on outcomes. When it encounters a task it can't handle, it finds or builds the capability. It has meta-cognitive awareness — it knows what it knows, what it doesn't know, and what it needs to learn. Push the boundary here — propose what's achievable in terms of self-learning, self-improvement, tool creation, and autonomous capability expansion. I want maximum capability.

**Has a consciousness layer.** Not simulated — functional. Through deep integration with SurfSense, everything I see, read, research, discuss, and decide flows into a persistent knowledge layer. This is bidirectional: the system pushes knowledge INTO this layer (every conversation, every research finding, every venture decision), and the layer feeds relevant context BACK into every interaction. It's a persistent subconscious that makes the system genuinely aware. An additional idea worth exploring: can this consciousness layer proactively surface relevant information without being asked? (This needs careful cost management — it shouldn't burn money on unnecessary processing, but the value could be immense if done right.)

**Has a beautiful, comprehensive UI.** The current Jarvis UI is an excellent reference — 13 functional tabs covering Dashboard, Chat, Goals, Workflows, Agents, Tasks, Authority, Memory, Pipeline, Calendar, Knowledge, Command, and Awareness. Plus settings with LLM configuration, integrations, channels. I will provide screenshots of every tab. The UI should be at least as good as Jarvis's, potentially better with additional SurfSense integration panels and OMNIS venture management panels.

**Is commercially viable.** This is for me first — running my actual businesses. But the end goal is a product I can sell. This means: no restrictive licenses in the stack (MIT and Apache 2.0 only), deployable architecture (likely fly.io initially), multi-tenant capable eventually. Everything must be commercially free and clear.

**Is extensible.** When a valuable new open-source tool, repository, or API emerges, I want to be able to integrate it. The architecture should support adding new capabilities without rebuilding the core. Think plugin architecture, tool registration, modular agents.

---

## 2. Existing Codebases (Local — Analyze These First)

These are on disk at `C:\Users\Admin\CORTEX-Ruflo\`. This is a copy of the working codebase. Analyze them deeply — understand the architecture, the patterns, what works, what doesn't, what's mature, what's placeholder.

### 2a. OMNIS — The Business Brain

**Location**: `C:\Users\Admin\CORTEX-Ruflo\omnis_ai\`

**What it is**: A Python/FastAPI-based autonomous business intelligence and venture management system. This is the core product — the part that actually runs businesses, creates ventures, manages HITL workflows, tracks revenue/costs, does research.

**Key areas to analyze**:
- `omnis_ai/core/agent_graph.py` — LangGraph StateGraph orchestrator (already uses LangGraph!)
- `omnis_ai/core/identity.py` — System prompt / persona definition ("the COO who happens to be AI")
- `omnis_ai/core/agent_bridge.py` — Current LLM bridge (Claude Agent SDK + direct Anthropic fallback)
- `omnis_ai/core/model_router.py` — Multi-provider LLM routing
- `omnis_ai/core/surfsense/` — SurfSense integration (client, ingestor, knowledge builder, stream processor)
- `omnis_ai/core/neo4j_checkpoint_saver.py` — Neo4j-based checkpoint saver (Neo4j already integrated!)
- `omnis_ai/core/omnis_tools.py` — Tools exposed to the LLM
- `omnis_ai/core/meta_cognitive.py` — Meta-cognitive processing
- `omnis_ai/core/self_model.py` — Self-model tracking
- `omnis_ai/venture/` — **The entire venture system**: VentureDNA, creation flow, discovery, research engine, knowledge store, feedback loops, self-optimizer, tool creator, epistemic idle loop, parallel executor, scheduler, always-on jobs
- `omnis_ai/core/skill_engine/` — Skill/plugin system (context injector, hook engine, plugin loader, skill router, subagent pool)
- `omnis_ai/core/execution/` — Execution engine with kill switch and recovery
- `omnis_ai/core/expert_minds/` — Expert framework cards (30 frameworks) for venture creation
- `omnis_ai/modules/` — Kelly criterion, B2B policy, ROI router, anomaly detection, and more
- `omnis_ai/server.py` — FastAPI backend
- `BUILD_STATE.yaml` — Current build state (1065/1100 tests passing, 5 phases complete)
- `requirements.txt` — Current Python dependencies

**Important context**: This code is REAL and tested. 1065 contract tests pass. Hardening gate complete. But I'm open to you evaluating it fresh — if you find a fundamentally better approach to any part, propose it. Don't preserve code just because it exists.

### 2b. Jarvis Reference — The "Alive" Personality Reference

**Location**: `C:\Users\Admin\CORTEX-Ruflo\jarvis_reference\src\`

**What it is**: The complete source code of Jarvis (@usejarvis/brain), a Node.js/TypeScript AI assistant. **Licensed under RSALv2** — this means we can read, study, and learn from it, but we CANNOT copy code or use it in production. We extract PATTERNS and LOGIC, then implement equivalent (or better) functionality in Python.

**Why it matters**: Jarvis is the closest thing to the "alive" feeling I want. It has personality learning, knowledge extraction, prompt assembly, commitment execution, multi-agent orchestration, a beautiful UI. The patterns in this code are the blueprint for what CORTEX should feel like.

**Key files to analyze for patterns** (NOT to copy):
- `agents/orchestrator.ts` — Agent loop, tool iteration, model routing, authority system
- `vault/extractor.ts` — Knowledge extraction prompt (entities, facts, relationships, commitments)
- `vault/retrieval.ts` — Memory query engine (search terms, entity profiles, context formatting)
- `personality/learner.ts` — Keyword-based personality signal extraction
- `personality/model.ts` — Personality model (verbosity, formality, humor, trust, emoji, format preferences)
- `roles/prompt-builder.ts` — Section-ordered prompt assembly (Identity > Responsibilities > Style > KPIs > Tools > Authority > Knowledge Context > Commitments > Goals)
- `daemon/commitment-executor.ts` — Three-mode commitment system (passive/moderate/aggressive cancel windows)
- `authority/` — Permission and authority hierarchy
- `goals/` — Goal tracking with accountability
- `workflows/` — Visual workflow engine with 30+ node types
- `comms/` — Multi-channel communication (WebSocket, Telegram, Discord, Signal, WhatsApp, voice)
- `awareness/` — Screen capture, OCR, context tracking, struggle detection, suggestion engine
- `observers/` — Calendar, clipboard, email, file watcher, notification, process observers
- `sidecar/` — External process management (MCP servers, etc.)

**Legal constraint**: Treat this as a reference architecture. Extract the patterns, understand the "why," then build your own implementation. Zero Jarvis code in the final product.

### 2c. Jarvis Integration Layer

**Location**: `C:\Users\Admin\CORTEX-Ruflo\jarvis_integration\`

**What it is**: The bridge between OMNIS and Jarvis — patches, tools, UI injections, workflows. This shows how the two systems currently communicate.

**Key files**:
- `tools/omnis-bridge.ts` — 19 bridge tools (HTTP calls from Jarvis to OMNIS)
- `patches/` — Patched Jarvis files (shows what was customized)
- `ui-injection/` — OMNIS panels injected into Jarvis UI
- `workflows/` — OMNIS-specific Jarvis workflows (HITL reminders, Kelly monitor, morning brief, opportunity scan)
- `config.yaml` — Jarvis configuration for OMNIS

### 2d. Existing OMNIS Dashboard

**Location**: `C:\Users\Admin\CORTEX-Ruflo\omnis-dashboard\`

**What it is**: A Next.js dashboard (partially built). Analyze it to understand what UI work exists.

---

## 3. Open-Source Repositories to Analyze

These are the key open-source projects that could serve as building blocks. Analyze each one for: what it does, how it's architected, what license it uses, and how (or whether) it fits into the CORTEX vision. **You don't need to use all of them.** Some may be redundant. Some may be better than what we planned. Your job is to evaluate.

### Core Architecture Candidates

**LangGraph** — https://github.com/langchain-ai/langgraph
- MIT License. Agent orchestration framework (state machines, tool routing, checkpointing, human-in-the-loop)
- OMNIS already uses LangGraph. SurfSense uses LangGraph internally. Likely the orchestration backbone — but evaluate whether this is optimal or if there's a better approach
- Analyze: StateGraph patterns, AsyncPostgresSaver, tool integration, streaming, multi-agent patterns

**Graphiti** — https://github.com/getzep/graphiti
- Apache 2.0. Temporal knowledge graph built on Neo4j
- Key capability: tracks how facts CHANGE over time. Auto-extracts entities/facts/relationships from conversations
- Has official LangGraph integration. Has MCP server
- OMNIS already has Neo4j. Graphiti would add a structured knowledge layer on top
- Analyze: episode ingestion, semantic search, temporal queries, ontology (prescribed vs learned), community detection

**SurfSense** — https://github.com/MODSetter/SurfSense
- Apache 2.0. AI-powered research and knowledge management
- Already deployed in the current system. The consciousness/retrieval layer
- Analyze: architecture, how it stores knowledge, how retrieval works, how to optimize the bidirectional flow, whether the existing integration in `omnis_ai/core/surfsense/` is optimal

**Mem0** — https://github.com/mem0ai/mem0
- Apache 2.0. Memory layer for AI agents (short-term and long-term)
- Potentially useful for lightweight personality/preference memory (complementing Graphiti's heavier knowledge graph)
- Analyze: how it compares to Graphiti for different memory needs, whether it adds value or is redundant given Graphiti + SurfSense

### Additional Repositories to Evaluate

**Jarvis (vierisid)** — https://github.com/vierisid/jarvis?tab=readme-ov-file
- The upstream Jarvis project. RSALv2 licensed. Reference only
- Compare against the local `jarvis_reference/` to understand if there are newer features
- Analyze: architecture patterns, what makes it "alive," what we want to replicate in Python

**CLI-Anything (HKUDS)** — https://github.com/HKUDS/CLI-Anything
- Evaluate for: command-line agent capabilities, how it handles arbitrary CLI tasks, whether the patterns are useful for CORTEX's Command tab or autonomous tool execution

**AutoResearch (Karpathy)** — https://github.com/karpathy/autoresearch
- Evaluate for: deep research patterns, how it structures multi-source research, whether it improves on OMNIS's existing research engine

**UI/UX Pro Max Skill** — https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
- Evaluate for: UI/UX patterns and best practices for building the CORTEX dashboard

**Awesome MCP Servers** — https://github.com/punkpeye/awesome-mcp-servers
- Not a codebase to integrate — a directory of MCP servers. Evaluate for: which MCP integrations would be most valuable for CORTEX (Gmail, Google Calendar, Slack, GitHub, Notion, etc.)
- OMNIS already has MCP support (`omnis_ai/core/mcp/`)

**Ruflo** — https://github.com/ruvnet/ruflo
- MIT licensed. 60+ specialized agents, hive-mind coordination, self-learning memory
- Analyze honestly: are there patterns that should be incorporated into CORTEX? Agent coordination patterns? Self-learning memory patterns? The HNSW vector memory? Stream-JSON chaining?
- Note: Ruflo is Node.js, not Python. Evaluate whether patterns can be ported, not whether code can be reused directly

**Additional repositories**: You should also search for and suggest other open-source projects that could enhance CORTEX. I'm open to anything that adds genuine capability. The only hard requirement is commercially-friendly licensing (MIT, Apache 2.0, BSD).

---

## 4. Key Constraints & Principles

### Hard Requirements
- **Zero RSALv2 in production** — no Jarvis code running. Patterns extracted, own code written
- **Commercially viable licensing** — MIT, Apache 2.0, BSD, or our own code. No AGPL, no Sustainable Use License, no RSAL
- **Python-first runtime** — single runtime, no Node.js/Python bridge friction. The UI can be JavaScript (React), but the backend is Python
- **Deployable** — must work locally (Windows + Docker) and on fly.io for cloud deployment
- **Cost-conscious** — smart model routing (premium models for reasoning, cheap/free models for tool loops, vision models for images). Don't burn money on unnecessary LLM calls
- **Safety** — the current system must keep working while we build the new one. No destructive changes to existing code

### Soft Preferences (challenge these if you have better ideas)
- LangGraph for orchestration (OMNIS already uses it, but if you find something strictly better, propose it)
- Neo4j + Graphiti for knowledge graph (Neo4j already in the stack)
- PostgreSQL + pgvector for state/embeddings (SurfSense already uses this)
- React + Vite for UI (matching Jarvis for familiarity)
- FastAPI for backend (OMNIS already uses it)

### Open Questions (for you to help answer)
- What's the optimal layering of memory systems? (Graphiti vs Mem0 vs SurfSense — complementary? redundant?)
- How should the consciousness layer (SurfSense) be deeply integrated vs. shallowly queried?
- What's the best approach for self-learning and self-optimization?
- How modular should ventures be? (Each venture as its own agent? Its own tool set? Its own sub-graph?)
- What's the right authority/autonomy model for different operation types?
- How should proactive information surfacing work without incurring unnecessary costs?
- What additional open-source repos should we evaluate?
- How do we make the system genuinely extensible for future capabilities?

---

## 5. The UI Vision

Jarvis's UI is the reference. I will provide screenshots of all 13 tabs. The system should have at minimum these functional areas:

- **Dashboard** — Overview of everything: agent activity, active ventures, goals, recent decisions
- **Chat** — The primary conversational interface with streaming responses
- **Goals** — Goal tracking, accountability, progress
- **Workflows** — Visual workflow editor (think node-based canvas)
- **Agents** — Multi-agent monitoring and management
- **Tasks** — Task queue, execution status, scheduling
- **Authority** — Permission hierarchy, what the system can do autonomously vs needs approval
- **Memory** — Knowledge graph visualization, what the system remembers and how
- **Pipeline** — Content pipeline management
- **Calendar** — Task and content scheduling
- **Knowledge** — Knowledge base browsing and search (Graphiti + SurfSense)
- **Command** — Direct command interface
- **Awareness** — Context monitoring (currently conceptual — evaluate what's achievable)
- **Settings** — LLM config, API keys, integrations, preferences
- **OMNIS Panels** — Venture management, Ledger, MCP integrations (partially built)

Additional: SurfSense integration panels (search, knowledge browsing, consciousness status).

---

## 6. About the Ventures (OMNIS's Core Value)

Each venture is fundamentally different. Examples of what ventures look like:

- An **Etsy store** — needs Etsy API integration, product research, SEO optimization, listing automation, sales tracking
- An **affiliate marketing site** — needs content generation, SEO, link tracking, revenue optimization
- A **SaaS product** — needs user analytics, feature development, customer support automation
- A **cold email campaign** — needs lead generation, email sequences, CRM integration, response tracking
- A **digital art business** — needs art generation pipelines, marketplace listing, pricing optimization
- **Data transformation services** — needs API integrations, data pipeline automation, quality monitoring

Each venture has:
- **Its own DNA** — a profile that captures everything about it (market, competition, strategy, performance, learnings)
- **Its own integrations** — API keys, OAuth tokens, service connections specific to that venture
- **Its own research** — ongoing market research, competitor monitoring, opportunity scanning
- **Its own optimization loops** — what's working, what's not, how to improve
- **Its own tools** — custom tools created specifically for that venture's needs

The venture creation process should be **intelligent and conversational** — not a form. The system asks the right questions, does deep research, identifies opportunities and risks, suggests strategies, and builds the venture DNA through genuine dialogue. Every possible information type can be fed into it (documents, URLs, data, screenshots, voice).

---

## 7. Your Discovery Process

### Step 1: Deep Analysis
Analyze all local codebases and open-source repositories listed above. Understand:
- What exists and works in OMNIS
- What patterns Jarvis uses that make it feel "alive"
- What each open-source repo offers and how it could fit
- Where there are overlaps, redundancies, and gaps

### Step 2: Tell Me What You Understand
Write back to me:
- Your understanding of the vision (in your own words)
- What you think the system should look like architecturally
- What you found in the codebases that's valuable vs. needs rethinking
- What the open-source repos offer that we should use

### Step 3: Ask Questions
Ask me anything you need to know:
- Clarifications on the vision
- Specific use cases you want to understand better
- Priorities and trade-offs
- Technical decisions that need my input

### Step 4: Suggest Improvements
Based on your analysis:
- Propose capabilities I haven't thought of
- Suggest architectural patterns that would be optimal
- Recommend additional tools, repos, or integrations
- Identify risks and propose mitigations
- If you find a fundamentally better approach than what was described, propose it

### Step 5: Iterate
We go back and forth until:
- The vision is crystal clear
- The architecture is validated against all codebases
- The implementation plan is optimal
- We both agree on the approach

### Step 6: Implementation Planning
Only after discovery is complete:
- Deep dive into all repositories to find optimal integration patterns
- Design the layer structure, meta-layers, and module connections
- Plan the build in phases with validation checkpoints
- Define what "done" looks like for each phase

### Step 7: Build
Phased construction with validation at each step. I will help test — both to verify functionality and to keep costs down.

---

## 8. What Was Already Discussed (Context, Not Constraint)

A detailed plan called "CORTEX v2 — Option G: Best-of-Breed Open Source Composition" was developed previously. Its core approach:
- Replace Jarvis brain with LangGraph orchestration + Graphiti knowledge graph + SurfSense consciousness layer
- Extract patterns from Jarvis source (read, not copy) reimplemented in Python
- Preserve OMNIS venture system as the business core
- Build new React UI matching Jarvis's 13-tab layout
- All code in `omnis_ai/core/cortex_v2/` — isolated from existing files
- Phased rollback safety (git branches, Jarvis keeps running)

**This plan may or may not be optimal.** I'm sharing it as context, not as instruction. If your analysis leads you to the same conclusion, great — that validates it. If you find a better approach, propose it. The vision matters more than any specific plan.

---

## 9. Summary — What I Want from You Right Now

1. **Analyze everything** — the local codebases, the GitHub repos, the vision description
2. **Tell me what you understand** — prove you get the vision
3. **Ask your questions** — anything unclear or that needs my input
4. **Suggest improvements** — based on what you find
5. **Don't build yet** — this is discovery, not execution

I want the best possible system that can be built. Not the fastest to build, not the simplest — the best. Let's find it together.
