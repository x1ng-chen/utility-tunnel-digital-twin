# V24 替换运行模型（2026-10-29）

按用户授权，读取模型专用对话“综合管廊四主控长方体模型搭建”的最新交付，将 [PR45 的 V24](https://github.com/x1ng-chen/utility-tunnel-digital-twin/pull/45) 接入前端及现有实物联调库。原模型交付文件保留，运行活动版本从 `hardware-live-v20` 切换为 `hardware-live-v24`。

新模型包含更通透的外壳、细化装配、P1／P2／P5中央氧模块、两侧嵌入式120mm风机和独立RGB灯效。开孔、厚度与螺丝孔距仍是模型展示假设；本次替换不表示加工尺寸或实物启停已验收。

## 模型编号与采集编号

V22／V23曾改模型显示编号，但固件、MQTT和业务历史仍用原采集编号。只换GLB会使部分告警命中错误探头。本次用精确模型SHA256启用独立适配表，保持所有业务 `Asset.code`、资产主键、硬件绑定与控制器归属不变：

| 原采集组 | V24模型标签／工位 |
| --- | --- |
| 气体／火焰01组 | 04组／P4 |
| 02组 | 01组／P1 |
| 03组 | 03组／P3 |
| 04组 | 02组／P2 |
| 05组 | 05组／P5 |
| 温湿度、液位01／02／03／04 | P4／P1／P3／P2，原网格保持 |
| GAS-O2-01 | GAS-O2-01／P1 |
| GAS-O2-02 | GAS-O2-05／P5 |
| GAS-O2-03 | GAS-O2-02／P2 |

不同编号时设备名称同时显示模型标签和“采集xx”，例如 `FLAME-01（采集 FLAME-02） · P1`。P5火焰仍为FLAME-05，P5没有温湿度模块。实际主控归属仍为11／7／6／7；V24交付附表里的旧主控所属不作为接线依据。四个主控对象坐标与V20一致，保持canonical身份，不因模型附表推测更换主控。

[完整版本化适配表](../../backend/operations/agent_catalog/model-v24-presentation.json)从V22编号迁移和V23氧模块迁移组合生成，31个目标唯一，位置核对实际GLB。历史任务冻结的旧站点证据保留，不倒改历史；跨呈现版本的接续按已有版本保护处理。

## 风机与灯效

- 独立转子按各自新鲜有效的 `rotational.speed/rpm` 驱动；V24 glTF本地轴为 `[0,1,0]`。
- RGB独立依据各自新鲜有效的 `supply.voltage/V`。有供电零RPM仍亮，断电惯性滑行可转而灯灭；缺测／离线显示未知，不借用其他风机反馈。
- RGB材质不被告警染色或脉冲覆盖，传感器告警强调效果保留。固定彩虹是显示近似，不声称RGB颜色回读。
- 继续使用一个动画循环。风机专用遥测窗口和心跳会持续刷新，避免31路传感器挤占全局最近数据页后丢失风机证据。

## 当前本机结果

现有实物联调运行目录为 `D:\shixi\utility-tunnel-worktrees\publish-software-agent-20261025`。只同步本次模型适配及前端联动文件，未覆盖其余未提交内容。相关旧源文件保存在该目录 `.hardware-live/v24-source-backup-*`，安装前SQLite完整备份为 `.hardware-live/before-v24-*.sqlite3`。

- 活动模型：`hardware-live-v24`，10,159,544字节。
- SHA256：`b974e683be2aff9b79e6c04dcd0e753849ec4619c961d48004eb5abf84711a9c`。
- 实际网络登录、模型就绪接口及活动GLB下载哈希核对通过；37个活动业务资产全部映射，31个物理传感器目标唯一。
- 前端静态GLB的实际HTTP下载哈希一致，Vite服务已启动。
- 资产主键／采集编码和MQTT绑定与安装前备份核对一致；没有发送硬件控制命令或模型请求。
- 完整后端372项通过；前端177项通过，含实际V24GLB转子／灯效测试；TypeScript和构建通过。当前运行目录的前端也单独构建通过。
- Work设置禁用浏览器操作，未进行实际画面走查；服务和静态/接口文件已验证，不声称浏览器视觉及真机告警重新验收。

本机页面：<http://127.0.0.1:5173/twin-3d>。旧标签页可按 `Ctrl+F5` 重新获取前端和活动模型；账号未在本次更改。

## 复现与检查

```powershell
node tools/check-v24-runtime.mjs
cd frontend
$env:FAN_MODEL_GLB = (Resolve-Path public/models/utility-tunnel-v24.glb).Path
npm test -- --reporter=dot
npm run build
cd ..
python backend/manage.py test operations.test_twin_v20_presentation operations.test_twin_v24_presentation --noinput
```

独立检查输出见 [实际GLB校验](glb-verification.json)、[本机接口验证](runtime-verification.json)。这些记录没有凭据、私有任务或原始遥测。

在另一个已经准备好的实物联调库安装时，先获取LFS二进制，再使用：

```powershell
python backend/manage.py install_twin_v24 --settings=config.hardware_live_settings
# 或指定已校验的完整文件；散列不一致会拒绝
python backend/manage.py install_twin_v24 --settings=config.hardware_live_settings --file 'D:\模型目录\square-five-station-v24-inset-rgb-fans.glb'
```

安装器只接受专用SQLite联调配置、完整身份清单及已知原映射。先备份，再原子切换映射和模型；循环编号先统一释放旧别名，避免顺序重命名串号。保持V20适配器，原GLB不删除。若需回退，先停止联调进程并审阅备份与此后的新增数据，不能直接覆盖数据库丢失新观测。
