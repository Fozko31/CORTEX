"""
cortex_surfsense_push.py — Single place for all SurfSense push calls from Phase G.

All Phase G modules (Loop 2/3/5) push to the cortex_optimization space.
This helper wraps the push_document() signature correctly.
"""

from datetime import datetime


async def push_to_optimization_space(
    title: str,
    content: str,
    tags: list[str] | None = None,
) -> bool:
    """
    Push a document to SurfSense cortex_optimization space.
    Handles the correct push_document(space_name, document) signature.
    Returns True on success, False on failure.
    """
    try:
        from python.helpers.cortex_surfsense_client import CortexSurfSenseClient
        client = CortexSurfSenseClient()
        meta = {"tags": tags or [], "created_at": datetime.now().isoformat()}
        await client.push_document(
            "cortex_optimization",
            {
                "title": title,
                "content": content,
                "metadata": meta,
            },
        )
        return True
    except Exception:
        return False
