"""
python/cortex/memory.py — Memory Interface (FAISS + Path Utilities)
====================================================================
Re-exports AZ's Memory class and path utilities during H1 transition.
Full ownership (FAISS wrapper + path logic) moves here in H4.

CORTEX code imports:
    from python.cortex.memory import Memory, get_agent_memory_subdir, abs_db_dir

Path utilities are the most-used interface:
    get_agent_memory_subdir(agent) → str  — memory subdir name for agent
    abs_db_dir(subdir: str) → str         — absolute path to DB directory
    abs_knowledge_dir(subdir, *parts)     — absolute knowledge path

Memory class (FAISS wrapper):
    Memory.get(agent) → Memory            — load or create for agent
    mem.search_similarity_threshold(query, limit, threshold, filter)
    mem.insert_text(text, metadata) → id
    mem.delete_documents_by_ids(ids)
"""
from python.helpers.memory import (
    Memory,
    MyFaiss,
    abs_db_dir,
    abs_knowledge_dir,
    get_agent_memory_subdir,
    get_context_memory_subdir,
    get_existing_memory_subdirs,
    get_knowledge_subdirs_by_memory_subdir,
    get_memory_subdir_abs,
    reload,
)

__all__ = [
    "Memory",
    "MyFaiss",
    "abs_db_dir",
    "abs_knowledge_dir",
    "get_agent_memory_subdir",
    "get_context_memory_subdir",
    "get_existing_memory_subdirs",
    "get_knowledge_subdirs_by_memory_subdir",
    "get_memory_subdir_abs",
    "reload",
]
