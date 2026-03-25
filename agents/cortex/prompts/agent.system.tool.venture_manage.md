# venture_manage

Manages existing CORTEX ventures: list, status, health pulse, activate, deactivate, delete.

## When to use
Use when the user asks about existing ventures, wants to see CVS scores, check health, switch active venture, or delete a venture.

## Actions

### List all ventures
```json
{"action": "list"}
```
Returns all ventures with compact health pulse summary.

### Full venture status (VentureDNA + CVS visual)
```json
{"action": "status", "venture_name": "..."}
```
If no name given, uses active venture.

### Compact health pulse
```json
{"action": "health", "venture_name": "..."}
```

### Activate a venture (sets it as the active context for all future turns)
```json
{"action": "activate", "venture_name": "..."}
```

### Deactivate (clear active venture context)
```json
{"action": "deactivate"}
```

### Delete a venture
```json
{"action": "delete", "venture_name": "..."}
```

### Show CVS score visual only
```json
{"action": "cvs", "venture_name": "..."}
```

### Show Kelly capital allocation signal
```json
{"action": "kelly", "venture_name": "..."}
```
Requires outcome data to be logged first.

## Notes
- If no venture_name is given, the active venture is used
- Activating a venture sets it in the system prompt for all subsequent turns
- Kelly signals require revenue/cost events logged via OutcomeLedger
