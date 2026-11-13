#!/usr/bin/env python3
"""Standalone GitHub workbench entry; Python stdlib, no Git/pip required."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPOSITORY = "https://github.com/matthewdailytools/codexbestpratice"
API = "https://api.github.com/repos/matthewdailytools/codexbestpratice"
MAX_ARCHIVE = 20 * 1024 * 1024
MAX_EXPANDED = 80 * 1024 * 1024


class WorkbenchError(Exception):
    pass


def _download(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": "codex-best-practice", "Accept": "application/vnd.github+json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read(limit + 1)
            break
        except (OSError, urllib.error.URLError) as exc:
            retryable = not isinstance(exc, urllib.error.HTTPError) or exc.code >= 500
            if attempt == 1 or not retryable:
                raise WorkbenchError("GitHub 获取失败，请检查网络或 API 限额；未改动项目，也未回退到旧版本。") from exc
    if len(data) > limit:
        raise WorkbenchError("GitHub 响应超过大小限制")
    return data


def _json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _validate_cache(directory, commit):
    info = _json(directory / ".workbench-cache.json")
    if info.get("source") != {"kind": "github", "repository": REPOSITORY, "commit": commit}:
        raise WorkbenchError("工作台缓存来源不匹配")
    for relative, expected in info["hashes"].items():
        path = directory / relative
        if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink() or _hash(path.read_bytes()) != expected:
            raise WorkbenchError("工作台缓存被修改，请保留修改后移走该缓存，再重新获取")
    return {**info, "toolkit_path": str(directory.resolve())}


def fetch_workbench(ref="main", cache_dir=None):
    """Download the entire workbench at a resolved commit into an immutable cache."""
    if not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,150}", ref) or ".." in ref:
        raise WorkbenchError("无效的 GitHub 分支、标签或 commit")
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        commit = ref
    else:
        try:
            commit = json.loads(_download(API + "/commits/" + urllib.parse.quote(ref, safe=""), 1_000_000))["sha"]
        except (KeyError, ValueError, TypeError) as exc:
            raise WorkbenchError("GitHub 未返回有效 commit") from exc
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise WorkbenchError("GitHub commit 格式无效")
    cache = Path(cache_dir).expanduser().resolve() if cache_dir else Path.home() / ".cache/codex-best-practice"
    destination = cache / commit
    if destination.exists():
        return _validate_cache(destination, commit)
    data = _download(f"https://codeload.github.com/matthewdailytools/codexbestpratice/zip/{commit}", MAX_ARCHIVE)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".download-", dir=cache) as temporary:
        unpacked = Path(temporary) / "workbench"
        unpacked.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 4000 or sum(i.file_size for i in entries) > MAX_EXPANDED:
                    raise WorkbenchError("工作台解压大小或文件数超过限制")
                roots, names = set(), set()
                for entry in entries:
                    parts = PurePosixPath(entry.filename).parts
                    if not parts or entry.filename.startswith("/") or "\\" in entry.filename or any(p in ("..", ".git") or ":" in p for p in parts):
                        raise WorkbenchError("GitHub 压缩包包含非法路径")
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        raise WorkbenchError("工作台压缩包不允许符号链接")
                    roots.add(parts[0])
                    if len(roots) != 1:
                        raise WorkbenchError("工作台压缩包根目录无效")
                    if len(parts) == 1 or entry.is_dir():
                        continue
                    relative = "/".join(parts[1:])
                    if relative.casefold() in names:
                        raise WorkbenchError("工作台压缩包包含重复路径")
                    names.add(relative.casefold())
                    path = unpacked.joinpath(*parts[1:])
                    if not path.resolve().is_relative_to(unpacked.resolve()):
                        raise WorkbenchError("工作台压缩包路径越界")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(archive.read(entry))
        except zipfile.BadZipFile as exc:
            raise WorkbenchError("GitHub 未返回有效的工作台压缩包") from exc
        if not all((unpacked / p).is_file() for p in ("README.md", "scripts/codex_bp.py", "catalog/index.json")):
            raise WorkbenchError("GitHub 包缺少完整工作台入口")
        versions = sorted(p.name for p in (unpacked / "releases").iterdir()
                          if p.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+", p.name))
        if not versions:
            raise WorkbenchError("GitHub 工作台尚无可安装规范版本")
        # Catalog drafts may be edited in the UI. Runtime code and published
        # snapshots remain verified, and extra local releases aren't upstream.
        hashes = {p.relative_to(unpacked).as_posix(): _hash(p.read_bytes())
                  for base in (unpacked / "scripts", unpacked / "releases", unpacked / "web")
                  for p in base.rglob("*") if p.is_file()}
        for name in ("workbench.py", "WORKBENCH.md", "README.md"):
            if (unpacked / name).is_file():
                hashes[name] = _hash((unpacked / name).read_bytes())
        info = {"source": {"kind": "github", "repository": REPOSITORY, "commit": commit},
                "versions": versions, "hashes": hashes}
        (unpacked / ".workbench-cache.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            os.rename(unpacked, destination)
        except OSError:
            if not destination.exists():
                raise
        return _validate_cache(destination, commit)


def main():
    parser = argparse.ArgumentParser(description="引用整个 GitHub 工作台，自动获取并应用到项目")
    parser.add_argument("--target", type=Path, default=Path.cwd())
    parser.add_argument("--mode", choices=("default", "guided"), default="default")
    parser.add_argument("--action", choices=("apply", "upgrade", "configure", "check", "open", "fetch"), default="apply")
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--ref", default=None)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "guided" and args.action in ("apply", "configure", "upgrade") and not args.settings:
            raise WorkbenchError("请由 Codex 收集引导设置，将答案作为 --settings 传入后自动应用")
        target = args.target.expanduser().resolve()
        ref = args.ref or "main"
        lock_path = target / ".codex-bp/lock.json"
        if args.ref is None and args.action in ("check", "configure", "apply") and lock_path.exists():
            source = _json(lock_path).get("source", {})
            if source.get("kind") == "github":
                ref = source["commit"]
        info = fetch_workbench(ref, args.cache_dir)
        if args.action == "fetch":
            result = {k: v for k, v in info.items() if k != "hashes"}
        elif args.action == "open":
            return subprocess.call([sys.executable, str(Path(info["toolkit_path"]) / "scripts/codex_bp.py"),
                                    "serve", "--open", "--target", str(target)])
        else:
            sys.path.insert(0, str(Path(info["toolkit_path"]) / "scripts"))
            from codexbp.core import Toolkit
            tool = Toolkit(info["toolkit_path"], source=info["source"], allowed_versions=info["versions"])
            if args.action == "check":
                result = tool.check(target)
            else:
                settings = _json(args.settings) if args.settings else None
                operation = {"apply": "init", "upgrade": "upgrade", "configure": "configure"}[args.action]
                if args.action == "apply" and lock_path.exists() and _json(lock_path).get("source", {}).get("kind") != "github":
                    operation = "upgrade"
                plan = tool.preview(operation, target, settings)
                summary = {"source": info["source"], "version": plan["version"], "target": plan["target"],
                           "config": plan["config"], "conflicts": plan["conflicts"],
                           "changes": [{k: v for k, v in change.items() if k != "content"} for change in plan["changes"]]}
                # Mode selection authorizes applying the workbench to the named
                # project; print the concrete changes before the guarded write.
                sys.stdout.buffer.write((json.dumps({"preview": summary}, ensure_ascii=False) + "\n").encode("utf-8"))
                sys.stdout.flush()
                result = tool.apply(plan)
                result["source"] = info["source"]
                result["status"] = tool.check(target)
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 2 if result.get("ok") is False else 0
    except Exception as exc:
        sys.stderr.buffer.write((json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n").encode("utf-8"))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
