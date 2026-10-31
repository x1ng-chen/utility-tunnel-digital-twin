# 四主控实物遥测联调

本配置只接收实物遥测，不运行模拟采样器、不发送硬件控制命令，也不调用付费模型。
原业务库、`.agent-demo` 和各评测库不作为启动目标。所有私有运行文件写入被 Git 忽略的 `.hardware-live/`。

## 首次启动

需要已安装 `backend/requirements.lock` 的 Python 环境，以及按锁文件安装好的 frontend、services/iotda-gateway Node 依赖。
启动现有 Mosquitto（本机端口1884），让电脑与ESP32网关连接同一热点。此脚本不会改写ESP32中的Wi-Fi/MQTT配置。

在项目根目录执行，解释器路径换成实际安装依赖的环境：

```powershell
.\deploy\hardware-live\start.ps1 -PythonPath "你的Python环境\Scripts\python.exe" -NodePath "你的Node路径\node.exe"
```

- 页面：`http://127.0.0.1:5173/telemetry`，后端：`http://127.0.0.1:8000/api`。
- 登录信息：`.hardware-live/access.json`，仅保存在本机，不提交GitHub。
- API健康信息必须返回 `profile=hardware-live`。端口被其他环境占用时脚本拒绝启动，不终止无关服务。
- 初始化只建立31传感器、四主控、双风机及其绑定，**不生成测量值、告警、工单或已审批经验**。
- 现有V17经过原有上传/校验/激活流程进入独立媒体目录；不重建模型。模型主控文字仍有旧编号，界面保留提示，身份以当前映射为准。
- 当前本机已另行启用V20，主控采用同名对象，站点为后左P1、后右P2、前左P3、前右P4、中央P5；正常启动保留已启用版本，不自动切回V17。V20与固件的版本化适配见`docs/model/v20-frontend-integration-20261028.md`。
- 运行账号为运维员；CLI模型导入服务禁止密码登录，CLI激活不记为人工验收。
- 硬件控制接口即使被管理员调用也拒绝；付费模型任务明确返回暂停提示，不进入无人处理的队列。五站直接巡检可用且不调用模型。

## 数据契约

订阅四个明确主题：`ut/v1/CTRL-01/telemetry` 至 `ut/v1/CTRL-04/telemetry`。
布局 `four-controller-20261026.1`，外部传感器归属 **11/7/6/7**；风机1归CTRL-04、风机2归CTRL-02。

新遥测保留 `provenance`：来源、主控、帧编号、布局、时钟来源、帧时间、采样年龄和序号。
只有专用接入身份可写入实物联调库，普通运维员不能通过网页/API伪造观测。
后端校验来源、归属、单位、量程及时序一致性；同一事件携带不同来源元数据时拒绝覆盖。

MQ/氧气原始值不会转换为可信ppm或氧气百分比。氧气保持可疑质量；MQ原始ADC4095降为可疑。
缺测占位零值显示“缺测”，不进入数值极值/均值计算。质量“良好”仍不证明接线、标定或实体触发验收通过。
历史数据不改时间；有效新观测才更新连接状态。默认2秒期望上报，15秒无有效新观测后进入过期/离线。
该来源标识是经过接入服务校验的链路来源，不是硬件签名或传感器真实性证明。

## 可复现验收

```powershell
python .\deploy\hardware-live\verify_ingestion.py --seconds 12
node .\deploy\hardware-live\verify_realtime.mjs
.\deploy\hardware-live\verify_transport_recovery.ps1 -PythonPath "你的Python环境\Scripts\python.exe" -NodePath "你的Node路径\node.exe"
```

前两个脚本只读取真实HTTP/WebSocket数据。第三个脚本临时停止CTRL-03的本机转发订阅，验证该板数据自然过期、其他板继续更新，并在finally中恢复四板订阅。
**转发中断测试不是实物RS-485拔线/掉电验收**。测试会真实产生并恢复本联调库中的通信告警，不生成模拟遥测。
原始结果、日志和进程记录保存在 `.hardware-live/`；公开报告仅整理不含密钥的摘要。

停止本配置记录的四个进程，不删除数据：

```powershell
.\deploy\hardware-live\stop.ps1
```

后续仍需逐路触发/恢复、双风机与INA226、实物拔线/掉电、长时间运行，以及页面人工验收。

## 火焰高亮验收

在已经运行的实物联调环境中，先使用同一Python环境执行：

```powershell
$env:DJANGO_SETTINGS_MODULE='config.hardware_live_settings'
python backend/manage.py prepare_flame_acceptance
node deploy/hardware-live/observe_flame.mjs
```

第一条命令只配置0/1火焰规则，不注入观测；第二条只读观察真实MQTT与平台提交后的实时事件，窗口180秒或完成一次触发恢复后结束。
网页是否高亮、位置是否正确及颜色是否恢复仍需实际观察。2026-10-28中央P5已经完成一次实物触发与用户画面确认，详见`docs/hardware/flame-highlight-acceptance-20261028.md`；其余四路待测。
