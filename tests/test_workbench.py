import contextlib
import io
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import workbench
from codexbp.core import BPError, LOCK, Toolkit
from codexbp import sources


def archive(extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        for relative in ("README.md", "WORKBENCH.md", "workbench.py", "scripts", "web", "catalog", ".agents", ".codex-bp", "releases"):
            path = ROOT / relative
            candidates = [path] if path.is_file() else path.rglob("*")
            for candidate in candidates:
                if candidate.is_file() and "__pycache__" not in candidate.parts:
                    z.write(candidate, "workbench-main/" + candidate.relative_to(ROOT).as_posix())
        if extra:
            name, value = extra
            if isinstance(name, zipfile.ZipInfo):
                z.writestr(name, value)
            else:
                z.writestr(name, value)
    return output.getvalue()


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = archive()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="workbench-test-")
        self.addCleanup(self.temporary.cleanup)
        self.cache = Path(self.temporary.name) / "cache"
        self.target = Path(self.temporary.name) / "project"
        self.target.mkdir()
        self.commit = "a" * 40

    def fetch(self):
        with patch.object(workbench, "_download", side_effect=[json.dumps({"sha":self.commit}).encode(), self.package]) as download:
            result = workbench.fetch_workbench(cache_dir=self.cache)
        return result, download

    def test_entire_workbench_fetch_and_pinned_cache_reuse(self):
        info, download = self.fetch()
        self.assertEqual(download.call_count, 2)
        self.assertEqual(info["source"]["commit"], self.commit)
        self.assertTrue((Path(info["toolkit_path"]) / "web/app.js").exists())
        self.assertTrue((Path(info["toolkit_path"]) / "workbench.py").exists())
        with patch.object(workbench, "_download", side_effect=AssertionError("cache must not download")):
            cached = workbench.fetch_workbench(self.commit, self.cache)
        self.assertEqual(info, cached)
        self.assertFalse(list(self.target.iterdir()))

    def test_cache_code_or_published_snapshot_modification_rejected(self):
        info, _ = self.fetch()
        (Path(info["toolkit_path"]) / "scripts/codex_bp.py").write_text("changed", encoding="utf-8")
        with self.assertRaises(workbench.WorkbenchError):
            workbench.fetch_workbench(self.commit, self.cache)

    def test_branch_update_uses_new_cache_without_changing_old(self):
        first, _ = self.fetch()
        other = "b" * 40
        with patch.object(workbench, "_download", side_effect=[json.dumps({"sha":other}).encode(), self.package]):
            second = workbench.fetch_workbench(cache_dir=self.cache)
        self.assertNotEqual(first["toolkit_path"], second["toolkit_path"])
        self.assertTrue(Path(first["toolkit_path"]).exists())

    def test_archive_traversal_and_symlinks_rejected(self):
        link = zipfile.ZipInfo("workbench-main/link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for extra in (("workbench-main/../../escape", "bad"), (link, "../outside")):
            with self.subTest(extra=str(extra[0])):
                with patch.object(workbench, "_download", return_value=archive(extra)):
                    with self.assertRaises(workbench.WorkbenchError):
                        workbench.fetch_workbench(self.commit, self.cache)
                self.assertFalse((self.cache / self.commit).exists())

    def test_fetch_failure_never_falls_back_to_local(self):
        with patch.object(sources, "fetch_workbench", side_effect=workbench.WorkbenchError("network unavailable")):
            with self.assertRaises(BPError) as caught:
                sources.for_operation(Toolkit(), self.target, "init")
        self.assertEqual(caught.exception.status, 502)
        self.assertFalse(list(self.target.iterdir()))

    def test_transient_read_failure_retries_once(self):
        response = io.BytesIO(b"downloaded")
        with patch.object(workbench.urllib.request, "urlopen", side_effect=[OSError("temporary"), response]) as request:
            self.assertEqual(workbench._download("https://api.github.com/test", 100), b"downloaded")
            self.assertEqual(request.call_count, 2)
        with patch.object(workbench.urllib.request, "urlopen", side_effect=OSError("offline")) as request:
            with self.assertRaises(workbench.WorkbenchError):
                workbench._download("https://api.github.com/test", 100)
            self.assertEqual(request.call_count, 2)

    def test_github_source_recorded_and_configure_keeps_commit(self):
        info, _ = self.fetch()
        tool = Toolkit(info["toolkit_path"], source=info["source"], allowed_versions=info["versions"])
        plan = tool.preview("init", self.target)
        tool.apply(plan)
        lock = json.loads((self.target / LOCK).read_text(encoding="utf-8"))
        self.assertEqual(lock["source"], info["source"])
        self.assertNotIn("toolkit_path", lock["source"])
        with patch.object(sources, "github_toolkit", return_value=tool) as fetch:
            sources.for_operation(Toolkit(), self.target, "configure")
            fetch.assert_called_once_with(self.commit, None)

    def test_cache_local_release_not_misrepresented_as_github(self):
        info, _ = self.fetch()
        local = Toolkit(info["toolkit_path"])
        local.release("9.0.0")
        remote = Toolkit(info["toolkit_path"], source=info["source"], allowed_versions=info["versions"])
        self.assertNotEqual(remote.latest(), "9.0.0")
        with self.assertRaises(BPError): remote.snapshot("9.0.0")
        with self.assertRaises(BPError): remote.release("9.0.1")

    def test_default_prompt_entry_applies_and_verifies_without_git(self):
        info, _ = self.fetch()
        output = SimpleNamespace(buffer=io.BytesIO(), flush=lambda: None)
        with patch.object(workbench, "fetch_workbench", return_value=info), \
             patch.object(sys, "argv", ["workbench.py", "--target", str(self.target)]), \
             patch.object(sys, "stdout", output), patch.object(sys, "path", sys.path.copy()), \
             patch.object(workbench.subprocess, "call", side_effect=AssertionError("Git/shell is not needed")):
            self.assertEqual(workbench.main(), 0)
        text = output.buffer.getvalue().decode("utf-8")
        self.assertIn('"ok": true', text)
        self.assertTrue((self.target / ".agents/skills/bp-setup/SKILL.md").exists())
        self.assertEqual(json.loads((self.target / LOCK).read_text())["source"]["commit"], self.commit)

    def test_guided_mode_requires_collected_settings_before_fetch(self):
        error = SimpleNamespace(buffer=io.BytesIO())
        with patch.object(workbench, "fetch_workbench") as fetch, \
             patch.object(sys, "argv", ["workbench.py", "--mode", "guided", "--target", str(self.target)]), \
             patch.object(sys, "stderr", error):
            self.assertEqual(workbench.main(), 1)
            fetch.assert_not_called()
        self.assertFalse(list(self.target.iterdir()))


if __name__ == "__main__":
    unittest.main()
