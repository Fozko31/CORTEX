# venture_ops Tool

Manage operational infrastructure for confirmed ventures: autonomy policy, credential vault, HITL queue, recurring tasks, and playbooks.

## When to use
- Checking venture health, pending approvals, or credential expiry
- Setting/changing autonomy rules for a venture (after user instruction)
- Storing credentials for a venture's integrations
- Approving or rejecting queued actions
- Adding or managing recurring automated tasks
- Retrieving a venture's operational playbook

## Operations

### health_check
```json
{
  "tool_name": "venture_ops",
  "operation": "health_check",
  "venture_slug": "my_venture"
}
```
Returns: scheduler tasks, pending HITL actions, credential expiry warnings, active recurring tasks.

### set_autonomy
Set autonomy level for an action class. **Only call after explicit user instruction.**
```json
{
  "tool_name": "venture_ops",
  "operation": "set_autonomy",
  "venture_slug": "my_venture",
  "action_class": "SEND_MESSAGE",
  "level": "DRAFT_FIRST",
  "resource_id": "gmail_primary",
  "resource_description": "Primary outreach Gmail account",
  "reason": "User wants to review all outbound emails from this account"
}
```
- `action_class`: READ | DRAFT | SEND_MESSAGE | SPEND_MONEY | DEPLOY | SCHEDULE | MODIFY_DATA | DEFAULT
- `level`: AUTO | DRAFT_FIRST | REQUIRE_APPROVAL
- `resource_id`: Optional. Enables per-resource rules (e.g. two email accounts with different rules).
- Use `action_class: DEFAULT` to set a venture-wide default. Add `spend_auto_threshold_eur` for spend cap.

### get_autonomy
```json
{
  "tool_name": "venture_ops",
  "operation": "get_autonomy",
  "venture_slug": "my_venture"
}
```

### list_pending / approve / reject
```json
{"tool_name": "venture_ops", "operation": "list_pending", "venture_slug": "my_venture"}
{"tool_name": "venture_ops", "operation": "approve", "action_id": "<uuid>"}
{"tool_name": "venture_ops", "operation": "reject", "action_id": "<uuid>"}
```

### set_credential
```json
{
  "tool_name": "venture_ops",
  "operation": "set_credential",
  "venture_slug": "my_venture",
  "name": "gmail_primary",
  "value": "<secret>",
  "description": "Main outreach Gmail app password",
  "expires_at": "2026-12-31T00:00:00Z"
}
```
Values are Fernet-encrypted at rest. Never stored in plaintext.

### list_credential_keys
```json
{
  "tool_name": "venture_ops",
  "operation": "list_credential_keys",
  "venture_slug": "my_venture"
}
```
Returns names + expiry status only. Never raw values.

### add_task / disable_task
```json
{
  "tool_name": "venture_ops",
  "operation": "add_task",
  "venture_slug": "my_venture",
  "task_type": "email_handling",
  "name": "MyVenture Email Triage",
  "cadence": "0 9 * * 1-5",
  "prompt": "Check Gmail for my_venture. Triage new emails. Draft replies for leads. Surface any requiring approval."
}
```

### get_playbook
```json
{
  "tool_name": "venture_ops",
  "operation": "get_playbook",
  "venture_slug": "my_venture",
  "version": 2
}
```
Omit `version` to get the latest.

## Autonomy policy rules
- NEVER set autonomy rules without explicit user instruction
- When the user says "for this venture, auto-send emails", use `set_autonomy` with level AUTO
- When the user specifies a resource (e.g. "for the personal email"), always include `resource_id`
- Rules persist across sessions. Once set, CORTEX follows them until explicitly changed.
- SPEND_MONEY AUTO is always subject to `spend_auto_threshold_eur` (default €0.00 = never auto)
