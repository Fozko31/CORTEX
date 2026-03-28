"""
python/cortex/extension.py — Extension Base Class + Hook Loader
===============================================================
CORTEX-owned copy of python/helpers/extension.py.

Differences from AZ original:
  - Removed AZ-internal cortex_event_store logging on failure
    (that was a circular dep — CORTEX's event store logging its own extension failures)
  - Same API: Extension, call_extensions()
  - Extensions still discovered from python/extensions/ and usr/extensions/
    (discovery path unchanged — CORTEX extensions live there, H1-B just changes imports)

H4: hook loader will be replaced with CORTEX's own when we own the conversation loop.
"""
from abc import abstractmethod
from typing import Any, TYPE_CHECKING

from python.helpers import extract_tools, files

if TYPE_CHECKING:
    from agent import Agent


DEFAULT_EXTENSIONS_FOLDER = "python/extensions"
USER_EXTENSIONS_FOLDER = "usr/extensions"

_cache: dict[str, list[type["Extension"]]] = {}


class Extension:

    def __init__(self, agent: "Agent|None", **kwargs):
        self.agent: "Agent" = agent  # type: ignore
        self.kwargs = kwargs

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass


async def call_extensions(
    extension_point: str, agent: "Agent|None" = None, **kwargs
) -> Any:
    from python.helpers import projects, subagents

    paths = subagents.get_paths(agent, "extensions", extension_point, default_root="python")
    all_exts = [cls for path in paths for cls in _get_extensions(path)]

    # merge: first occurrence of file name is the override
    unique = {}
    for cls in all_exts:
        file = _get_file_from_module(cls.__module__)
        if file not in unique:
            unique[file] = cls
    classes = sorted(
        unique.values(), key=lambda cls: _get_file_from_module(cls.__module__)
    )

    for cls in classes:
        await cls(agent=agent).execute(**kwargs)


def _get_file_from_module(module_name: str) -> str:
    return module_name.split(".")[-1]


def _get_extensions(folder: str):
    global _cache
    folder = files.get_abs_path(folder)
    if folder in _cache:
        classes = _cache[folder]
    else:
        if not files.exists(folder):
            return []
        classes = extract_tools.load_classes_from_folder(folder, "*", Extension)
        _cache[folder] = classes

    return classes
