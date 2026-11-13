import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from codexbp import core
from codexbp.core import BPError, CONFIG, LOCK, ROOT, Toolkit, digest, json_bytes, safe_path
from codexbp.server import LocalServer


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class ToolkitFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex bp 测试 ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "toolkit"
        shutil.copytree(ROOT / "catalog", self.source / "catalog")
        shutil.copytree(ROOT / ".agents", self.source / ".agents")
        shutil.copytree(ROOT / ".codex-bp/templates", self.source / ".codex-bp/templates")
        self.tool = Toolkit(self.source)
        self.tool.release("0.1.0")
        self.target = self.base / "项目 with spaces"
        self.target.mkdir()

    def install(self, settings=None):
        return self.tool.apply(self.tool.preview("init", self.target, settings))

    def change_rule(self, title="新标题"):
        item = self.tool.catalog()[0]
        return self.tool.save_item({**item, "title": title, "body": item["body"] + "\n- 新增约定。\n"})


class ToolkitTests(ToolkitFixture):
    def test_preview_is_read_only_and_repeated_init_is_idempotent(self):
        before = tree(self.target)
        plan = self.tool.preview("init", self.target)
        self.assertEqual(before, tree(self.target))
        self.assertFalse(plan["conflicts"])
        self.tool.apply(plan)
        installed = tree(self.target)
        self.assertEqual(self.install()["changed"], 0)
        self.assertEqual(installed, tree(self.target))
        self.assertTrue(self.tool.check(self.target)["ok"])

    def test_existing_agents_bytes_preserved_outside_block(self):
        original = b"\xef\xbb\xbf# Existing\r\n\r\nKeep my rules.\r\n"
        (self.target / "AGENTS.md").write_bytes(original)
        self.install()
        self.assertTrue((self.target / "AGENTS.md").read_bytes().startswith(original))
        with (self.target / "AGENTS.md").open("ab") as f:
            f.write(b"\r\n# Custom tail\r\n")
        self.change_rule()
        self.tool.release("0.1.1")
        self.tool.apply(self.tool.preview("upgrade", self.target))
        actual = (self.target / "AGENTS.md").read_bytes()
        self.assertTrue(actual.startswith(original))
        self.assertTrue(actual.endswith(b"\r\n# Custom tail\r\n"))

    def test_collision_aborts_all_writes(self):
        collision = self.target / ".agents/skills/bp-plan/SKILL.md"
        collision.parent.mkdir(parents=True)
        collision.write_text("My skill", encoding="utf-8")
        before = tree(self.target)
        plan = self.tool.preview("init", self.target)
        self.assertTrue(plan["conflicts"])
        with self.assertRaises(BPError): self.tool.apply(plan)
        self.assertEqual(before, tree(self.target))

    def test_empty_existing_skill_directory_not_adopted(self):
        (self.target / ".agents/skills/bp-plan").mkdir(parents=True)
        self.assertTrue(self.tool.preview("init", self.target)["conflicts"])

    def test_override_blocks_install(self):
        (self.target / "AGENTS.override.md").write_text("My override", encoding="utf-8")
        self.assertTrue(self.tool.preview("init", self.target)["conflicts"])

    def test_upgrade_preserves_config_and_tasks(self):
        self.install()
        config = json.loads((self.target / CONFIG).read_text(encoding="utf-8"))
        config["project_name"] = "My custom name"
        config["boundaries"] = ["Keep schema compatible"]
        (self.target / CONFIG).write_bytes(json_bytes(config))
        (self.target / "TASK.md").write_text("task context", encoding="utf-8")
        old_config = (self.target / CONFIG).read_bytes()
        self.change_rule()
        self.tool.release("0.1.1")
        self.tool.apply(self.tool.preview("upgrade", self.target))
        self.assertEqual((self.target / CONFIG).read_bytes(), old_config)
        self.assertEqual((self.target / "TASK.md").read_text(), "task context")
        self.assertEqual(self.tool.check(self.target)["version"], "0.1.1")

    def test_modified_managed_file_blocks_upgrade(self):
        self.install()
        (self.target / ".agents/skills/bp-plan/SKILL.md").write_text("local change", encoding="utf-8")
        before = tree(self.target)
        self.change_rule(); self.tool.release("0.1.1")
        plan = self.tool.preview("upgrade", self.target)
        with self.assertRaises(BPError): self.tool.apply(plan)
        self.assertEqual(before, tree(self.target))

    def test_modified_agents_block_blocks_upgrade(self):
        self.install()
        path = self.target / "AGENTS.md"
        path.write_bytes(path.read_bytes().replace(b"# Codex Best Practice", b"# Local change"))
        self.assertFalse(self.tool.check(self.target)["ok"])

    def test_stale_target_rejected(self):
        plan = self.tool.preview("init", self.target)
        (self.target / "AGENTS.md").write_text("concurrent edit", encoding="utf-8")
        before = tree(self.target)
        with self.assertRaises(BPError): self.tool.apply(plan)
        self.assertEqual(before, tree(self.target))

    def test_tampered_plan_not_executed(self):
        plan = self.tool.preview("init", self.target)
        plan["changes"][0]["content"] = "ZXZpbA=="
        with self.assertRaises(BPError): self.tool.apply(plan)
        self.assertEqual(tree(self.target), {})

    def test_stale_snapshot_rejected(self):
        plan = self.tool.preview("init", self.target)
        snapshot = self.source / "releases/0.1.0/catalog/rules/working-agreements.md"
        snapshot.write_bytes(b"tampered")
        with self.assertRaises(BPError): self.tool.apply(plan)
        self.assertEqual(tree(self.target), {})

    def test_new_release_does_not_silently_change_preview(self):
        plan = self.tool.preview("init", self.target)
        self.change_rule(); self.tool.release("0.1.1")
        self.tool.apply(plan)
        self.assertEqual(self.tool.check(self.target)["version"], "0.1.0")

    def test_cli_from_another_working_directory(self):
        plan_path = self.base / "plan.json"
        command = [sys.executable, str(ROOT / "scripts/codex_bp.py")]
        result = subprocess.run(command + ["preview", "--operation", "init", "--target", str(self.target), "--out", str(plan_path)], cwd=self.base, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertEqual(tree(self.target), {})
        result = subprocess.run(command + ["apply", "--plan", str(plan_path)], cwd=self.base, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        result = subprocess.run(command + ["check", "--target", str(self.target)], cwd=self.base, capture_output=True)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_invalid_settings_and_version_rejected(self):
        for settings in ({"unknown":1}, {"stack":"Python"}, {"enabled_ids":["missing"]}, {"checks":[{"name":"test"}]}):
            with self.subTest(settings=settings):
                with self.assertRaises(BPError): self.tool.preview("init", self.target, settings)
        with self.assertRaises(BPError): self.tool.release("../escape")

    def test_failure_rolls_back_existing_and_created_files(self):
        (self.target / "AGENTS.md").write_bytes(b"Original")
        before = tree(self.target)
        plan = self.tool.preview("init", self.target)
        original_write = core.atomic_write
        calls = 0
        def fail_once(path, data):
            nonlocal calls
            calls += 1
            if calls == 10: raise OSError("simulated disk failure")
            return original_write(path, data)
        with patch.object(core, "atomic_write", side_effect=fail_once):
            with self.assertRaises(BPError): self.tool.apply(plan)
        self.assertEqual(before, tree(self.target))
        self.assertFalse((self.target / ".codex-bp").exists())

    def test_no_release_overwrite_and_semver_order(self):
        snapshot = tree(self.source / "releases/0.1.0")
        with self.assertRaises(BPError): self.tool.release("0.1.0")
        with self.assertRaises(BPError): self.tool.release("0.0.9")
        self.assertEqual(snapshot, tree(self.source / "releases/0.1.0"))

    def test_source_newline_choices_do_not_change_draft(self):
        path = self.source / "catalog/rules/working-agreements.md"
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertFalse(self.tool.draft_diff())
        self.tool.release("0.1.1")
        _, files = self.tool.snapshot("0.1.1")
        self.assertNotIn(b"\r\n", files["catalog/rules/working-agreements.md"])
        self.assertFalse(self.tool.draft_diff())

    def test_concurrent_editor_conflict(self):
        stale = self.tool.catalog()[0]
        self.change_rule()
        with self.assertRaises(BPError): self.tool.save_item(stale)

    def test_create_disable_and_restore(self):
        item = self.tool.save_item({"id":"custom-rule", "kind":"rule", "title":"自定义", "description":"测试", "body":"# Keep it local", "enabled":True})
        self.assertTrue(item["enabled"])
        self.tool.save_item({**item, "enabled":False})
        self.assertFalse(next(i for i in self.tool.catalog() if i["id"] == "custom-rule")["enabled"])
        fingerprint = digest(json_bytes(self.tool.catalog()))
        self.tool.restore_draft("0.1.0", fingerprint)
        self.assertFalse(any(i["id"] == "custom-rule" for i in self.tool.catalog()))
        self.assertFalse(self.tool.draft_diff())

    def test_disabled_item_removed_only_after_upgrade(self):
        self.install()
        item = next(i for i in self.tool.catalog() if i["id"] == "bp-plan")
        self.tool.save_item({**item, "enabled":False})
        self.assertTrue((self.target / ".agents/skills/bp-plan/SKILL.md").exists())
        self.tool.release("0.1.1")
        self.tool.apply(self.tool.preview("upgrade", self.target))
        self.assertFalse((self.target / ".agents/skills/bp-plan/SKILL.md").exists())

    def test_configure_changes_selection_without_new_release(self):
        self.install()
        config = self.tool.check(self.target)["config"]
        config["enabled_ids"].remove("bp-review")
        config["project_name"]="Changed"
        self.tool.apply(self.tool.preview("configure", self.target, config))
        self.assertFalse((self.target / ".agents/skills/bp-review/SKILL.md").exists())
        self.assertEqual(self.tool.check(self.target)["config"]["project_name"], "Changed")

    def test_typescript_detection_never_executes_commands(self):
        (self.target / "package.json").write_bytes(json_bytes({"packageManager":"pnpm@9.0.0", "scripts":{"test":"malicious command", "lint":"eslint ."}}))
        (self.target / "tsconfig.json").write_text("{}")
        detected = self.tool.detect(self.target)
        self.assertEqual(detected["stack"], ["TypeScript"])
        self.assertEqual(detected["checks"][0], {"name":"test", "command":"pnpm run test", "confirmed":False})

    def test_python_and_missing_checks(self):
        (self.target / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths=['tests']\n")
        detected = self.tool.detect(self.target)
        self.assertEqual(detected["stack"], ["Python"])
        self.assertEqual(detected["checks"][0]["command"], "python -m pytest")
        (self.target / "pyproject.toml").unlink()
        self.install()
        self.assertIn("验证命令待补充", self.tool.check(self.target)["notes"])

    def test_path_traversal_rejected(self):
        for relative in ("../outside", "/etc/passwd", "C:/file", ".git/config", "x\\..\\outside"):
            with self.subTest(relative=relative):
                with self.assertRaises(BPError): safe_path(self.target, relative)

    def test_symlink_escape_rejected(self):
        outside = self.base / "outside"; outside.mkdir()
        try: (self.target / ".codex-bp").symlink_to(outside, target_is_directory=True)
        except OSError as exc: self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaises(BPError): self.tool.preview("init", self.target)
        self.assertEqual(tree(outside), {})

    def test_template_references_and_skill_metadata(self):
        self.install()
        for item in self.tool.catalog():
            if item["kind"] != "skill": continue
            fields, body = core.split_skill((self.target / f".agents/skills/{item['id']}/SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual(fields["name"], item["id"])
            for reference in core.re.findall(r"\.codex-bp/templates/[a-z-]+\.md", body):
                self.assertTrue((self.target / reference).exists(), reference)


class ServerTests(ToolkitFixture):
    def setUp(self):
        super().setUp()
        shutil.copytree(ROOT / "web", self.source / "web")
        self.server = LocalServer(self.tool)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, path, data=None, token=True, origin=True, host=None):
        headers={}
        if data is not None:
            headers["Content-Type"]="application/json"
            if token: headers["X-BP-Token"]=self.server.token
            if origin: headers["Origin"]=self.server.origin
        if host: headers["Host"]=host
        req=urllib.request.Request(self.server.origin+path, data=json_bytes(data) if data is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc: return exc.code, exc.read()

    def test_api_registration_preview_apply_and_configure(self):
        status, body=self.request("/api/projects", {"path":str(self.target)})
        self.assertEqual(status, 200); p=json.loads(body)
        status, body=self.request("/api/plans", {"project_id":p["id"], "operation":"init"})
        self.assertEqual(status, 200); plan=json.loads(body)
        self.assertEqual(tree(self.target), {})
        self.assertEqual(self.request(f"/api/plans/{plan['id']}/apply", {})[0],200)
        self.assertEqual(self.request(f"/api/plans/{plan['id']}/apply", {})[0],409)
        status, body=self.request("/api/state")
        self.assertTrue(json.loads(body)["projects"][0]["status"]["installed"])

    def test_api_security_headers_and_unknown_target(self):
        data={"path":str(self.target)}
        self.assertEqual(self.request("/api/projects",data,token=False)[0],403)
        self.assertEqual(self.request("/api/projects",data,origin=False)[0],403)
        self.assertEqual(self.request("/api/state",host="evil.example")[0],403)
        self.assertEqual(self.request("/api/plans",{"operation":"init","project_id":"unknown"})[0],404)
        self.assertEqual(self.request("/%2e%2e/README.md")[0],400)

    def test_api_editor_concurrency_and_release(self):
        item=self.tool.catalog()[0]
        self.assertEqual(self.request("/api/catalog", {**item,"body":item["body"]+"\nChanged"})[0],200)
        self.assertEqual(self.request("/api/catalog",item)[0],409)
        self.assertEqual(self.request("/api/releases",{"version":"0.1.1","catalog_hash":"stale"})[0],409)
        fingerprint=digest(json_bytes(self.tool.catalog()))
        self.assertEqual(self.request("/api/releases",{"version":"0.1.1","catalog_hash":fingerprint})[0],200)


if __name__ == "__main__":
    unittest.main()
