---
name: kk-oled-use
description: 在已经采用 KK_OLED 的工程中实现或排查界面绘图、文字、位图、旋转、动画以及阻塞/IT/DMA 刷新。用于应用层显示需求；平台、总线和控制器接入使用 kk-oled-port，字体子集与缺字使用 kk-oled-font。不要用于与 KK_OLED 无关的 OLED 任务。
license: MIT
metadata:
  author: "Qingdao BaudDance Technology Co., Ltd."
  version: "0.1.0"
  compatibility: "需要访问已经采用 KK_OLED 的目标工程；本 Skill 不携带运行时源码。"
---

# KK_OLED 使用

只依据目标工程实际提供的公共头文件和已链接资源编写应用代码，不假定示例目录、分辨率、字体或硬件平台。

## 工作流程

1. 找到目标工程实际使用的 `kk_oled.h`、实现版本、构建接入、应用显示代码和已有本地修改。阅读公共声明及其注释，不从记忆补出不存在的 API。
2. 明确界面状态、逻辑方向、布局、刷新频率、阻塞限制、字体和位图资源。能从应用代码确认的事实不要重复询问。
3. 完整阅读 [api-semantics.md](references/api-semantics.md)，再组织绘制与刷新。每一帧重画完整场景，并正确处理 Busy、异步最终状态和失败后的恢复。
4. 默认只改应用层显示代码、资源引用和必要构建项。未经明确要求，不修改 graphics、driver、双缓冲/提交语义或公共 API。
5. 使用目标工程确实存在的接口实现坐标、裁剪、旋转、绘图模式、XBM、文字度量和刷新状态机。返回值必须被应用按实际语义处理。
6. 运行目标工程已有的相关测试和构建；只有获得对应设备操作授权时才烧录。分别报告构建结果与屏幕视觉结果。

如果问题源于控制器、地址、总线或传输回调，转用 `kk-oled-port`。如果需要新字形、字体裁剪或 Flash 优化，转用 `kk-oled-font`；只有该 Skill 可用时才显式调用它。
