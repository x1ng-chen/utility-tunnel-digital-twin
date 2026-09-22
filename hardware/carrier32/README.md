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

完整工程检查在后续任务补齐原理图、PCB和验证器后启用。

## 当前发布状态

工程处于设计阶段。机械尺寸、模块引脚、电气额定值及样板负载测试未完成前，
不得把本目录的任何输出作为可投产制造包。
