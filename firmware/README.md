# 固件导航

当前方案：四块STM32F103RCT6、一个ESP32-S3网关，另有独立小管语音终端。

- [四主控与网关完整业务源码](four-controller/README.md)
- [业务镜像构建、发布与烧录](four-controller/RELEASE.md)
- [本次发布与下载](../docs/releases/2026-10-31/README.md)
- [当前接线与引脚](../docs/hardware/four-controller-wiring-20261026/README.md)
- [语音终端与服务](../services/voice-assistant/README.md)
- [独立SHT诊断源码](four-controller/diagnostics/sht-isolation/README.md)：临时测试，非CTRL-02业务交付镜像。

`stm32f103rct6/`保留HAL/CMSIS、链接脚本及旧固件依赖；`rs485-bench/`保留总线诊断；`esp8266-01s/`为旧双节点方案。历史源码不代表当前要刷入ESP8266。

仓库发布的CTRL-02包含全部业务功能。实物最后确认运行临时诊断版，回装和启动验证仍待进行；详情见[当前进度](../docs/PROJECT_STATUS.md)。
