# V24同编号传感器映射修订

依据2026-10-29用户要求，将31路采集物理编号绑定到同编号模型模块。
原V24、已通过的火焰位置及全部设备几何位置保留；修订只更新映射、对应元数据和中央氧气文字。

- MQ-2、MQ-4、CO、火焰01～05分别位于P1～P5。
- 温湿度SHT-01～04与液位LEVEL-01～04保留现有同编号模块位置：P4、P1、P3、P2。
- 氧气O2-01、02、03分别位于P1、P2、P5；中央旧O2-05更名O2-03，不增加氧气探头。
- 固件主控归属11/7/6/7不变；模型位置不能用于推断接线主控。
- 首路旧业务别名SMOKE-01、GAS-CH4-01、GAS-CO-01分别代表MQ2-01、MQ4-01、CO-01。

`sensor-bindings.json`是31路具体映射；`verification.json`记录原件保护和变换不变检查；
`three-validation.json`记录实际Three.js加载、对象坐标及双风机结构检查。
这些是软件/模型验证，不能代替实物触发、高亮与恢复验收。

从原V24 Blender文件重建：

```powershell
blender --background --disable-autoexec model/square-five-station-v24-inset-rgb-fans/square-five-station-v24-inset-rgb-fans.blend --python model/square-five-station-v24-unified-numbering/build_unified.py
node tools/verify-unified-sensors.mjs
```

仅在独立实物联调库安装（先验证文件散列，再备份并事务更新）：

```powershell
$env:DJANGO_SETTINGS_MODULE='config.hardware_live_settings'
python backend/manage.py install_twin_v24 --unified-numbering
```

安装保留资产ID、遥测、硬件通信绑定及历史告警。旧告警按其资产ID查阅时会使用当前定位，不能将其解释为历史触发位置也已复核。
