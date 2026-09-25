# Carrier32 展示版交付

本工程供原理图、PCB 布局及 3D 外观展示，不作为制板或装配文件。板框为 360 × 260 mm，图纸已扩大至 A3（原理图）和 A2（PCB）。

## 内容

- 传感器接口共 32 路：SHT30 ×4、液位 ×5、MQ-2 ×5、MQ-4 ×5、MQ-7 ×5、氧气 ×3、火焰 ×5；无 DHT11。每路使用 4 位 JST XH 载板接口。
- 双 STM32F103RCT6 模块座、ESP-01S ×2、ST7735S ×2、B 型摇杆、12 V/0.2 A 四线风扇 ×2、INA226 ×2、继电器、蜂鸣器、WS2812 ×18 均有原理图符号和 PCB 封装。
- PCB 共 118 个封装。多数封装使用 KiCad 标准 3D 模型；两块 STM32 模块板和两块 ST7735S 屏幕使用项目内的外观示意模型（`3dmodels/`），不是实测机械模型。`Carrier32:LMR51450_visual_13pin` 是 13 焊盘外观占位封装，不表示真实器件的生产封装。
- `build/demo/carrier32-preview.glb` 是 KiCad 导出的 3D 预览；在 PCB 编辑器中也可按 `Alt+3` 打开 3D 查看器。
- `build/demo/module-overview.svg`（及同名 PNG）是双 STM32 模块与双 ST7735S 屏幕的放大可读视图，标注按当前原理图的针号和网络标签自动生成；其源脚本是 `scripts/render_module_overview.py`。原理图仍以 `carrier32.kicad_sch` 为准，该视图不替代电气原理图。

## 检查边界

2026-09-23 保存状态：ERC 0 个错误、65 个警告（63 个网格端点、2 个孤立标签）；PCB DRC 0 个几何/间距违规、0 个原理图一致性问题、327 个未布线连接。后者意味着不能将此板视为电气完成或可制板设计。详细报告位于 `build/demo/carrier32-erc.rpt` 与 `build/demo/carrier32-drc.rpt`。

若只为展示外观，自动布线不是查看 3D 模型的前提。若要改善二维走线观感，KiCad 10 可对选中焊盘使用 `Shift+F` 尝试逐条完成；全板自动布线可通过 Freerouting 的 DSN/SES 工作流完成。应在板文件副本上运行，并重新检查未连接数和 DRC。当前模块座与电源芯片包含外观占位映射，自动布线结果不应解释为实物针位或电气可靠性验证。
