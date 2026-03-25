# venture_create

Creates a new CORTEX venture through a deep iterative research and dialogue process.

## When to use
Use when the user wants to start a new venture, business idea, project, or investment opportunity. This tool drives the full creation flow: market research → gap analysis → brain-picking → CVS scoring → confirmation.

## How it works
1. Pulls L1/L2/L3 memory for existing context
2. Runs Tier 1 market research (Tavily + Exa)
3. Analyzes gaps → asks the user targeted questions
4. Optionally runs Tier 2 deep research (Perplexity) for high-confidence gaps
5. Synthesizes VentureDNA with 8-dimension CVS scoring + CORTEX capability lens
6. User iterates until satisfied → confirms → DNA persisted + SurfSense spaces created

## Actions

### Start a new venture
```json
{"action": "start", "venture_name": "...", "description": "brief description (optional)"}
```

### Continue creation flow (answer questions, review synthesis, etc.)
```json
{"action": "continue", "input": "user's answer or feedback"}
```

### Force Tier 2 deep research
```json
{"action": "use_tier2"}
```

### Skip Tier 2 (proceed to synthesis)
```json
{"action": "skip_tier2"}
```

### Confirm venture (after CRYSTALLIZATION)
```json
{"action": "confirm"}
```

### Cancel and discard
```json
{"action": "cancel"}
```

### Check current session state
```json
{"action": "status"}
```

## CVS Scoring
8 dimensions, each 0-100:
- Market Size, Problem Severity, Solution Uniqueness, Implementation Ease, Distribution Clarity (weighted composite)
- Risk Level, AI Setup Autonomy, AI Run Autonomy (CORTEX Advantage, displayed separately)
- Verdict: AUTO_PROCEED (≥75), REVIEW (≥60), CONDITIONAL (≥35), DISCARD (<35)

## Notes
- The user can say "use tier 2" conversationally at any point — you will call this tool with action='use_tier2'
- Each question from this tool should be passed verbatim to the user — don't editorialize
- On CONFIRMATION: DNA saved, SurfSense spaces created, OutcomeLedger updated, active venture set
