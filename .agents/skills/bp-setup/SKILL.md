---
name: "bp-setup"
description: "为项目接入、配置或升级 Codex Best Practice；支持快速确认和引导设置。"
---

# 项目接入与设置

用于首次接入、更改项目配置、检查状态或按需升级。不要将普通编码请求误判为接入请求。

## 定位与检查

1. 从用户给出的路径定位模板仓库，确认其 README.md、scripts/codex_bp.py 与 releases/；如果当前位置就是工具仓库可直接使用。已安装的本技能不会自动带来整个工具仓库；找不到时只询问工具仓库位置。
2. 明确用户指定的目标目录；读取现有 AGENTS.md、AGENTS.override.md、清单、锁文件及有关规则。不要修改全局 Codex 配置。
3. 调用 `python <工具仓库>/scripts/codex_bp.py check --target <目标目录>`。尚未接入是正常结果，退出码 2 不代表工具损坏。

## 两种设置方式

- 快速确认：从项目清单与脚本推导推荐配置，列出推导来源；未验证的命令使用 confirmed=false，找不到时留空并注明待补充。
- 引导设置：依次收集项目名称、技术栈、验证命令、修改边界、启用项；收集答案期间不写目标项目。不要询问能从仓库确定的事实。
- 用户未指定时使用快速确认。可调用 `serve --open` 使用管理台完成同一流程。

## 一次确认后应用

配置 JSON 字段为 project_name、stack（字符串列表）、checks（name/command/confirmed 的列表）、boundaries（字符串列表）、enabled_ids（从对应版本目录选择，可省略）。confirmed 仅表示命令已核实可用，不表示已执行或已通过。

将设置与预览计划保存在系统临时目录，调用：

```text
python <工具仓库>/scripts/codex_bp.py preview --operation init --target <目标目录> --settings <临时设置.json> --out <临时计划.json>
```

升级使用 operation=upgrade；只调整配置用 configure。路径作为独立参数传递。先检查退出码与 conflicts，展示实际文件差异、配置、版本及待补充内容；有冲突时不尝试强制覆盖。展示完成后请求一次最终确认；用户已经明确批准完全相同的具体预览时不重复询问。

确认后调用 `apply --plan <临时计划.json>`。若文件已变化或版本被修改，重新预览实际差异后再确认，不自动重试写入。最后调用 check 并报告结果和日常技能入口。不执行项目命令，不自动提交或推送；若用户另行授权则遵循其授权。
