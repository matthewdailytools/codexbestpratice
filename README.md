# Codex Best Practice

一套可直接复制到 Codex 项目根目录的工程规范，配有本地浏览、整套复制和正文编辑界面。

默认规范集中在 [default/](default/)，共 **49 个文件**。界面与 API 对默认原件保持只读；需要修改时，新建一套完整副本后编辑保存。

## 在 Codex 工程中引用

在**目标项目**的 Codex 对话中发送以下 Prompt，让 Codex 自动获取并引入规范，无需手动复制文件：

```text
请为当前工程引入下面仓库的默认 Codex 工程规范：
https://github.com/matthewdailytools/codexbestpratice

请直接完成以下工作：
1. 检查当前工程根目录、AGENTS.md、已有技能、项目配置与 Git 状态，保留现有约定和用户修改。
2. 将来源仓库获取到当前工程之外的临时目录，固定本次来源 commit；阅读 README.md、default/VERSION_NOTES.md 和 default/.codex-bp/manifest.json，核对文件清单及哈希。
3. 将 default/ 里面的全部规范内容引入当前工程根目录，包括 AGENTS.md、VERSION_NOTES.md、.agents/ 和 .codex-bp/。不要在工程内再套一层 default/，也不要复制工作台源码、测试或历史资料。
4. 已有同名文件先比较：相同内容直接保留；可明确合并的内容安全合并，不删除原规则；存在无法判断的冲突时保留原文件，集中说明冲突及待决事项，不覆盖或假报接入完成。
5. 根据真实工程补齐 .codex-bp/project.json 中的项目名称、技术栈、边界和验证入口。能从代码查证的直接查证，未知信息保留待补齐；confirmed 仅表示命令入口已核实，不表示测试已通过。
6. 检查文件引用与技能名称，验证未合并文件与来源一致，说明合并差异。具备 Codex 技能扫描能力时确认项目内技能的路径与作用域；否则明确尚未验证发现结果。实际任务中按需读取规则及对应平台／后端技能。

本次仅引入并检查规范，不开发业务、不修改全局 Codex 配置、不自动安装业务依赖或配置 MCP/CI，也不提交、推送或部署。不要要求我手动 clone、复制文件或执行命令；遇到真实权限、网络或合并阻塞时说明具体原因。

完成后简要报告来源 commit、引入及合并的文件、实际检查结果、未解决冲突和后续使用方式。区分文件存在、技能发现、模型读取和实际行为遵循，不能把复制成功当作所有规范已被模型验证。说明需要在目标项目开启新的 Codex 运行加载项目指引。
```

这段 Prompt 使用的是当前的 `default/` 文件包，不依赖旧版远程安装器。若希望自己操作，也可按下一节直接复制。

## 使用默认规范

1. 获取本仓库，将 `default/` **里面的全部内容**复制到目标项目根目录，包含 `.agents/` 和 `.codex-bp/` 隐藏目录。不要只把 `default/` 文件夹放进项目。
2. 已有同名文件时先比较合并，保留原有 `AGENTS.md`、技能、项目配置和用户修改。
3. 在目标项目开启新的 Codex 运行，先核对项目事实，再根据真实工程补齐 `.codex-bp/project.json` 的技术栈、边界和验证入口。

复制后的结构：

```text
你的项目/
├── AGENTS.md                 # 精简入口与规则索引
├── VERSION_NOTES.md          # 使用说明、设计取舍和验证边界
├── .agents/skills/           # 13 个流程、平台与后端技能
└── .codex-bp/
    ├── rules/               # 按参考文章顺序排列的 14 章规则
    ├── prompts/             # 12 份可复制的任务 Prompt
    ├── templates/           # 6 类任务产物记录模板
    ├── project.json         # 项目事实与实际验证入口
    └── manifest.json        # 文件清单、导航和完整性哈希
```

复制提供项目指引和按需技能，不会安装语言环境、依赖、MCP 或 CI，也不会修改全局 Codex 配置。配置中的空列表或 `confirmed` 状态不表示检查已执行或通过。

## 浏览和修改

在本仓库根目录运行，要求 **Python 3.11+**，仅使用标准库，无需安装依赖或构建前端：

```powershell
python workbench.py --open
```

终端会显示本机地址，端口自动分配；也可通过 `--port 50501` 指定端口。关闭服务使用 `Ctrl+C`。

- **阅读默认规范**：按 14 章分层导航，优先显示实际规则正文；版本说明独立展示。
- **新建一套**：复制当前完整规范，在自定义副本中修改规则、技能、Prompt、配置和版本说明。
- **编辑正文**：实时预览并保存，刷新后保留；过期编辑会被拒绝，避免覆盖其他页面的新内容。
- **复制 Prompt**：打开模板后直接复制全文，按实际任务填写输入。
- **下载整套文件**：导出可直接解压到项目根目录的 ZIP，包含隐藏目录；解压到已有项目时仍需处理同名文件。

自定义副本保存在本机 `.local/rule-sets/`，不纳入 Git；需要备份或共享时导出整套文件。默认原件的文件清单由程序校验，直接在磁盘修改原件会导致完整性检查拒绝。

## 规则与 Prompt

规则按参考文章顺序组织：整体工作流、项目初始化、需求分析、里程碑与任务拆分、统一任务执行、测试策略、多 Agent、Git、安全权限、Skills/MCP/自动化、日常节奏与交接、常见错误、完成标准、项目类型适配。

第五章包含全部 **12 份 Prompt**；第二章也提供项目分析入口：

- [项目分析](default/.codex-bp/prompts/project-analysis.md)、[完整开发任务](default/.codex-bp/prompts/full-task.md)
- [需求分析](default/.codex-bp/prompts/requirements.md)、[架构规划](default/.codex-bp/prompts/architecture.md)、[项目初始化](default/.codex-bp/prompts/project-setup.md)、[任务拆分](default/.codex-bp/prompts/planning.md)
- [编码实现](default/.codex-bp/prompts/implementation.md)、[自动化验证](default/.codex-bp/prompts/verification.md)、[代码审查](default/.codex-bp/prompts/review.md)、[交付发布](default/.codex-bp/prompts/delivery.md)
- [续接与交接](default/.codex-bp/prompts/handoff.md)、[复盘与规范改进](default/.codex-bp/prompts/retrospective.md)

原文的项目分析、任务规划、编码实现和代码审查已融入模板，其余阶段沿用相同的输入、执行要求、输出和验收结构补齐。`prompts/` 用于发起任务，`templates/` 用于记录产物；小任务不强制套完整流程，单阶段模板也不自动授权后续实现或发布。

复制步骤和适用边界详见 [VERSION_NOTES.md](default/VERSION_NOTES.md)。

## 检查

后端与文件包回归使用 Python 标准库；JavaScript 语法检查需要 Node.js，运行工作台不需要 Node.js：

```powershell
python -m unittest discover -s tests -v
node --check web/package.js
```

当前记录：**8 项自动化回归通过，13 个技能被真实 Codex CLI 发现，7 项真实模型任务完成并通过**。项目分析 Prompt 的单独模型测试受账户额度限制，未完成，不计为通过；其余未抽测模板也不宣称已通过模型行为测试。

详细结果、模型配置与限制见 [VALIDATION.md](VALIDATION.md)。原始模型轨迹、浏览器截图和本机归档保存在被 Git 忽略的 `.local/`，不会随仓库推送；报告中的这些本机证据链接仅在原验证环境可用。

旧接入、升级和版本管理方案已退出当前工作台；已提交历史可从 Git 记录查看，本机旧资料另保留在 `.local/archive/`。
