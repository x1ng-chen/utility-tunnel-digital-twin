# IoTDA 安全转发网关

该服务订阅本地 `ut/v1/CTRL-01/telemetry`，校验 `ut.telemetry.v1` 报文后**双路输出**：

1. **云端路**：通过 `mqtts://<IoTDA接入域名>:8883` 上报到华为云设备消息 Topic。IoTDA 下行消息和命令会转发到本地 `ut/v1/CTRL-01/cmd/iotda`。
2. **平台路**：将同一条遥测映射为 Django 批量契约报文，用专用服务账号登录后 `POST /api/telemetry/` 幂等入库，由后端触发阈值告警、审计与工单闭环。适配器不绕过 API、不直接访问数据库。

两路相互独立、可单独关闭（`IOTDA_ENABLED=false` 或不配置 `DJANGO_API_URL`），但至少要保留一路，否则启动即报错。

## 使用

1. 在华为云 IoTDA 创建产品和密钥鉴权设备，记录设备 ID、设备密钥和实例“接入信息”中的设备接入域名。
2. 为平台路创建一个**专用运维员服务账号**（如 `gateway@example.com`，通过管理员在「用户管理」中创建；不要复用个人账号）。运维员及以上角色才有遥测写入权限。
3. 将 `.env.example` 复制为 `.env` 并填写；`.env` 已被仓库忽略。
4. 执行 `npm ci`，再执行 `npm start`。

当前开发机将 Mosquitto 的容器端口 `1883` 映射到宿主机端口 `1884`，因此
`LOCAL_MQTT_URL` 使用 `mqtt://127.0.0.1:1884`。

网关使用华为云规定的 `deviceId_0_0_YYYYMMDDHH` ClientId 和 HMAC-SHA256 密码，并强制校验 TLS 服务端证书。首期使用 `$oc/devices/{device_id}/sys/messages/up` 上报原始遥测，无需先冻结产品属性模型；产品模型确认后可再映射为 properties/report。

## 平台路（Django 转发）细节

- **认证**：服务账号调用 `/api/auth/login/` 获取 Bearer Token；平台令牌默认 15 分钟过期，网关遇到 401 会自动重新登录并重放当前批次。
- **字段映射**：`assetCode` 大写归一化；`metric`（设备侧指标键）作为 `metricKey`；显示名与单位按固定映射表转换（如 `degC` → `°C`，`temperature` → `环境温度`），与 `seed_demo` 的阈值单位保持一致；设备未提供 `ts` 时使用网关接收时间作为 `recordedAt`。
- **幂等**：每条读数的 `eventId` 形如 `gw:CTRL-01:<接收毫秒时间戳>:<序号>`，同一条 MQTT 消息重试复用同一编号；重放已入库事件只会增加 `duplicates`，不会重复写库。
- **失败处理**：网络错误、5xx、429 和并发 409 进入有界重试队列（默认 150 批，指数退避，最多保留约 5 分钟的 2 秒周期数据，溢出丢弃最旧批次）；4xx 校验错误不会自愈，直接丢弃并记录错误，保证实时车道不被堵死。
- **观察性**：每批成功/重试/丢弃都会输出日志；`Django stored N reading(s) (duplicates X, queued Y)` 即为平台路心跳。

## 联调冒烟

无需硬件与 MQTT broker，可对已 `seed_demo` 的 Django 后端验证平台路全闭环（入库 → 单位映射 → 幂等重放 → 阈值自动告警）：

```powershell
python manage.py runserver 127.0.0.1:8000   # backend/，另开终端
cd services/iotda-gateway
$env:SMOKE_BASE_URL = "http://127.0.0.1:8000"
node smoke-django.mjs
```

输出 `SMOKE OK` 即表示网关→Django 遥测入库与告警闭环可用。
