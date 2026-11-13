# 十四、按项目类型采用适用规范

从用户目标、仓库工程和实际部署形态选择技术方案，不根据 agent 当前操作系统推断目标平台。跨端与全栈任务组合使用相关技能，不加载无关平台。

| 实际交付目标 | 对应技能 |
| --- | --- |
| 网站、浏览器应用，含手机和平板浏览器 | `.agents/skills/bp-ui-web/SKILL.md` |
| iPhone 原生应用 | `.agents/skills/bp-ui-ios/SKILL.md` |
| iPad 原生应用 | `.agents/skills/bp-ui-ipados/SKILL.md` |
| Android 应用 | `.agents/skills/bp-ui-android/SKILL.md` |
| Windows 桌面应用 | `.agents/skills/bp-ui-windows/SKILL.md` |
| macOS 桌面应用 | `.agents/skills/bp-ui-macos/SKILL.md` |
| 后端服务、API、数据或后台任务 | `.agents/skills/bp-backend/SKILL.md` |

依据项目支持版本核实平台 API 与设计规范，沿用已有框架。新项目选择足够完成首版且可维护的方案，不默认套用固定分层、数据库或云服务。

验证区分静态检查、浏览器实测、模拟器／设备、真实集成和生产运行。平台方案不能冒充原生构建或真机验证；不可用环境明确记录限制。
