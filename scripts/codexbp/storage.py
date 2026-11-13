from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import threading
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
GUARD = threading.RLock()


class BPError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_json(path, default=None):
    if not path.exists() and default is not None:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        raise BPError(f"无法读取 JSON {path.name}: {exc}") from exc


def safe_path(root, relative):
    root = Path(root).resolve()
    rel = PurePosixPath(relative)
    if not relative or "\\" in relative or rel.is_absolute() or any(
        part in ("..", ".git") or ":" in part for part in rel.parts
    ):
        raise BPError(f"禁止访问路径: {relative}")
    path = root.joinpath(*rel.parts)
    # Reject links/junctions, including ones pointing inside the root: rollback must
    # address exactly the file previewed, rather than an alias to another file.
    for parent in (path, *path.parents):
        if parent == root:
            break
        reparse = parent.exists() and bool(getattr(parent.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
        if parent.is_symlink() or reparse:
            raise BPError(f"受管路径包含符号链接或 junction: {relative}")
    if not path.resolve().is_relative_to(root):
        raise BPError(f"路径越界: {relative}")
    return path


def read_bytes(path):
    if path.is_dir():
        raise BPError(f"预期文件，发现目录: {path}", 409)
    return path.read_bytes() if path.exists() else None


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = path.stat().st_mode if path.exists() else None
    fd, temp = tempfile.mkstemp(prefix=".bp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if previous_mode is not None:
            os.chmod(temp, previous_mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def transaction(root, writes, expected):
    """Check all inputs before writing, rollback failures, lock record is last."""
    root = Path(root).resolve()
    originals = {}
    created_dirs = set()
    for relative, expected_hash in expected.items():
        path = safe_path(root, relative)
        actual = read_bytes(path)
        if digest(actual) != expected_hash:
            raise BPError(f"预览已过期，文件发生变化: {relative}", 409)
        originals[relative] = actual
    written = []
    try:
        for relative, content in writes.items():
            path = safe_path(root, relative)
            parent = path.parent
            while parent != root and not parent.exists():
                created_dirs.add(parent)
                parent = parent.parent
            written.append(relative)
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, content)
    except Exception as exc:
        recovery_errors = []
        for relative in reversed(written):
            try:
                path = safe_path(root, relative)
                old = originals.get(relative)
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, old)
            except Exception as recovery:
                recovery_errors.append(f"{relative}: {recovery}")
        for directory in sorted(created_dirs, key=lambda p: len(p.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        if recovery_errors:
            raise BPError("写入失败且部分恢复失败，请检查: " + "; ".join(recovery_errors), 500) from exc
        raise BPError(f"写入失败，文件已恢复: {exc}", 500) from exc


def validate_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value) or len(value) > 63:
        raise BPError("标识须为 1–63 位小写字母、数字和连字符")
    return value


def split_skill(text):
    """Our authored frontmatter uses two JSON-quoted YAML scalar fields."""
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", text, re.S)
    if not match:
        raise BPError("SKILL.md 缺少 frontmatter")
    fields = {}
    for line in match[1].splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or key not in ("name", "description"):
            raise BPError("本规范库的 Skill 元信息仅支持 name、description")
        try:
            fields[key] = json.loads(value.strip())
        except ValueError as exc:
            raise BPError("Skill 元信息请使用 JSON 双引号字符串，或通过表单修改") from exc
    if not all(isinstance(fields.get(k), str) and fields[k].strip() for k in ("name", "description")):
        raise BPError("Skill 必须包含 name、description")
    validate_id(fields["name"])
    return fields, match[2].lstrip("\n")
