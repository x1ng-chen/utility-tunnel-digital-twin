# 服务导航

| 服务 | 用途 | 入口 |
| --- | --- | --- |
| MQTT接入 | 四主控遥测归一化、幂等与来源信息 | [iotda-gateway](iotda-gateway/README.md) |
| 本地决策 | AnyJev闭集只读路由；默认禁用 | [部署](../deploy/decision-router/README.md) |
| 小管语音 | S3语音终端的独立服务 | [voice-assistant](voice-assistant/README.md) |
| 本机MQTT | 开发联调Broker | [local-mqtt](local-mqtt/README.md) |

当前状态见[项目进度](../docs/PROJECT_STATUS.md)。本地决策与语音终端均不替代ESP32-S3汇总网关。
