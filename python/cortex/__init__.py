# python/cortex — CORTEX's own infrastructure package
#
# This package owns all framework primitives that CORTEX depends on.
# No CORTEX code should import from python.helpers.* or agent.* for these
# once H1-B (import migration) is complete.
#
# Contents:
#   dirty_json  — lenient JSON parser
#   extension   — Extension base class + hook loader
#   tool        — Tool base class + Response
#   loop_data   — LoopData (prompt injection state)
#   memory      — Memory (FAISS vector DB + path utilities)
#   config      — CortexConfig (CORTEX-specific configuration)
#   state       — CortexState (persistent session KV store)
#   scheduler   — TaskScheduler / ScheduledTask / TaskSchedule
#   logger      — CortexLogger (structured, no SocketIO coupling)
