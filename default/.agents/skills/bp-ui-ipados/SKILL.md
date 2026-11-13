---
name: "bp-ui-ipados"
description: "为 iPad 原生应用制定或实现自适应多栏、窗口、多任务和触控键盘交互；在 iPad 浏览器中的网站应使用 Web 规范。"
---

# iPadOS UI 与交互

确认目标为 iPad 原生应用，核实最低系统版本、现有工程和使用场景。以当前窗口可用空间组织任务，保持 iPad 的交互习惯；不直接把 iPhone 页面等比放大。

- 规划侧栏、列表详情、多栏内容与主要操作，窗口变窄时合理折叠并保留当前选择、输入和导航上下文。横竖屏、系统安全区域和软键盘变化不得遮住核心内容或操作。
- 根据支持版本和产品范围处理窗口调整、多任务及适用的多窗口，保持文档与编辑状态一致；不锁死全屏来绕过布局问题，也不为简单任务强行加入多窗口。
- 触控可独立完成主要流程，控件优先采用 44×44 pt 的舒适触控尺寸；支持硬件键盘、快捷键、指针和焦点操作。拖放、悬停或 Pencil 功能须有适用场景，重要操作提供可发现替代入口。
- 统一视觉层级、语义颜色、文字、间距和组件状态，利用大屏呈现相关内容并控制信息密度。支持 Dynamic Type、VoiceOver、深浅主题、对比度与减少动态效果。
- 明确加载、空内容、失败、离线、权限拒绝与恢复，编辑时保留输入；同步或跨窗口操作处理冲突与重复提交，不将模拟数据表现成真实保存。
- 验证窄窗口、多栏切换、方向变化、键盘弹出、外接键盘、VoiceOver 和适用的窗口状态恢复。报告实际构建／模拟器／设备证据；只有响应式网页不能宣称原生应用已完成。

依据：[Apple iPadOS HIG](https://developer.apple.com/design/human-interface-guidelines/designing-for-ipados)、[Apple 布局](https://developer.apple.com/design/human-interface-guidelines/layout)、[Apple 可访问性](https://developer.apple.com/design/human-interface-guidelines/accessibility)。
