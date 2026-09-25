# Carrier32 KiCad 工程文件说明

将压缩包完整解压到同一个文件夹后，用 KiCad 打开 `carrier32.kicad_pro`。请保留各文件原名和目录结构，否则项目库及 3D 模型的相对路径可能失效。

| 用途 | 文件 |
| --- | --- |
| KiCad 工程入口 | `carrier32.kicad_pro` |
| 可编辑原理图 | `carrier32.kicad_sch` |
| 可编辑 PCB | `carrier32.kicad_pcb` |
| 项目符号库 | `lib/carrier32.kicad_sym`、`sym-lib-table` |
| 项目封装库 | `Carrier32.pretty/`、`fp-lib-table` |
| STM32 与屏幕 3D 外观模型 | `3dmodels/` |
| 整板 3D 预览 | `build/demo/carrier32-preview.glb` |
| STM32 与屏幕放大接线图 | `build/demo/module-overview.png`、`module-overview.svg` |
| PCB 3D 展示图 | `build/demo/modules-3d-top.png`、`modules-3d-iso.png` |
| 原理图及 PCB 原始预览 | `build/demo/schematic-preview.png`、`pcb-preview.png` |
| 立创EDA导入包（原理图+PCB+库） | `立创EDA导入_原理图_PCB_含库.zip` |
| 立创EDA仅导入PCB备用包 | `立创EDA导入_仅PCB.zip` |

原理图与 PCB 文件必须保持共同的 `carrier32` 基名，方便 KiCad 按同一工程关联；因此没有给这三个原生文件单独添加中文前缀。放大接线图是展示视图，不替代可编辑原理图。此工程为视觉展示版，PCB 尚未布线完成，不可作为制板文件。

## 导入立创EDA

先解压桌面上的完整工程压缩包，再在立创EDA的 KiCad 导入入口选择内部的 `立创EDA导入_原理图_PCB_含库.zip`，不要把完整交付包直接当作导入文件。此专用 ZIP 的根目录含 `carrier32.kicad_pro`、`carrier32.kicad_sch`、`carrier32.kicad_pcb`、项目符号库、封装库和 3D 模型目录。如只需 PCB，可改用 `立创EDA导入_仅PCB.zip`。

立创EDA标准版与专业版的 KiCad 导入器不是 KiCad 原生编辑器；专业版官方导入说明明确列举 KiCad 5.1/5.9 文件格式。本工程由较新版 KiCad 保存，因此压缩包和文件后缀符合官方导入入口要求，但不能保证其解析器完整接受或还原所有内容。若直接导入失败，可使用专业版官方“格式转换助手”处理同一工程 ZIP。导入后须核对原理图、封装、PCB 铺铜与 3D 模型；3D 模型可能需要在立创EDA内重新绑定。此包未伪装成原生 `.epro` 工程。

官方说明：
- 专业版 KiCad 导入：https://prodocs.lceda.cn/cn/import-export/import-kicad/index.html
- 专业版格式转换助手：https://prodocs.lceda.cn/cn/import-export/easyeda-pro-format-converter/
- 标准版 KiCad 导入：https://docs.lceda.cn/cn/Import/Import-KiCAD/
