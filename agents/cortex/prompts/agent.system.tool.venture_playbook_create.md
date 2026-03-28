# venture_playbook_create Tool

Create, manage, and publish operational playbooks for confirmed ventures.
A playbook documents how the venture runs: business model, customers, operations, team, tools, KPIs, compliance.

## When to use
- User asks to create a playbook for a venture
- Starting or resuming a playbook creation session
- Saving answers for a completed step
- Publishing a finished playbook

## Flow overview
9 steps. Complete them in order. After each step: call `save_step` with the content, then ask the user the next step's questions. Never batch multiple steps.

Steps:
1. venture_confirmed (implicit — venture already exists)
2. business_model
3. customer_profile
4. core_operations
5. team_and_roles
6. tools_and_integrations
7. metrics_and_kpis
8. compliance_and_legal ← important: always include this
9. reviewed_and_published

## Operations

### start
Begin a new playbook (or detect existing draft).
```json
{
  "tool_name": "venture_playbook_create",
  "operation": "start",
  "venture_slug": "my_venture",
  "venture_name": "My Venture"
}
```
If returns `status: draft_found` → offer to resume or start fresh.

### resume
Continue from last completed step.
```json
{
  "tool_name": "venture_playbook_create",
  "operation": "resume",
  "venture_slug": "my_venture"
}
```

### save_step
Save content for one completed step.
```json
{
  "tool_name": "venture_playbook_create",
  "operation": "save_step",
  "venture_slug": "my_venture",
  "step": "business_model",
  "content": {
    "problem": "...",
    "revenue_model": "subscription",
    "revenue_streams": ["..."],
    "cost_structure": "..."
  }
}
```
Returns: next step name + prompt text to ask the user.

### publish
Finalize and version the playbook.
```json
{
  "tool_name": "venture_playbook_create",
  "operation": "publish",
  "venture_slug": "my_venture"
}
```
Saves as `playbook_v{N}.json` locally. Pushes to SurfSense `{slug}_ops` space as "{VentureName} Playbook v{N}".

### get_status
```json
{
  "tool_name": "venture_playbook_create",
  "operation": "get_status",
  "venture_slug": "my_venture"
}
```

### discard_draft
```json
{
  "tool_name": "venture_playbook_create",
  "operation": "discard_draft",
  "venture_slug": "my_venture"
}
```

## Compliance step guidance
Step 8 (compliance_and_legal) must always be completed before publishing. Key questions to ask the user:
- What personal data is collected? How stored and for how long?
- GDPR lawful basis (consent, legitimate interest, contract)
- User rights procedures (access, erasure, portability)
- Legal entity + jurisdiction
- ToS and Privacy Policy status (draft / live / not yet created)
- Known liability risks and mitigations

## Important
- Never skip steps without user instruction
- Always offer resume when a draft is found
- Playbooks are versioned — publishing v2 keeps v1 intact
- Retrieve published playbooks via venture_ops get_playbook
