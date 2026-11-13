# 开发与接口说明

## 结构与单一来源

`scripts/codexbp/core.py` 实现文件保护、目录、版本、识别与接入；`server.py` 暴露 HTTP API；`scripts/codex_bp.py` 提供 CLI；`web/` 是无构建前端。

索引为 `catalog/index.json`；规则原文在 `catalog/rules/`，Skills 在 `.agents/skills/`，模板在 `.codex-bp/templates/`。界面直接编辑源文件，没有数据库副本。

Skill frontmatter 仅支持 `name`、`description`，值为 JSON 双引号字符串（有效 YAML 标量）。界面自动生成；首版不提供任意外部 YAML Skill 导入和附属脚本打包。

版本在 `releases/<版本>/`，包含源文件与 `manifest.json`。新增版本统一使用 LF；草稿比较忽略纯换行差异。历史快照保留原始字节，通过 `.gitattributes` 禁止 Git 换行转换。哈希能发现普通文件篡改；不是签名验证，不能防御同时改写快照和清单的本机恶意程序。

本机目录登记在 `.local/projects.json`。Web 计划仅在服务内存中，最多 100 项，重启后重新预览。CLI 计划保存到目标目录之外。

## CLI 配置

`python scripts/codex_bp.py --help` 列出命令。除 `serve` 外输出 UTF-8 JSON；`preview --out` 直接保存 UTF-8，避免终端重定向编码差异。

`--settings` 接受可选字段，参考 `examples/project-settings.json`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `project_name` | 非空字符串 | 项目显示名 |
| `stack` | 字符串数组 | 技术栈 |
| `checks` | 对象数组 | 每项含 `name`、`command`、可选布尔 `confirmed` |
| `boundaries` | 字符串数组 | 修改约定，不是运行环境权限 |
| `enabled_ids` | 字符串数组 | 对应版本的已启用规范；首次省略时采用全部启用项 |

`configure` 固定当前版本，只改变配置和启用选择；`upgrade` 默认使用最新版本，`--version` 可指定不低于当前版本的已有版本。重复 `init` 固定已有版本，未传设置时应无文件变更。

退出码：0 成功；2 输入、冲突或未接入；1 I/O 等执行失败。`check` 的 notes 是非阻塞提醒。

## 本地 HTTP API

仅监听 IPv4 回环地址，默认端口由操作系统分配。Host 必须匹配服务地址。写请求须携带同源 `Origin`、`application/json` 和 `/api/state` 返回的 `X-BP-Token`。

| 方法与路径 | 请求／返回 |
| --- | --- |
| `GET /api/state` | 目录及 etag、项目状态、版本、草稿差异、会话令牌 |
| `POST /api/catalog` | `{id,title,kind,description,body,enabled,etag?}`；编辑需旧 etag |
| `POST /api/projects` | `{path}` 登记已有目录，返回项目 id |
| `POST /api/detect` | `{project_id}` 返回技术栈与命令建议 |
| `POST /api/plans` | `{project_id,operation,settings?,version?}` 返回配置、冲突、差异、计划 id |
| `POST /api/plans/<id>/apply` | `{}` 应用并消费对应计划 |
| `GET /api/releases/<version>` | 快照清单及当前草稿相对该版本差异 |
| `POST /api/releases` | `{version,catalog_hash}` 创建本地版本 |
| `POST /api/restore` | `{version,catalog_hash}` 复制历史内容为草稿 |

错误为 `{error: string}`：输入 400、来源／令牌 403、未知对象 404、过期／冲突 409、读取写入故障 500。项目 API 只接受已登记项目 id。

## 文件保护与实际边界

- 路径限制在指定根目录，拒绝路径穿越、`.git`、符号链接及 junction/reparse-point 受管路径。
- 写入前核对计划、快照与目标哈希。`AGENTS.md` 按字节区间替换，保留区块外内容与 BOM。
- 单文件使用同目录临时文件与 `os.replace`；异常时恢复已改内容，最后写入接入记录。
- 同一服务进程串行化读写。首版无跨进程文件锁，不要同时从多个管理台／CLI 写同一目录。
- 恢复处理进程仍运行时的写入异常；断电或强制终止不保证多文件事务原子性。项目仍应使用 Git 管理。
- 不提供远程访问、账号和权限系统。预览不执行原始 HTML，图片显示占位文字，不加载外部资源。

## 开发检查

```bash
python -m unittest discover -s tests -v
```

前端另用 `node --check web/app.js` 做开发检查（使用者运行管理台不需要 Node）。浏览器回归使用隔离工具仓库与临时项目，不污染真实版本。

Skill 元数据可使用 Codex 自带 `skill-creator/scripts/quick_validate.py` 检查；其 PyYAML 是开发检查环境依赖，不是本项目运行依赖。实际结果见 `VALIDATION.md`。
