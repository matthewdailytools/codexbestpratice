from __future__ import annotations

import json
import mimetypes
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .core import BPError, GUARD, Toolkit, digest, json_bytes, safe_path
from .sources import REPOSITORY, for_operation, for_project, github_toolkit


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, toolkit, port=0, cache_dir=None, project_id=None):
        self.toolkit = toolkit
        self.cache_dir = cache_dir
        self.project_id = project_id
        self.token = secrets.token_urlsafe(32)
        self.plans = {}
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def log_message(self, fmt, *args):
        # Avoid local paths and request content in logs.
        pass

    def send(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json_bytes(body)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def validate_host(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            raise BPError("请求 Host 不允许", 403)
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise BPError("拒绝跨站请求", 403)

    def payload(self):
        origin = self.headers.get("Origin")
        if origin != self.server.origin:
            raise BPError("写入仅允许来自本管理台", 403)
        if not secrets.compare_digest(self.headers.get("X-BP-Token", ""), self.server.token):
            raise BPError("会话已过期，请刷新页面", 403)
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise BPError("请求必须使用 application/json", 415)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0 or size > 2_000_000:
                raise BPError("请求过大", 413)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise BPError("请求内容必须为对象")
            return data
        except (ValueError, UnicodeError) as exc:
            raise BPError("无效的 JSON 请求") from exc

    def do_GET(self):
        with GUARD:
            self.handle_get()

    def handle_get(self):
        try:
            self.validate_host()
            path = urlsplit(self.path).path
            tool = self.server.toolkit
            if path == "/api/state":
                items = tool.catalog()
                projects = []
                for item in tool.project_list():
                    try:
                        status = for_project(tool, item["path"], self.server.cache_dir).check(item["path"])
                    except (BPError, OSError, ValueError) as exc:
                        status = {"installed": False, "ok": False, "issues": [str(exc)]}
                    projects.append({**item, "status": status})
                self.send(200, {"token": self.server.token, "catalog": items,
                                "catalog_hash": digest(json_bytes(items)), "projects": projects,
                                "releases": tool.releases(), "next_version": tool.next_version(),
                                "draft_diff": tool.draft_diff(), "toolkit_path": str(tool.root),
                                "repository": REPOSITORY, "project_id": self.server.project_id})
            elif path.startswith("/api/releases/"):
                version = unquote(path.removeprefix("/api/releases/"))
                manifest, _ = tool.snapshot(version)
                self.send(200, {"manifest": manifest, "diff": tool.draft_diff(version)})
            elif path.startswith("/api/"):
                raise BPError("接口不存在", 404)
            else:
                relative = "index.html" if path == "/" else unquote(path.lstrip("/"))
                file = safe_path(tool.root / "web", relative)
                if not file.is_file():
                    raise BPError("文件不存在", 404)
                kind = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                if file.suffix == ".js":
                    kind = "text/javascript"
                self.send(200, file.read_bytes(), kind + ("; charset=utf-8" if kind.startswith("text/") else ""))
        except BPError as exc:
            self.send(exc.status, {"error": str(exc)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.send(500, {"error": f"读取失败: {exc}"})

    def do_POST(self):
        try:
            self.validate_host()
            data = self.payload()
            path = urlsplit(self.path).path
            tool = self.server.toolkit
            with GUARD:
                if path == "/api/catalog":
                    result = tool.save_item(data)
                elif path == "/api/projects":
                    result = tool.register(data.get("path", ""))
                elif path == "/api/detect":
                    target = tool.registered(data.get("project_id"))
                    result = tool.detect(target)
                elif path == "/api/sources/github":
                    selected = github_toolkit(data.get("ref") or "main", self.server.cache_dir)
                    manifest, _ = selected.snapshot(data.get("version"))
                    result = {"source": selected.source, "version": manifest["version"], "catalog": manifest["catalog"]}
                elif path == "/api/plans":
                    target = tool.registered(data.get("project_id"))
                    selected = for_operation(tool, target, data.get("operation"), data.get("source", "github"),
                                             data.get("ref"), self.server.cache_dir)
                    plan = selected.preview(data.get("operation"), target, data.get("settings"), data.get("version"))
                    ident = secrets.token_urlsafe(18)
                    if len(self.server.plans) >= 100:
                        self.server.plans.pop(next(iter(self.server.plans)))
                    self.server.plans[ident] = (selected, plan)
                    result = {**plan, "id": ident}
                elif path.startswith("/api/plans/") and path.endswith("/apply"):
                    ident = path[len("/api/plans/"):-len("/apply")]
                    stored = self.server.plans.get(ident)
                    if not stored:
                        raise BPError("计划不存在或已应用，请重新预览", 409)
                    selected, plan = stored
                    tool.registered(next((p["id"] for p in tool.project_list() if p["path"] == plan["target"]), None))
                    result = selected.apply(plan)
                    del self.server.plans[ident]
                elif path == "/api/releases":
                    if data.get("catalog_hash") != digest(json_bytes(tool.catalog())):
                        raise BPError("规范草稿已变化，请重新查看差异", 409)
                    result = tool.release(data.get("version"))
                elif path == "/api/restore":
                    result = tool.restore_draft(data.get("version"), data.get("catalog_hash"))
                else:
                    raise BPError("接口不存在", 404)
            self.send(200, result)
        except BPError as exc:
            self.send(exc.status, {"error": str(exc)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.send(400, {"error": f"请求无法处理: {exc}"})


def serve(toolkit=None, port=0, open_browser=False, target=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    toolkit = toolkit or Toolkit()
    project_id = toolkit.register(str(target))["id"] if target else None
    server = LocalServer(toolkit, port, project_id=project_id)
    print(f"Codex Best Practice: {server.origin}", flush=True)
    print("仅本机访问。按 Ctrl+C 停止。", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(server.origin)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
