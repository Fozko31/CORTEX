from abc import abstractmethod
from typing import Any
from python.helpers import extract_tools, files
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import Agent


DEFAULT_EXTENSIONS_FOLDER = "python/extensions"
USER_EXTENSIONS_FOLDER = "usr/extensions"

_cache: dict[str, list[type["Extension"]]] = {}


class Extension:

    def __init__(self, agent: "Agent|None", **kwargs):
        self.agent: "Agent" = agent  # type: ignore < here we ignore the type check as there are currently no extensions without an agent
        self.kwargs = kwargs

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass


async def call_extensions(
    extension_point: str, agent: "Agent|None" = None, **kwargs
) -> Any:
    from python.helpers import projects, subagents

    # search for extension folders in all agent's paths
    paths = subagents.get_paths(agent, "extensions", extension_point, default_root="python")
    all_exts = [cls for path in paths for cls in _get_extensions(path)]

    # merge: first ocurrence of file name is the override
    unique = {}
    for cls in all_exts:
        file = _get_file_from_module(cls.__module__)
        if file not in unique:
            unique[file] = cls
    classes = sorted(
        unique.values(), key=lambda cls: _get_file_from_module(cls.__module__)
    )

    # execute unique extensions
    for cls in classes:
        try:
            await cls(agent=agent).execute(**kwargs)
        except Exception as exc:
            # Log extension failure to Phase G event store (best-effort, never crash)
            try:
                ext_name = _get_file_from_module(cls.__module__)
                from python.helpers import cortex_event_store as _es
                session_id = str(getattr(getattr(agent, "id", None), "__str__", lambda: "")()) if agent else ""
                _es.log_extension_failure(
                    extension_name=ext_name,
                    exception_type=type(exc).__name__,
                    exception_msg=str(exc)[:300],
                    session_id=session_id,
                )
            except Exception:
                pass
            raise


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
