# IoTDA 安全转发网关

该服务订阅本地 `ut/v1/CTRL-01/telemetry`，校验 `ut.telemetry.v1` 报文后**双路输出**：

1. **云端路**：通过 `mqtts://<IoTDA接入域名>:8883` 上报到华为云设备消息 Topic。IoTDA 下行消息和命令会转发到本地 `ut/v1/CTRL-01/cmd/iotda`。
2. **平台路**：将同一条遥测映射为 Django 批量契约报文，使用仅限遥测写入的机器 API Key `POST /api/telemetry/` 幂等入库，由后端触发阈值告警、审计与工单闭环。适配器不绕过 API、不直接访问数据库。

两路相互独立、可单独关闭（`IOTDA_ENABLED=false` 或不配置 `DJANGO_API_URL`），但至少要保留一路，否则启动即报错。

## 使用

1. 在华为云 IoTDA 创建产品和密钥鉴权设备，记录设备 ID、设备密钥和实例“接入信息”中的设备接入域名。
2. 在 Django 端运行 `python manage.py configure_ingest_principal`，并从密钥管理系统向后端和网关注入同一个至少 32 字符的 `DJANGO_INGEST_API_KEY`。该机器身份不能读取平台数据或操作告警/工单。
3. 将 `.env.example` 复制为 `.env` 并填写；`.env` 已被仓库忽略。
4. 执行 `npm ci`，再执行 `npm start`。

当前开发机将 Mosquitto 的容器端口 `1883` 映射到宿主机端口 `1884`，因此
`LOCAL_MQTT_URL` 使用 `mqtt://127.0.0.1:1884`。

网关默认还会每 3 秒向每个可用 IPv4 网卡的定向广播地址发送 UDP `4210` 报文，向 ESP8266 公告宿主机可访问的 MQTT 端口 `1884`。ESP 从 UDP 来源地址得到电脑当前 IP，因此手机热点 DHCP 地址变化后无需重新烧录。相关配置为：

```ini
MQTT_DISCOVERY_ENABLED=true
MQTT_DISCOVERY_PORT=4210
MQTT_DISCOVERY_INTERVAL_MS=3000
MQTT_DISCOVERY_HMAC_KEY=replace-with-the-same-random-key-as-the-esp
MQTT_PUBLIC_PORT=1884
```

`MQTT_PUBLIC_PORT` 是 ESP 从局域网访问 Windows 宿主机时使用的端口，不是容器内部端口。成功启动日志包含 `MQTT discovery broadcasting UDP/4210 for local MQTT/1884.`。该发现协议只适用于隔离台架局域网，不应跨公网使用。

网关使用华为云规定的 `deviceId_0_0_YYYYMMDDHH` ClientId 和 HMAC-SHA256 密码，并强制校验 TLS 服务端证书。首期使用 `$oc/devices/{device_id}/sys/messages/up` 上报原始遥测，无需先冻结产品属性模型；产品模型确认后可再映射为 properties/report。

## 平台路（Django 转发）细节

- **认证**：使用 `X-Ingest-Key` 机器凭据，权限仅覆盖 `POST /api/telemetry/`。邮箱/密码方式只作为迁移兼容，不应继续用于新部署。
- **字段映射**：`assetCode` 大写归一化；`metric`（设备侧指标键）作为 `metricKey`；显示名与单位按固定映射表转换（如 `degC` → `°C`，`temperature` → `环境温度`），与 `seed_demo` 的阈值单位保持一致；设备未提供 `ts` 时使用网关接收时间作为 `recordedAt`。
- **幂等**：每帧以设备 ID、业务时间和完整 readings 计算 SHA-256 摘要，再为各读数附加序号；同毫秒不同载荷不会碰撞，MQTT 重投同一载荷仍复用编号。
- **失败处理**：批次先写入 `DJANGO_QUEUE_DB` 指定的 SQLite/WAL outbox；进程重启后会自动续传。默认 `DJANGO_QUEUE_MAX=43200`，按 2 秒一帧约覆盖 24 小时，可按磁盘容量调整。网络错误、5xx、429 和普通并发 409 进入指数退避重试；`idempotency_conflict`、不可恢复 4xx 和队列溢出批次会原样转存同一 SQLite 文件的 `django_dead_letter` 表并记录原因，不再静默丢失。死信需经人工核验、修正后再重放或归档。
- **观察性**：每批成功/重试/丢弃都会输出日志；`Django stored N reading(s) (duplicates X, queued Y)` 即为平台路心跳。

ESP8266 会在保留状态主题 `ut/v1/<DEVICE_ID>/status` 发布 `online`，并以 LWT 发布 `offline`；STM32 帧含单调 `seq` 便于识别缺帧。ESP 侧使用固定内存的 8 帧短时缓冲，在 Wi-Fi/MQTT 恢复后顺序补发；网关收到帧后再由 SQLite outbox 提供重启续传。受 PubSubClient 发布能力限制，ESP→本地 Broker 当前仍是 QoS 0，因此这是“短时断线缓冲 + 可观测缺帧”，不是端到端 exactly-once；重要验收仍需执行断网和掉电测试。

## 联调冒烟

无需硬件与 MQTT broker，可对已 `seed_demo` 的 Django 后端验证平台路全闭环（入库 → 单位映射 → 幂等重放 → 阈值自动告警）：

```powershell
python manage.py runserver 127.0.0.1:8000   # backend/，另开终端
cd services/iotda-gateway
$env:SMOKE_BASE_URL = "http://127.0.0.1:8000"
node smoke-django.mjs
```

输出 `SMOKE OK` 即表示网关→Django 遥测入库与告警闭环可用。
