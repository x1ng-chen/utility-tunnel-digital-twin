# IoTDA 安全转发网关

该服务订阅本地 `ut/v1/CTRL-01/telemetry`，校验 `ut.telemetry.v1` 报文后，通过 `mqtts://<IoTDA接入域名>:8883` 上报到华为云设备消息 Topic。IoTDA 下行消息和命令会转发到本地 `ut/v1/CTRL-01/cmd/iotda`。

## 使用

1. 在华为云 IoTDA 创建产品和密钥鉴权设备，记录设备 ID、设备密钥和实例“接入信息”中的设备接入域名。
2. 将 `.env.example` 复制为 `.env` 并填写；`.env` 已被仓库忽略。
3. 执行 `npm ci`，再执行 `npm start`。

当前开发机将 Mosquitto 的容器端口 `1883` 映射到宿主机端口 `1884`，因此
`LOCAL_MQTT_URL` 使用 `mqtt://127.0.0.1:1884`。

网关使用华为云规定的 `deviceId_0_0_YYYYMMDDHH` ClientId 和 HMAC-SHA256 密码，并强制校验 TLS 服务端证书。首期使用 `$oc/devices/{device_id}/sys/messages/up` 上报原始遥测，无需先冻结产品属性模型；产品模型确认后可再映射为 properties/report。
