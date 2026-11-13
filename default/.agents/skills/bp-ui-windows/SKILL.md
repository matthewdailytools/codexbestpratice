---
name: "bp-ui-windows"
description: "为 Windows 桌面应用制定或实现窗口、键盘鼠标、Fluent 交互与可访问性验收；不因 agent 运行在 Windows 就用于其他目标平台。"
---

# Windows 桌面 UI 与交互

先核实目标 Windows 版本、工程框架和用户任务。沿用 WinUI、WPF、Qt、Electron 等既有选择；原生组件与 Fluent 习惯应结合现有产品采用，不为了统一外观强制迁移框架。

- 规划窗口、导航、工具栏、内容区域与高频操作，统一文字层级、语义颜色、间距和密度。避免把移动端单列界面机械放大，或用自绘标题栏破坏系统移动、调整大小和窗口管理。
- 核心流程支持鼠标与完整键盘操作；Tab／Shift+Tab、方向键、Enter、Escape 行为符合控件语义，焦点清楚且无陷阱。高频命令提供可发现的快捷键，尊重系统保留快捷键，右键菜单不能是唯一入口。
- 适配窗口缩放、多显示器和不同 DPI，验证窄窗口下导航与内容仍可用。保持合理最小尺寸；平台支持触摸时不能只有悬停才出现的关键操作。
- 使用可访问名称、角色和状态，检查 Narrator、系统文字缩放、对比主题、深浅色及减少动态效果。自定义控件补足 UI Automation 语义，不能只凭截图判断无障碍。
- 有文件编辑时明确保存、撤销、未保存退出和恢复行为，优先系统文件选择器；耗时任务提供进度、取消或清晰等待状态，避免阻塞窗口线程。
- 验证键盘全流程、弹窗焦点往返、调整大小、DPI 与主题切换、失败重试和任务恢复。报告实际运行框架与检查结果；未运行原生应用时如实保留限制。

依据：[Windows 设计](https://learn.microsoft.com/en-us/windows/apps/design/)、[键盘交互](https://learn.microsoft.com/en-us/windows/apps/develop/input/keyboard-interactions)、[可访问性检查](https://learn.microsoft.com/en-us/windows/apps/design/accessibility/accessibility-checklist)。
