# Carrier32 KiCad 工程

本目录实现 `docs/superpowers/specs/2026-09-22-dual-node-32-sensor-carrier-design.md`。

## 工具链

- KiCad 10.0.5：`D:\KiCad\bin\kicad-cli.exe`
- Python 3：设计输入、网络合同及制造包检查脚本
- PowerShell：统一检查入口 `scripts/run_checks.ps1`

已安装的辅助能力包括 `kicad-tool`、`kicad-workflow`、
`kicad-sch-cleanup-loop`、`manage-pcba-program`、
`qualify-pcba-sourcing`、`design-and-review-circuit`、
`schematic-humanizer`、`pcb-layout-review`、
`release-pcba-fabrication`，以及 kicad-happy 的 `kicad`、`emc`、`bom`。
这些能力从下一轮 Codex 技能加载起可用。

## 运行检查

仅检查本机工具和工程骨架：

```powershell
powershell -ExecutionPolicy Bypass -File hardware/carrier32/scripts/run_checks.ps1 -Preflight
```

目前已经建立受保护的 12 V 输入、两路独立 5 V 降压和两路 ESP 3.3 V
电源原理图草稿，见 [电源审查记录](docs/power-review.md)。`scripts/check_power_nets.ps1`
对电源网表执行 80 项引脚映射断言；当前 ERC 为 0 错误、10 个尚未接到后续接口的警告。
导出的图面仍拥挤且标题栏未清理，因此尚未通过视觉审查。

32 个传感器数量和 MCU 引脚分配已锁定在 `config/net-contract.csv`，
不包含 DHT11。载板端 32 个统一四针传感器接口及线束边界见
[参考接口标准](docs/reference-interface-standard.md)和 `config/connector-contract.csv`；
运行 `python hardware/carrier32/scripts/check_connector_contract.py hardware/carrier32/config/connector-contract.csv hardware/carrier32/config/net-contract.csv`
可检查针位分配。完整工程检查在原理图、PCB和制造包补齐后启用。

## 当前发布状态

工程处于设计阶段。`config/design-inputs.csv` 中有 39 项制造关键实测输入尚未验证，
其中包括控制板排针、各类传感器模块引脚顺序、输出电压和机箱尺寸。
这些信息无法由软件或通用器件资料安全推断。机械尺寸、模块引脚、电气额定值及样板负载测试未完成前，
不得把本目录的任何输出作为可投产制造包。
