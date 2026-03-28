# Tool: self_improve

Use this tool to manage CORTEX's self-optimization system (Phase G).

## When to use

- User asks about CORTEX's performance, weak spots, or improvement
- User wants to run the weekly self-improvement cycle manually
- User wants to review, apply, or reject an experiment result
- User asks about versions, rollbacks, or benchmark scores
- User wants CORTEX to analyze its own struggles

## Operations

### trigger_analysis
Aggregates struggle events from the past week → generates improvement hypotheses → sends to Telegram.
```json
{"operation": "trigger_analysis", "params": {"days": 7, "top_n": 3}}
```

### run_experiment
Runs a specific experiment. Requires trigger_analysis to have been run first.
Specify rank (1, 2, or 3) or experiment_id. Use dry_run=true for testing.
```json
{"operation": "run_experiment", "params": {"rank": 1, "dry_run": false}}
```

### show_report
Show the full report for an experiment.
```json
{"operation": "show_report", "params": {"experiment_id": "exp-abc12345"}}
```

### apply
Apply an approved experiment to live files. Requires user to have reviewed the report.
```json
{"operation": "apply", "params": {"experiment_id": "exp-abc12345"}}
```

### reject
Reject an experiment. No files changed. Reason is logged.
```json
{"operation": "reject", "params": {"experiment_id": "exp-abc12345", "reason": "delta too small"}}
```

### show_versions
List pinned CORTEX versions (stable versions by default).
```json
{"operation": "show_versions", "params": {"stable_only": true}}
```

### get_version
Get a version report. format: "human" (default) or "agent".
```json
{"operation": "get_version", "params": {"version_id": "cortex-v7-0", "format": "human"}}
```

### rollback_request
Stage a rollback — FIRST confirmation. Returns confirm_phrase needed for step 2.
```json
{"operation": "rollback_request", "params": {"tag": "cortex-v7-0", "reason": "experiment broke routing", "failed_assumptions": "assumed routing was isolated"}}
```

### rollback_execute
Execute the staged rollback — SECOND confirmation. Pass exact confirm_phrase from step 1.
```json
{"operation": "rollback_execute", "params": {"confirm_phrase": "ROLLBACK-cortex-v7-0-1430-CONFIRM"}}
```

### benchmark
Run the 20-query benchmark suite to check current CORTEX capability scores.
```json
{"operation": "benchmark", "params": {"dry_run": false}}
```

### show_status
Overall self-optimization system status: event store, struggles, experiments, versions, benchmark drift.
```json
{"operation": "show_status", "params": {}}
```

## Rules

- Never apply an experiment without showing the user the full report first
- Never execute a rollback without going through rollback_request first (two steps required)
- When user says "apply experiment X" or "reject experiment X" — use apply/reject operation
- Experiments affect prompts and knowledge files only — never cloud memory
- show_status is the default when the user asks general questions about CORTEX's performance
