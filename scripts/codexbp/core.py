from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
import re
import stat
import tempfile
import threading
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
START = b"<!-- codex-bp:start -->"
END = b"<!-- codex-bp:end -->"
CONFIG = ".codex-bp/project.json"
LOCK = ".codex-bp/lock.json"
GUARD = threading.RLock()


class BPError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def canonical_text(data):
    """Authoring catalogs contain text only; Git/editor newline choices aren't edits."""
    return data.replace(b"\r\n", b"\n") if data is not None else None


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


def skill_text(name, description, body):
    return f"---\nname: {json.dumps(name)}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n{body.rstrip()}\n"


class Toolkit:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()

    def catalog(self):
        index = load_json(self.root / "catalog/index.json")
        if not isinstance(index, list):
            raise BPError("规范目录必须为 JSON 数组")
        result = []
        identifiers = set()
        for item in index:
            item = dict(item)
            validate_id(item["id"])
            if item["id"] in identifiers or item.get("kind") not in ("rule", "skill", "template"):
                raise BPError("规范标识重复或类型无效")
            identifiers.add(item["id"])
            if not isinstance(item.get("enabled"), bool) or not isinstance(item.get("title"), str):
                raise BPError("规范标题或启用状态无效")
            path = safe_path(self.root, item["path"])
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            if item["kind"] == "skill":
                fields, body = split_skill(text)
                if fields["name"] != item["id"]:
                    raise BPError(f"Skill 名称与目录标识不一致: {item['id']}")
                item["description"] = fields["description"]
                item["body"] = body
            else:
                item["body"] = text
            item["etag"] = digest(json_bytes({"metadata": item, "raw": digest(raw)}))
            result.append(item)
        return result

    def save_item(self, data):
        with GUARD:
            items = self.catalog()
            ident = validate_id(data.get("id"))
            old = next((i for i in items if i["id"] == ident), None)
            if old and data.get("etag") != old["etag"]:
                raise BPError("规范已被其他编辑修改，请重新加载", 409)
            if not old and data.get("etag"):
                raise BPError("规范不存在", 404)
            kind = data.get("kind", "rule")
            if kind not in ("rule", "skill", "template") or (old and kind != old["kind"]):
                raise BPError("规范类型无效，已有规范的类型不能更改")
            title, description, body = (data.get(k, "") for k in ("title", "description", "body"))
            if not all(isinstance(v, str) for v in (title, description, body)) or not title.strip() or not body.strip():
                raise BPError("标题和正文不能为空")
            if kind == "skill" and not description.strip():
                raise BPError("Skill 描述不能为空")
            if len(description) > 1024 or len(body) > 500_000:
                raise BPError("描述或正文过长")
            path = old["path"] if old else (
                f".agents/skills/{ident}/SKILL.md" if kind == "skill" else
                f".codex-bp/templates/{ident}.md" if kind == "template" else f"catalog/rules/{ident}.md"
            )
            text = skill_text(ident, description, body) if kind == "skill" else body.rstrip() + "\n"
            metadata = {"id": ident, "title": title.strip(), "description": "" if kind == "skill" else description,
                        "kind": kind, "enabled": bool(data.get("enabled", True)), "path": path}
            index = load_json(self.root / "catalog/index.json")
            index = [metadata if i["id"] == ident else i for i in index] if old else index + [metadata]
            writes = {path: text.encode("utf-8"), "catalog/index.json": json_bytes(index)}
            transaction(self.root, writes, {p: digest(read_bytes(safe_path(self.root, p))) for p in writes})
            return next(i for i in self.catalog() if i["id"] == ident)

    def releases(self):
        result = []
        directory = self.root / "releases"
        if directory.exists():
            for path in directory.iterdir():
                if path.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+", path.name):
                    manifest = load_json(safe_path(self.root, f"releases/{path.name}/manifest.json"))
                    result.append({"version": path.name, "created_at": manifest["created_at"],
                                   "items": len(manifest["catalog"])})
        return sorted(result, key=lambda r: tuple(map(int, r["version"].split("."))))

    def latest(self):
        releases = self.releases()
        if not releases:
            raise BPError("尚未创建规范版本，请先在版本管理中创建版本")
        return releases[-1]["version"]

    def next_version(self):
        releases = self.releases()
        if not releases:
            return "0.1.0"
        major, minor, patch = map(int, releases[-1]["version"].split("."))
        return f"{major}.{minor}.{patch + 1}"

    def release(self, version):
        with GUARD:
            if not isinstance(version, str) or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version):
                raise BPError("版本格式应为 major.minor.patch，例如 0.1.0")
            destination = safe_path(self.root, f"releases/{version}")
            if destination.exists():
                raise BPError("版本已存在，不允许覆盖", 409)
            if self.releases() and tuple(map(int, version.split("."))) <= tuple(map(int, self.latest().split("."))):
                raise BPError("新版本必须大于已有最新版本", 409)
            catalog = self.catalog()
            files = {"catalog/index.json": canonical_text((self.root / "catalog/index.json").read_bytes())}
            for item in catalog:
                files[item["path"]] = canonical_text(safe_path(self.root, item["path"]).read_bytes())
            manifest = {"schema_version": 1, "version": version,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "catalog": [{k: v for k, v in i.items() if k not in ("body", "etag")} for i in catalog],
                        "hashes": {p: digest(b) for p, b in files.items()}}
            writes = {f"releases/{version}/{p}": b for p, b in files.items()}
            writes[f"releases/{version}/manifest.json"] = json_bytes(manifest)
            transaction(self.root, writes, {p: None for p in writes})
            return {"version": version, "items": len(catalog)}

    def snapshot(self, version=None):
        version = version or self.latest()
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise BPError("无效的版本号")
        directory = safe_path(self.root, f"releases/{version}")
        manifest = load_json(directory / "manifest.json")
        files = {}
        for relative, expected in manifest["hashes"].items():
            data = safe_path(directory, relative).read_bytes()
            if digest(data) != expected:
                raise BPError(f"版本快照被修改: {relative}", 409)
            files[relative] = data
        return manifest, files

    def draft_diff(self, version=None):
        if not self.releases():
            return [{"path": i["path"], "diff": "新规范"} for i in self.catalog()]
        manifest, files = self.snapshot(version)
        current = {"catalog/index.json": (self.root / "catalog/index.json").read_bytes()}
        current.update({i["path"]: safe_path(self.root, i["path"]).read_bytes() for i in self.catalog()})
        return [change_info(p, canonical_text(files.get(p)), canonical_text(current.get(p)))
                for p in sorted(files.keys() | current.keys())
                if canonical_text(files.get(p)) != canonical_text(current.get(p))]

    def restore_draft(self, version, expected):
        with GUARD:
            if digest(json_bytes(self.catalog())) != expected:
                raise BPError("草稿已变化，请重新预览", 409)
            _, files = self.snapshot(version)
            writes = {i["path"]: None for i in self.catalog() if i["path"] not in files}
            writes.update(files)
            transaction(self.root, writes, {p: digest(read_bytes(safe_path(self.root, p))) for p in writes})
            return {"restored": version}

    def project_list(self):
        return load_json(self.root / ".local/projects.json", [])

    def register(self, target):
        with GUARD:
            target = project_root(target)
            items = self.project_list()
            found = next((i for i in items if i["path"] == str(target)), None)
            if found:
                return found
            item = {"id": uuid.uuid4().hex, "name": target.name, "path": str(target)}
            items.append(item)
            atomic_write(safe_path(self.root, ".local/projects.json"), json_bytes(items))
            return item

    def registered(self, ident):
        item = next((i for i in self.project_list() if i["id"] == ident), None)
        if not item:
            raise BPError("请先登记项目目录", 404)
        return project_root(item["path"])

    def detect(self, target):
        target = project_root(target)
        stack, checks, notes = [], [], []
        package_path = safe_path(target, "package.json")
        if package_path.exists():
            package = load_json(package_path)
            stack.append("TypeScript" if safe_path(target, "tsconfig.json").exists() else "JavaScript")
            manager = str(package.get("packageManager", "")).split("@")[0]
            if manager not in ("pnpm", "yarn", "npm", "bun"):
                manager = next((m for f, m in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
                                              ("bun.lock", "bun")) if safe_path(target, f).exists()), "npm")
            scripts = package.get("scripts", {})
            for name in ("test", "lint", "typecheck", "build"):
                if isinstance(scripts.get(name), str):
                    checks.append({"name": name, "command": f"{manager} run {name}", "confirmed": False})
        pyproject = safe_path(target, "pyproject.toml")
        if pyproject.exists() or safe_path(target, "requirements.txt").exists():
            stack.append("Python")
            if pyproject.exists():
                try:
                    config = tomllib.loads(pyproject.read_text(encoding="utf-8-sig"))
                    if "pytest" in config.get("tool", {}):
                        checks.append({"name": "test", "command": "python -m pytest", "confirmed": False})
                except (ValueError, OSError):
                    notes.append("pyproject.toml 无法解析，请手动填写验证命令")
        if not checks:
            notes.append("验证命令待补充；接入工具不会执行任何项目命令")
        return {"project_name": target.name, "stack": stack, "checks": checks,
                "boundaries": [], "notes": notes}

    def settings(self, target, supplied, catalog, existing=None):
        value = dict(existing) if existing else self.detect(target)
        value.pop("notes", None)
        if supplied is not None:
            allowed = {"project_name", "stack", "checks", "boundaries", "enabled_ids"}
            if not isinstance(supplied, dict) or set(supplied) - allowed:
                raise BPError("项目配置包含未知字段")
            value.update(supplied)
        available = {i["id"] for i in catalog if i["enabled"]}
        if "enabled_ids" not in value:
            value["enabled_ids"] = sorted(available)
        if existing and not supplied:
            value["enabled_ids"] = [i for i in value["enabled_ids"] if i in available]
        if not isinstance(value.get("project_name"), str) or not value["project_name"].strip():
            raise BPError("项目名称不能为空")
        for key in ("stack", "boundaries", "enabled_ids"):
            if not isinstance(value.get(key), list) or not all(isinstance(i, str) for i in value[key]):
                raise BPError(f"{key} 必须为字符串列表")
        if len(value["enabled_ids"]) != len(set(value["enabled_ids"])) or set(value["enabled_ids"]) - available:
            raise BPError("启用项包含重复、未知或已停用的规范")
        if not isinstance(value.get("checks"), list):
            raise BPError("checks 必须为列表")
        for check in value["checks"]:
            if not isinstance(check, dict) or not all(isinstance(check.get(k), str) for k in ("name", "command")):
                raise BPError("每项验证命令须有 name 和 command 字符串")
            if not isinstance(check.get("confirmed", False), bool):
                raise BPError("confirmed 须为布尔值")
        return value

    def preview(self, operation, target, settings=None, version=None):
        with GUARD:
            target = project_root(target)
            if operation not in ("init", "upgrade", "configure"):
                raise BPError("未知操作")
            old_lock_bytes = read_bytes(safe_path(target, LOCK))
            lock = load_json(safe_path(target, LOCK)) if old_lock_bytes else None
            if operation != "init" and not lock:
                raise BPError("项目尚未接入，请先初始化", 409)
            if lock and lock.get("schema_version") != 1:
                raise BPError("不支持的接入记录版本", 409)
            chosen = (lock["version"] if operation in ("configure", "init") and lock else version or self.latest())
            if lock and tuple(map(int, chosen.split("."))) < tuple(map(int, lock["version"].split("."))):
                raise BPError("不支持降级；请将历史规范复制为新的草稿版本", 409)
            manifest, files = self.snapshot(chosen)
            catalog = manifest["catalog"]
            config_path = safe_path(target, CONFIG)
            existing = load_json(config_path) if config_path.exists() else None
            config = self.settings(target, settings, catalog, existing)
            enabled = set(config["enabled_ids"])
            payload, rules = {}, []
            for item in catalog:
                if item["id"] not in enabled or not item["enabled"]:
                    continue
                data = files[item["path"]]
                if item["kind"] == "rule":
                    rules.append(data.decode("utf-8").strip())
                elif item["kind"] == "skill":
                    payload[f".agents/skills/{item['id']}/SKILL.md"] = data
                else:
                    payload[f".codex-bp/templates/{item['id']}.md"] = data
            block = START + b"\n" + ("# Codex Best Practice\n\n"
                "项目配置见 `.codex-bp/project.json`：修改前读取 boundaries，验证时核实 checks。\n"
                "验证命令仅在适用且确认后运行；接入记录中的 confirmed 不代表测试已通过。\n\n" +
                "\n\n".join(rules) + "\n").encode("utf-8") + END
            agents_path = safe_path(target, "AGENTS.md")
            agents = read_bytes(agents_path) or b""
            begin, end = block_bounds(agents)
            conflicts = []
            if lock and chosen == lock["version"] and lock.get("release_hash") != digest(json_bytes(manifest)):
                conflicts.append("已接入版本的快照记录被修改")
            override = read_bytes(safe_path(target, "AGENTS.override.md"))
            if override and override.strip():
                conflicts.append("AGENTS.override.md 会遮蔽 AGENTS.md，请先处理该项目的指令入口")
            if begin is not None:
                if not lock or digest(agents[begin:end]) != lock.get("agents_block_hash"):
                    conflicts.append("AGENTS.md 受管区块存在未记录的本地修改")
                new_agents = agents[:begin] + block + agents[end:]
            else:
                if lock:
                    conflicts.append("AGENTS.md 受管区块已被移除")
                separator = b"\r\n" if b"\r\n" in agents else b"\n"
                new_agents = agents + (separator * 2 if agents else b"") + block + separator
            old_files = lock.get("files", {}) if lock else {}
            for relative, old_hash in old_files.items():
                if not managed_payload_path(relative):
                    raise BPError(f"接入记录包含非法受管路径: {relative}")
                if digest(read_bytes(safe_path(target, relative))) != old_hash:
                    conflicts.append(f"受管文件被本地修改或删除: {relative}")
            for relative in payload:
                if relative not in old_files and safe_path(target, relative).exists():
                    conflicts.append(f"已有同名文件，拒绝覆盖: {relative}")
                elif relative not in old_files and relative.startswith(".agents/skills/") and safe_path(target, relative).parent.exists():
                    conflicts.append(f"已有同名 Skill 目录，拒绝接管: {relative}")
            if not lock and config_path.exists():
                conflicts.append(f"已有 {CONFIG}，拒绝接管")
            desired = {p: None for p in old_files if p not in payload}
            desired.update(payload)
            desired["AGENTS.md"] = new_agents
            desired[CONFIG] = json_bytes(config) if settings or not existing else config_path.read_bytes()
            new_lock = {"schema_version": 1, "version": chosen,
                        "release_hash": digest(json_bytes(manifest)), "enabled_ids": sorted(enabled),
                        "agents_block_hash": digest(block), "files": {p: digest(b) for p, b in payload.items()}}
            desired[LOCK] = json_bytes(new_lock)
            watched = {p: digest(read_bytes(safe_path(target, p))) for p in desired}
            watched["AGENTS.override.md"] = digest(override)
            changes = [change_info(p, read_bytes(safe_path(target, p)), b) for p, b in desired.items()
                       if read_bytes(safe_path(target, p)) != b]
            plan = {"schema_version": 1, "operation": operation, "target": str(target), "version": chosen,
                    "settings": settings, "release_hash": digest(json_bytes(manifest)), "expected": watched,
                    "conflicts": conflicts, "changes": changes, "config": config}
            plan["fingerprint"] = digest(json_bytes(plan))
            return plan

    def apply(self, plan):
        with GUARD:
            if not isinstance(plan, dict) or plan.get("schema_version") != 1:
                raise BPError("不支持的预览计划")
            unsigned = {key: value for key, value in plan.items() if key != "fingerprint"}
            if digest(json_bytes(unsigned)) != plan.get("fingerprint"):
                raise BPError("计划内容被修改，请重新预览", 409)
            fresh = self.preview(plan["operation"], plan["target"], plan.get("settings"), plan["version"])
            if fresh["conflicts"]:
                raise BPError("存在冲突，未写入任何文件: " + "; ".join(fresh["conflicts"]), 409)
            if fresh["fingerprint"] != plan.get("fingerprint"):
                raise BPError("预览已过期或被修改，请重新预览并确认", 409)
            writes = {c["path"]: base64.b64decode(c["content"]) if c["content"] is not None else None
                      for c in fresh["changes"]}
            # The lock is always the last write, even if payload ordering changes.
            if LOCK in writes:
                writes[LOCK] = writes.pop(LOCK)
            transaction(Path(fresh["target"]), writes, fresh["expected"])
            return {"ok": True, "version": fresh["version"], "changed": len(writes)}

    def check(self, target):
        target = project_root(target)
        if not safe_path(target, LOCK).exists():
            return {"installed": False, "ok": False, "issues": ["尚未接入"], "detected": self.detect(target)}
        plan = self.preview("configure", target)
        config = plan["config"]
        notes = [f"命令待确认: {i['name']}" for i in config["checks"] if not i.get("confirmed")]
        if not config["checks"]:
            notes.append("验证命令待补充")
        return {"installed": True, "ok": not plan["conflicts"], "version": plan["version"],
                "latest": self.latest(), "issues": plan["conflicts"], "notes": notes, "config": config}


def project_root(value):
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise BPError("请提供项目目录")
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise BPError(f"项目目录不存在: {path}")
    if ".git" in path.parts:
        raise BPError("不能在 .git 内操作")
    return path


def managed_payload_path(relative):
    return bool(re.fullmatch(r"\.agents/skills/[a-z][a-z0-9-]*/SKILL\.md|\.codex-bp/templates/[a-z][a-z0-9-]*\.md", relative))


def block_bounds(data):
    if data.count(START) != data.count(END) or data.count(START) > 1:
        raise BPError("AGENTS.md 受管区块标记缺失或重复", 409)
    if START not in data:
        return None, None
    begin, end = data.index(START), data.index(END) + len(END)
    if data.index(END) < begin:
        raise BPError("AGENTS.md 受管区块标记顺序错误", 409)
    return begin, end


def change_info(path, old, new):
    diff = "".join(difflib.unified_diff((old or b"").decode("utf-8-sig").splitlines(True),
                                       (new or b"").decode("utf-8-sig").splitlines(True),
                                       fromfile=f"before/{path}", tofile=f"after/{path}"))
    return {"path": path, "action": "delete" if new is None else "create" if old is None else "update",
            "diff": diff, "content": base64.b64encode(new).decode() if new is not None else None}
