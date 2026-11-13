"""A read-only, copyable default folder and complete editable copies."""
from __future__ import annotations

import io
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .storage import BPError, GUARD, digest, json_bytes, load_json, read_bytes, safe_path, split_skill, transaction

MANIFEST = ".codex-bp/manifest.json"


class RuleSets:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def directory(self, ident):
        if ident == "default":
            return safe_path(self.root, "default")
        if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{32}", ident):
            raise BPError("规范副本不存在", 404)
        path = safe_path(self.root, f".local/rule-sets/{ident}/files")
        if not path.is_dir():
            raise BPError("规范副本不存在", 404)
        return path

    def manifest(self, ident):
        directory = self.directory(ident)
        manifest = load_json(safe_path(directory, MANIFEST))
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("files"), dict):
            raise BPError("规范文件清单无效", 409)
        for relative, expected in manifest["files"].items():
            path = safe_path(directory, relative)
            if relative == MANIFEST or not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
                raise BPError("规范文件清单无效", 409)
            if ident == "default" and digest(read_bytes(path)) != expected:
                raise BPError(f"默认原件被外部修改，请恢复原文件：{relative}", 409)
        return manifest

    def list(self):
        with GUARD:
            manifest = self.manifest("default")
            result = [{"id": "default", "title": manifest["title"], "readonly": True}]
            parent = safe_path(self.root, ".local/rule-sets")
            if parent.exists():
                for path in sorted(parent.iterdir()):
                    if re.fullmatch(r"[0-9a-f]{32}", path.name):
                        info = safe_path(self.root, f".local/rule-sets/{path.name}/info.json")
                        if info.exists():
                            record = load_json(info)
                            result.append({"id": path.name, "title": record["title"], "readonly": False})
            return result

    def describe(self, ident):
        with GUARD:
            manifest = self.manifest(ident)
            return {"id": ident, "title": manifest["title"], "version": manifest["version"],
                    "readonly": ident == "default", "chapters": manifest["chapters"],
                    "notes": manifest["notes"], "files": sorted([*manifest["files"], MANIFEST])}

    def read(self, ident, relative):
        with GUARD:
            manifest = self.manifest(ident)
            if relative not in manifest["files"] and relative != MANIFEST:
                raise BPError("该文件不在规范包内", 404)
            data = safe_path(self.directory(ident), relative).read_bytes()
            return {"path": relative, "body": data.decode("utf-8"), "etag": digest(data),
                    "editable": ident != "default" and relative != MANIFEST}

    def create(self, source, title):
        with GUARD:
            if not isinstance(title, str) or not title.strip() or len(title) > 80:
                raise BPError("名称须为 1–80 字符")
            manifest = self.manifest(source)
            source_dir = self.directory(source)
            files = {p: safe_path(source_dir, p).read_bytes() for p in manifest["files"]}
            ident = uuid.uuid4().hex
            manifest = {**manifest, "title": title.strip(), "files": {p: digest(data) for p, data in files.items()}}
            prefix = f".local/rule-sets/{ident}"
            writes = {f"{prefix}/files/{p}": data for p, data in files.items()}
            writes[f"{prefix}/files/{MANIFEST}"] = json_bytes(manifest)
            writes[f"{prefix}/info.json"] = json_bytes({"title": title.strip(), "source": source,
                "created_at": datetime.now(timezone.utc).isoformat()})
            transaction(self.root, writes, {p: None for p in writes})
            return self.describe(ident)

    def save(self, ident, relative, body, etag):
        with GUARD:
            if ident == "default":
                raise BPError("默认规范只读，请先新建一套再编辑", 403)
            current = self.read(ident, relative)
            if not current["editable"]:
                raise BPError("文件清单由系统维护", 403)
            if current["etag"] != etag:
                raise BPError("正文已被其他编辑修改，请刷新后重试", 409)
            if not isinstance(body, str) or not body.strip() or len(body) > 500_000:
                raise BPError("正文须为非空文本，最多 500000 字符")
            if relative.endswith(".json"):
                import json
                try:
                    if not isinstance(json.loads(body), dict):
                        raise ValueError("配置须为对象")
                except ValueError as exc:
                    raise BPError(f"JSON 配置无效：{exc}") from exc
            if relative.endswith("/SKILL.md"):
                fields, _ = split_skill(body)
                if fields["name"] != relative.split("/")[-2]:
                    raise BPError("技能 name 必须与文件夹名一致")
            directory = self.directory(ident)
            manifest = self.manifest(ident)
            data = (body.rstrip() + "\n").encode("utf-8")
            manifest["files"][relative] = digest(data)
            transaction(directory, {relative: data, MANIFEST: json_bytes(manifest)},
                        {relative: current["etag"], MANIFEST: digest(safe_path(directory, MANIFEST).read_bytes())})
            return self.read(ident, relative)

    def archive(self, ident):
        with GUARD:
            manifest = self.manifest(ident)
            directory = self.directory(ident)
            files = {p: safe_path(directory, p).read_bytes() for p in manifest["files"]}
            manifest["files"] = {p: digest(data) for p, data in files.items()}
            files[MANIFEST] = json_bytes(manifest)
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for relative, data in sorted(files.items()):
                    archive.writestr(relative, data)
            return output.getvalue()
