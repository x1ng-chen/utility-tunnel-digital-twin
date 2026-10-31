# V24：两侧嵌入式 120 mm RGB 风机

2026-10-29。用户确认两只风机均为 120 × 120 mm，TACH 已接，RGB 灯随供电自动点亮且与转速无关；本轮设备未开机，完成模型与软件联动，不进行硬件启停、烧录或现场验收。

## 安装模型

FAN-01 嵌入 +Y 侧板（管口朝下俯视图的左侧），FAN-02 嵌入 −Y 侧板（右侧）。二者沿板面的中心均为 X=350 mm、Z=220 mm，风机正面与盒体外表面齐平，主体向内嵌入。亚克力板已实际切除开口，原来小圆风机及旧圆孔已替换；并非将风机贴在完整板面上。

两处安装口相同，120.4 × 120.4 mm，给 120 × 120 mm 外框每侧预留 0.2 mm 的概念装配间隙，补有压边、角垫和固定件。25 mm 风机厚度、105 mm 螺丝孔距、圆角与间隙均为未测量的展示假设；不是可直接送加工的尺寸冻结。实际开孔前需量实物厚度、外框、圆角、孔距并确认加工公差及压边方式。

每台为黑色方框、圆形风道、七片带弯曲和桨距的扇叶、独立转子及 24 段固定彩虹发光网格。发光网格包含外圈正反面与中心光环，固定在外壳上，转动不会带着外框或灯环一起旋转。外壳/叶轮/发光段分别保留可编程节点。

31 个传感器、69 个语义资产、五个站点及其他 67 个资产根的身份和位置全部保留，包括 P1/P2/P5 中央氧传感器的 01/02/05 编号。本版实际 GLB 为 755 个唯一节点。

## 软件联动规则

| 输入 | 影响 | 不影响 |
| --- | --- | --- |
| 各自 `rotational.speed` / rpm | 对应 `FAN-0n_ROTOR` 叶轮转动；0 rpm 保持角度 | RGB 灯是否亮 |
| 各自 `supply.voltage` / V | 对应 RGB 灯亮灭 | 叶轮是否转动 |

两个输入都要求 API 数据来源、同一台风机的在线绑定、有效且新鲜的心跳/采样时间及 good 质量；演示数据、离线、过期、未来时间、错误单位和冲突样本不能冒充实物反馈。断线时叶轮冻结，灯光供电显示未知。没有电压数据时，即使有正 RPM，也不据此推断灯已亮。

电压显示策略为有效实测 V>0 显示有供电灯效、V=0 显示灭灯；这是与用户说明一致的供电显示近似，未声称测到了灯光、LED 实际点亮阈值或 RGB 颜色。颜色按照片固定彩虹近似，无 ARGB 控制协议、颜色回读或变色控制命令。

重点覆盖：有供电但零 RPM 时灯仍亮；无供电但 RPM>0 的惯性滑行时叶轮仍转、灯已灭；两台风机独立，不能互相借用反馈。叶轮展示速度上限 90 rpm，实际反馈数值不截断，避免高转速画面混叠；不承诺实际转子相位同步。

前端沿用原来的单一动画循环，按 V24 导出的 glTF 本地轴 `[0,1,0]` 驱动，兼容 V17–V23 的旧轴。RGB 使用各风机独立克隆材质，排除告警颜色/发光脉冲的改写，模型卸载时恢复和释放材质。

轮询增加两台风机各自的遥测窗口及最新硬件绑定，避免全局遥测页被其他传感器挤满后丢失风机信号，也避免只读取一次旧心跳后永久判为过期。未修改固件、接线、数据库或实际平台资产编号。

## 文件与查看

- `square-five-station-v24-inset-rgb-fans.blend`：最新原生模型，默认反馈未知、静止且不发光。
- 同名 `.glb`：包含完整模型、实际开孔和独立叶轮/灯环的导出。
- `previews/overall-powered-example.png`：整体亮灯效果示例。
- `previews/fan-inset-powered-example.png`：嵌入安装及 RGB 细节。
- `previews/power-and-motion-example.gif`：四阶段演示，明确标注合成输入，依次为供电转动、供电停转、断电滑行、断电停转。不是实物联调录像。
- `asset-map.json`、`sensor-bindings.json`、`station-focus.json`：继承 V23 并同步风机位置。
- `fan-animation-contract.json`：尺寸证据、节点/轴、测速与独立供电灯效契约。
- `fan-mount-review.json`、`export-verification.json`、`software-validation.json`：原生/实际导出/软件检查结果。
- `build_inset_fans.py`、`export_and_render.py`、`render_motion_example.py`：Blender MCP 执行脚本。
- `verify_export.mjs`：实际 Three.js GLTFLoader 复核。

## 下载与复现

GitHub 本次发布完整 V24 模型包及风机联动参考实现；服务器正式模型发布和运行资产台账不在本次模型归档范围内。

1. 在仓库根目录执行 `git lfs pull --include="model/square-five-station-v24-inset-rgb-fans/**" --exclude=""` 获取真实二进制文件，或下载本目录的 `v24-inset-rgb-fans-delivery.zip`。
2. 直接用 Blender 5.2 打开本目录 `.blend` 即可编辑最新版；运行 `python model/square-five-station-v24-inset-rgb-fans/verify_package.py` 核对包内哈希。
3. 从仓库的 `frontend` 目录执行 `npm ci` 安装已有 Three.js 依赖，再在仓库根目录运行 `node model/square-five-station-v24-inset-rgb-fans/verify_export.mjs` 与 `node model/square-five-station-v24-inset-rgb-fans/integration/verify-fan-motion.mjs`，验证实际 GLB、开孔、转子轴及供电独立灯效。
4. 如需重新生成 V24：先打开 `sources/square-five-station-v23-refined-acrylic/` 中冻结的 V23 `.blend`，通过 Blender MCP 运行 `build_inset_fans.py`，再运行 `export_and_render.py`。执行脚本时将 `__file__` 设为该脚本绝对路径，例如 `exec(compile(script.read_text(encoding='utf-8'),str(script),'exec'),{'__file__':str(script),'__name__':'__main__'})`。原生 V24 及冻结输入的 SHA256 已记录。

`sources/` 只保存本次重建所需的冻结输入，不宣称包含 V19–V23 的全部中间工程。`history/` 保存传感器编号和氧模块的身份迁移表，接入平台前应核对实际台账。

`integration/fan-motion.mjs` 是本次已测试 TypeScript 风机联动器的可执行 JavaScript 参考实现；`integration/README.md` 给出接入位置。彩光由供电反馈控制，绝不从 RPM 推断供电。生产前端或其他未提交的业务改动没有被打包为本次上传内容。

本次发布的模型不是服务器活动模型自动切换，也不是硬件验收。用户明确设备目前未开机，真实启停联动验收为 NOT_RUN；原本地实现的 111 项测试和构建结果保留在 `software-validation.json`，发布包另有针对实际 GLB/参考实现的独立复核。

![嵌入式风机与 RGB 示意](previews/fan-inset-powered-example.png)

![供电与转速独立的合成状态演示](previews/power-and-motion-example.gif)
