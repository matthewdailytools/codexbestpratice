"""Local-only rules browser and complete-copy editor."""
from __future__ import annotations
import json
import mimetypes
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from .rule_sets import RuleSets
from .storage import BPError, GUARD, ROOT, json_bytes, safe_path

class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, root=ROOT, port=0):
        self.root=Path(root).resolve(); self.store=RuleSets(self.root)
        self.token=secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1",port),Handler)
        self.origin=f"http://127.0.0.1:{self.server_port}"

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def send(self,status,body,kind="application/json; charset=utf-8"):
        if isinstance(body,(dict,list)): body=json_bytes(body)
        if isinstance(body,str): body=body.encode("utf-8")
        self.send_response(status)
        for key,value in {"Content-Type":kind,"Content-Length":str(len(body)),"Cache-Control":"no-store",
            "X-Content-Type-Options":"nosniff", "Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items(): self.send_header(key,value)
        self.end_headers(); self.wfile.write(body)
    def validate_host(self):
        if self.headers.get("Host")!=f"127.0.0.1:{self.server.server_port}" or self.headers.get("Sec-Fetch-Site")=="cross-site": raise BPError("请求来源不允许",403)
    def payload(self):
        if self.headers.get("Origin")!=self.server.origin: raise BPError("写入仅允许来自本工作台",403)
        if not secrets.compare_digest(self.headers.get("X-BP-Token",""),self.server.token): raise BPError("会话已过期，请刷新",403)
        if self.headers.get("Content-Type","").split(";")[0]!="application/json": raise BPError("请求须为 JSON",415)
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size<0 or size>2_000_000: raise BPError("请求过大",413)
            result=json.loads(self.rfile.read(size))
            if not isinstance(result,dict): raise ValueError("请求须为对象")
            return result
        except (ValueError,UnicodeError) as exc: raise BPError("无效 JSON 请求") from exc
    def do_GET(self):
        try:
            self.validate_host(); url=urlsplit(self.path); path=url.path; store=self.server.store
            if path=="/api/sets": self.send(200,{"token":self.server.token,"sets":store.list()})
            elif path.startswith("/api/sets/"):
                parts=path.removeprefix("/api/sets/").split("/"); ident=unquote(parts[0])
                if len(parts)==1: self.send(200,store.describe(ident))
                elif parts[1:]==["file"]: self.send(200,store.read(ident,parse_qs(url.query).get("path",[""])[0]))
                elif parts[1:]==["export"]: self.send(200,store.archive(ident),"application/zip")
                else: raise BPError("接口不存在",404)
            elif path.startswith("/api/"): raise BPError("接口不存在",404)
            else:
                relative="package.html" if path=="/" else unquote(path.lstrip("/"))
                file=safe_path(self.server.root/"web",relative)
                if not file.is_file(): raise BPError("文件不存在",404)
                kind="text/javascript" if file.suffix==".js" else mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                self.send(200,file.read_bytes(),kind+("; charset=utf-8" if kind.startswith("text/") else ""))
        except BPError as exc: self.send(exc.status,{"error":str(exc)})
        except (OSError,ValueError,KeyError,TypeError) as exc: self.send(500,{"error":f"读取失败：{exc}"})
    def do_POST(self):
        try:
            self.validate_host(); data=self.payload(); path=urlsplit(self.path).path
            with GUARD:
                if path=="/api/sets": result=self.server.store.create(data.get("source","default"),data.get("title"))
                elif path.startswith("/api/sets/") and path.endswith("/file"):
                    ident=unquote(path.removeprefix("/api/sets/").removesuffix("/file"))
                    result=self.server.store.save(ident,data.get("path"),data.get("body"),data.get("etag"))
                else: raise BPError("接口不存在",404)
            self.send(200,result)
        except BPError as exc: self.send(exc.status,{"error":str(exc)})
        except (OSError,ValueError,KeyError,TypeError) as exc: self.send(400,{"error":f"操作失败：{exc}"})

def serve(root=ROOT,port=0,open_browser=False):
    import sys
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    server=LocalServer(root,port)
    print(f"Codex Best Practice: {server.origin}",flush=True)
    print("默认规范只读；新建整套副本后编辑。仅本机访问。",flush=True)
    if open_browser: webbrowser.open(server.origin)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
