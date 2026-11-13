#!/usr/bin/env python3
"""Run from any working directory; Python 3.11+, no pip installation."""
import argparse
import json
import sys
from pathlib import Path

from codexbp.core import BPError, Toolkit, json_bytes, load_json
from codexbp.sources import for_operation, for_project, for_record, github_toolkit


def main():
    parser = argparse.ArgumentParser(description="Codex Best Practice 本地规范管理与项目接入")
    subs = parser.add_subparsers(dest="command", required=True)
    server = subs.add_parser("serve", help="启动本地管理台")
    server.add_argument("--open", action="store_true", help="打开浏览器")
    server.add_argument("--port", type=int, default=0, help="默认自动分配空闲端口")
    server.add_argument("--target", type=Path, help="由工作台入口自动登记并选中当前项目")
    preview = subs.add_parser("preview", help="生成只读变更计划，JSON 输出到标准输出")
    preview.add_argument("--operation", choices=("init", "upgrade", "configure"), required=True)
    preview.add_argument("--target", required=True)
    preview.add_argument("--settings", type=Path)
    preview.add_argument("--version")
    preview.add_argument("--source", choices=("github", "local"), default="github", help="默认从 GitHub 获取工作台规范")
    preview.add_argument("--ref", help="GitHub 分支、标签或 commit；预览后固定 commit")
    preview.add_argument("--cache-dir", type=Path)
    preview.add_argument("--out", type=Path, help="可选：计划保存到目标项目之外")
    apply = subs.add_parser("apply", help="应用已预览并确认的计划")
    apply.add_argument("--plan", type=Path, required=True)
    check = subs.add_parser("check", help="检查接入状态与本地修改")
    check.add_argument("--target", required=True)
    release = subs.add_parser("release", help="从草稿创建不可变本地版本")
    release.add_argument("--version", required=True)
    args = parser.parse_args()
    try:
        tool = Toolkit()
        if args.command == "serve":
            from codexbp.server import serve
            serve(tool, args.port, args.open, args.target)
            return 0
        if args.command == "preview":
            selected = for_operation(tool, args.target, args.operation, args.source, args.ref, args.cache_dir)
            result = selected.preview(args.operation, args.target, load_json(args.settings) if args.settings else None, args.version)
            if args.out:
                if args.out.resolve().is_relative_to(Path(args.target).resolve()):
                    raise BPError("为保持预览只读，请将计划保存到目标项目目录之外")
                args.out.write_bytes(json_bytes(result))
        elif args.command == "apply":
            plan = load_json(args.plan)
            result = for_record(tool, plan.get("source")).apply(plan)
        elif args.command == "check":
            result = for_project(tool, args.target).check(args.target)
        else:
            result = tool.release(args.version)
        sys.stdout.buffer.write(json_bytes(result))
        return 2 if result.get("conflicts") or result.get("ok") is False else 0
    except (BPError, OSError, ValueError, KeyError, TypeError) as exc:
        sys.stderr.buffer.write(json_bytes({"error": str(exc)}))
        return 2 if isinstance(exc, BPError) and exc.status < 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
