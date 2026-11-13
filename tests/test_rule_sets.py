import io
import json
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from codexbp.storage import BPError, ROOT, json_bytes
from codexbp.rule_sets import MANIFEST, RuleSets
from codexbp.server import LocalServer
from codexbp import storage


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class RuleSetsFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="bp-copyable-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / "default", self.root / "default")
        self.store = RuleSets(self.root)


class RuleSetsTests(RuleSetsFixture):
    def test_default_is_complete_ordered_and_readonly(self):
        before = tree(self.root / "default")
        description = self.store.describe("default")
        self.assertTrue(description["readonly"])
        self.assertEqual([c["id"] for c in description["chapters"]], [f"chapter-{i:02d}" for i in range(1, 15)])
        for chapter in description["chapters"]:
            for node in [chapter, *chapter["children"]]:
                self.assertIn(node["path"], description["files"])
        agents = self.store.read("default", "AGENTS.md")["body"]
        for relative in re.findall(r"`(\.codex-bp/rules/[^`]+)`", agents):
            self.assertIn(relative, description["files"])
        with self.assertRaises(BPError) as raised:
            self.store.save("default", "AGENTS.md", "changed", "anything")
        self.assertEqual(raised.exception.status, 403)
        self.assertEqual(tree(self.root / "default"), before)

    def test_prompts_cover_all_workflow_stages_and_are_navigable(self):
        description = self.store.describe("default")
        required = {"requirements", "architecture", "project-setup", "planning", "implementation", "verification", "review", "delivery"}
        prompt_paths = {f for f in description["files"] if f.startswith(".codex-bp/prompts/")}
        self.assertEqual(len(prompt_paths), 12)
        self.assertTrue({f".codex-bp/prompts/{name}.md" for name in required} <= prompt_paths)
        self.assertTrue(prompt_paths <= {n["path"] for n in description["chapters"][4]["children"]})
        for path in prompt_paths:
            body = self.store.read("default", path)["body"]
            self.assertIn("## 输入", body)
            self.assertIn("## 执行要求", body)
        self.assertIn(".codex-bp/prompts/", self.store.read("default", "AGENTS.md")["body"])

    def test_complete_copy_edits_and_conflict_preserve_default(self):
        before = tree(self.root / "default")
        created = self.store.create("default", "我的规范")
        ident = created["id"]
        self.assertFalse(created["readonly"])
        self.assertEqual(set(created["files"]), set(self.store.describe("default")["files"]))
        original = self.store.read(ident, "AGENTS.md")
        saved = self.store.save(ident, original["path"], original["body"] + "\n- 自定义要求。", original["etag"])
        self.assertIn("自定义要求", saved["body"])
        with self.assertRaises(BPError) as raised:
            self.store.save(ident, original["path"], "stale", original["etag"])
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(self.store.read(ident, original["path"])["body"], saved["body"])
        self.assertEqual(tree(self.root / "default"), before)
        fork = self.store.create(ident, "另一套")
        self.assertEqual(self.store.read(fork["id"], "AGENTS.md")["body"], saved["body"])

    def test_export_contains_project_root_files_and_correct_hashes(self):
        created = self.store.create("default", "导出副本")
        for ident in ("default", created["id"]):
            with zipfile.ZipFile(io.BytesIO(self.store.archive(ident))) as archive:
                names = set(archive.namelist())
                self.assertIn("AGENTS.md", names)
                self.assertIn("VERSION_NOTES.md", names)
                self.assertEqual(sum(p.endswith("/SKILL.md") for p in names), 13)
                self.assertTrue(all(not p.startswith("default/") for p in names))
                manifest = json.loads(archive.read(MANIFEST))
                import hashlib
                for relative, expected in manifest["files"].items():
                    self.assertEqual(hashlib.sha256(archive.read(relative)).hexdigest(), expected)

    def test_invalid_paths_content_and_metadata_do_not_write(self):
        ident = self.store.create("default", "验证副本")["id"]
        before = tree(self.root)
        for relative, body in (("../outside.md", "bad"), (MANIFEST, "bad"),
                               (".codex-bp/project.json", "not json"),
                               (".agents/skills/bp-plan/SKILL.md", "---\nname: wrong\ndescription: bad\n---\nwrong")):
            with self.assertRaises(BPError):
                current = self.store.read(ident, relative)
                self.store.save(ident, relative, body, current["etag"])
        with self.assertRaises(BPError): self.store.describe("../default")
        self.assertEqual(tree(self.root), before)

    def test_external_default_corruption_is_not_silently_exported(self):
        (self.root / "default/AGENTS.md").write_text("external edit", encoding="utf-8")
        for action in (lambda: self.store.create("default", "bad"), lambda: self.store.archive("default")):
            with self.assertRaises(BPError): action()

    def test_failed_save_restores_body_and_manifest(self):
        ident = self.store.create("default", "恢复验证")["id"]
        before = tree(self.root)
        original = self.store.read(ident, "AGENTS.md")
        write = storage.atomic_write
        calls = 0
        def fail_manifest_once(path, data):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError("simulated disk failure")
            return write(path, data)
        with patch.object(storage, "atomic_write", side_effect=fail_manifest_once):
            with self.assertRaises(BPError):
                self.store.save(ident, "AGENTS.md", "new text", original["etag"])
        self.assertEqual(tree(self.root), before)


class RuleSetsApiTests(RuleSetsFixture):
    def test_read_create_save_download_and_origin_protection(self):
        server = LocalServer(self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def request(path, body=None, authorized=True, origin=None, host=None):
            headers = {"Content-Type": "application/json", "Origin": server.origin}
            if origin is not None: headers["Origin"] = origin
            if host is not None: headers["Host"] = host
            if authorized: headers["X-BP-Token"] = server.token
            req = urllib.request.Request(server.origin + path, data=json_bytes(body) if body is not None else None, headers=headers)
            try:
                with opener.open(req, timeout=20) as response: return response.status, response.read()
            except urllib.error.HTTPError as exc: return exc.code, exc.read()
        try:
            status, body = request("/api/sets")
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(body)["sets"][0]["readonly"])
            self.assertEqual(request("/api/sets", {"source": "default", "title": "test"}, False)[0], 403)
            self.assertEqual(request("/api/sets", {"source": "default", "title": "test"}, origin="https://example.test")[0], 403)
            self.assertEqual(request("/api/sets", host="example.test")[0], 403)
            self.assertEqual(request("/api/sets/default/file", {"path": "AGENTS.md", "body": "bad", "etag": "bad"})[0], 403)
            status, body = request("/api/sets", {"source": "default", "title": "API 副本"})
            self.assertEqual(status, 200)
            ident = json.loads(body)["id"]
            _, body = request(f"/api/sets/{ident}/file?path=AGENTS.md")
            original = json.loads(body)
            self.assertEqual(request(f"/api/sets/{ident}/file", {**original, "body": original["body"] + "\n- API 修改。"})[0], 200)
            _, body = request(f"/api/sets/{ident}/file?path=AGENTS.md")
            self.assertIn("API 修改", json.loads(body)["body"])
            status, body = request(f"/api/sets/{ident}/export")
            self.assertEqual(status, 200)
            with zipfile.ZipFile(io.BytesIO(body)) as archive: self.assertIn("AGENTS.md", archive.namelist())
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__": unittest.main()
