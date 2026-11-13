"""GitHub is the install default; core remains deterministic and offline."""
import sys

from .core import BPError, LOCK, ROOT, Toolkit, load_json, safe_path

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workbench import REPOSITORY, WorkbenchError, fetch_workbench


def github_toolkit(ref="main", cache_dir=None):
    try:
        info = fetch_workbench(ref, cache_dir)
    except (WorkbenchError, OSError, ValueError, KeyError) as exc:
        raise BPError(str(exc), 502) from exc
    return Toolkit(info["toolkit_path"], source=info["source"], allowed_versions=info["versions"])


def for_operation(local, target, operation, source="github", ref=None, cache_dir=None):
    if source == "local":
        return local
    if source != "github":
        raise BPError("规范源须为 github 或 local")
    lock_path = safe_path(target, LOCK)
    if ref is None and operation in ("init", "configure", "check") and lock_path.exists():
        recorded = load_json(lock_path).get("source", {})
        if recorded.get("kind") == "github":
            validate_source(recorded)
            ref = recorded["commit"]
    return github_toolkit(ref or "main", cache_dir)


def validate_source(source):
    if source.get("kind") != "github" or source.get("repository") != REPOSITORY or not source.get("commit"):
        raise BPError("未知的工作台来源")


def for_record(local, source, cache_dir=None):
    if not source or source.get("kind") == "local":
        return local
    validate_source(source)
    return github_toolkit(source["commit"], cache_dir)


def for_project(local, target, cache_dir=None):
    path = safe_path(target, LOCK)
    return for_record(local, load_json(path).get("source") if path.exists() else None, cache_dir)
