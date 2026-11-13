---
name: "bp-ui-android"
description: "为 Android 应用制定或实现 UI、系统返回、自适应布局和无障碍交互；不将此规范套用于 iOS 或仅运行在 Android 浏览器中的网站。"
---

# Android UI 与交互

核实 minSdk、targetSdk、现有 Compose／Views／跨平台工程和品牌。沿用项目设计系统，合适时使用 Material 组件；系统行为按支持版本核实，不能因采用新样式擅自替换工具链。

- 明确信息层级、主要屏幕、主要操作和组件视觉状态，统一文字、颜色和间距。导航依据当前可用窗口空间适配底部导航、侧栏或列表详情，不以设备型号硬编码一套布局。
- 保持系统返回、应用内向上导航和任务栈含义一致；按目标版本处理预测性返回。覆盖旋转、窗口变化、前后台与进程重建，区分短期界面状态和需要持久化的业务数据。
- 处理系统栏、edge-to-edge、安全 inset、屏幕切口与输入法；不要让键盘遮挡当前字段或提交入口。触控目标至少 48 dp，邻近操作留有间隔。
- 支持字体缩放、TalkBack 语义与合理焦点顺序，图标操作有可访问名称；深浅色与对比度不依赖单一颜色表示状态。手势、拖动和长按的重要功能提供可发现的替代入口。
- 加载、空内容、错误、权限拒绝、离线和恢复应有明确反馈，保留输入且避免重复提交。按使用场景请求权限，优先现有系统选择器和最少必要权限。
- 按产品支持范围测试手机、可调整窗口与适用的大屏／折叠布局、字体缩放、返回和状态恢复。未具备 Android 构建、模拟器或设备时明确尚未验证的行为，不能把浏览器原型称作 Android 原生应用已验收。

依据：[Android 自适应应用质量](https://developer.android.com/docs/quality-guidelines/adaptive-app-quality)、[Android 核心质量与触控](https://developer.android.com/develop/adaptive-apps/quality-guidelines/core-app-quality)。仅采用与产品形态相关的要求。
