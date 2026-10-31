# 2026-10-31 完整业务镜像

四块STM32和一个ESP32-S3网关的业务镜像；**CTRL-02保留全部业务功能，不是SHT最小诊断版**。每个目标的地址、大小和SHA256见[manifest.json](manifest.json)。构建ID：`fa7f40f31621109d`。

- STM32各自`0x08000000`，必须核对板号/UID；不能把4号镜像刷到2号。
- GW-01使用manifest中的四段地址，保留NVS；不整片擦除，不将填充合并镜像覆盖NVS。
- 网关凭据不编入镜像，按[运行时配置说明](../../../firmware/four-controller/RELEASE.md)设置。
- 镜像构建/软件检查通过，不代表当前设备已刷入、引脚电压合格或现场功能验收通过。
- 板2最后确认仍运行临时诊断版；温湿度未恢复，详见[当前状态](../../../docs/PROJECT_STATUS.md)。

[完整下载包](https://github.com/x1ng-chen/utility-tunnel-digital-twin/releases/tag/v2026.10.31-integration)另含ELF、MAP、构建日志、冻结源码和校验脚本。以上仓库镜像可直接下载；请先核对散列再制定实际刷写方案。
