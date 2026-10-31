> **2026-10-31完整业务发布**：[下载、指纹与验证](../../docs/releases/2026-10-31/README.md)。四板与网关均从本次集成源码构建；CTRL-02为完整业务镜像，不是SHT最小诊断版。上传不等于已刷入实物，板2温湿度仍待定位。发布包不含网络凭据，网关使用运行时配置。

# 四STM32＋S3网关完整业务固件交付版

版本`2026.10.27.2`，适用于STM32F103RCT6×4、ESP32-S3 N16R8网关×1。另一块小智S3不在本包内。软件镜像已生成并验证身份/散列；`hardwareVerified=false`表示还需在实物上验收，不代表本包已烧录。

网关修订：`.1`版本在真实S3上处理UART配置请求时复现了`loopTask`栈溢出；`.2`将该任务栈从Arduino默认8 KiB显式调整为24 KiB。配置回执新增`loopStackMinFreeBytes`，表示ESP-IDF报告的实际任务栈最小剩余字节数；主机桩返回0，不是实物测量。烧录、UART配置、Wi-Fi连接、MQTT连接和四节点通信仍需分别验收；旧启动成功记录不证明配网接口已通过。

## 五个目标

| 目标 | 位置与职责 | 外部传感器 |
|---|---|---:|
| CTRL-01 | 左下，P3/P5，中文状态屏 | 11 |
| CTRL-02 | 右下，P4，中文主屏/摇杆、FAN-02/继电器/INA | 7 |
| CTRL-03 | 右上，P2，蜂鸣器/18灯灯带 | 6 |
| CTRL-04 | 左上，P1，FAN-01/继电器/INA | 7 |
| GW-01 | S3汇总、四节点轮询、Wi-Fi/MQTT、菜单转发、命令与回执关联 | 汇总31路 |

业务协议仍为RTU v2：地址1～4，19200/8E1，签名0x5554、版本0x0200；不与8寄存器诊断固件混用。传感器、保护、手动租期、独立RPM/INA反馈、回执去重和过期判断沿用业务协议。中文双屏逐行重绘；STM32主循环看门狗在卡死后复位，启动日志包含复位原因、板号、软件版本和buildId。看门狗名义约4秒，实际由LSI决定；波形/故障恢复须在实物上测量。

## 包内文件

- `CTRL-01`～`CTRL-04`：各自`.bin`、`.elf`、`.map`。**板号必须对应，不能把一份镜像给四块板通刷。**
- `GW-01`：S3应用、bootloader、partition table及boot_app0。网关为完整联网能力镜像，未配置时继续串口诊断/485轮询，不假装已上云。
- `manifest.json`：全部文件SHA256、来源指纹、五目标、构建参数、测试结果和待实测状态。
- `release-profile.json`：明确的PWM/继电器极性、PPR、INA配置及其验证标记。
- `logic-tests.json`和`logs/`：实际软件测试与编译日志。
- `source.zip`：可复查的公开源码快照，排除`.pio`、构建产物和`secrets.h`；无实际网络凭据。
- `flash_plan.py`只校验并打印命令，**不调用烧录器、不连接端口**。
- `provision_gateway.py`在指定本次端口后才打开串口配置网关。

## 构建与核验

在完整工程根目录执行，需已有Arm GCC、CMake、Ninja、Python/PlatformIO。Windows的可移植测试使用pyelftools/Unicorn；Linux可用本机GCC。生成的字形头文件已入源码，普通构建无需安装字体/Pillow或重新生成字库。

```powershell
python firmware/four-controller/tools/build_release.py --output D:/shixi/deliverables/<新的目录名> --test-mode arm-emulated
python firmware/four-controller/tools/build_release.py --verify D:/shixi/deliverables/<目录名>
```

构建器校验四块板的向量表、Flash/RAM范围和内嵌板号；网关校验内嵌版本。全部通过才移除`INCOMPLETE`。不覆盖旧发布目录；未完成的目录不得烧录。

```powershell
python <交付包>/flash_plan.py --target CTRL-04
python <交付包>/flash_plan.py --target GW-01 --port COMx
```

命令是分段写入：S3 bootloader在0x0、partitions在0x8000、boot_app0在0xe000、应用在0x10000。**不要自行把0～应用区的空隙填满合并再写入，那会覆盖NVS。** 已确认启动器/分区相同的后续升级可以只更新应用。原Flash备份包含设备私有数据，保存在本地，不提交GitHub。

STM32备份使用`--upload <地址> <长度> <文件>`，参数依据[ST UM2237](https://www.st.com/resource/en/user_manual/dm00403500-stm32cubeprogrammer-stmicroelectronics.pdf)；实际执行时使用本机已安装的CubeProgrammer CLI路径。S3烧录需esptool，配网需pyserial；本机已安装相应工具。

## S3本地配置，无需重新编译

网关发布镜像强制`UT_RUNTIME_CONFIG_ONLY`，不读取编译期`secrets.h`。先烧录，退出其他串口监视器，再执行：

```powershell
python <交付包>/provision_gateway.py --port COMx --action set
python <交付包>/provision_gateway.py --port COMx --action status
```

交互输入Wi-Fi、MQTT主机/端口、账户和NTP；密码使用隐藏输入，不通过命令行参数传递、不在回执中返回。也可使用**本地私有**JSON文件传入`--config-file`，字段为`ssid`、`wifiPassword`、`mqttHost`、`mqttPort`、`mqttUser`、`mqttPassword`、`ntpServer`，不得提交该文件。

当前台架broker位于运行网关服务的电脑局域网地址；若使用现有compose端口映射，S3端口为1884。S3中不能填127.0.0.1。NTP可以填可达的本地时间服务器；没有有效UTC时仍上报存疑数据，并拒绝MQTT硬件命令。

配置在独立NVS命名空间`ut-net-v1`内保存，校验格式、长度和存储读回；成功保存后重启应用。存储损坏时保持未配置，不能静默读取错误数据。配置只经本地UART接收，MQTT不能改配置；没有开放配置热点。NVS校验用于发现损坏，不是加密存储。保存成功不等于已连接Wi-Fi/MQTT，需看实际递增遥测与broker日志。

显式清除网络配置：

```powershell
python <交付包>/provision_gateway.py --port COMx --action clear --confirm-clear
```

清除配置不清理`ut-cmd-v2`命令记录，重启/重连不把旧cmdId重新执行。未经确认的命令不能由配置工具下发。

## 当前硬件参数与平台对接

2026-10-29按用户及旧接线记录确认的R010修订为INA分流10000µΩ（0.01Ω）、100µA/LSB，电流寄存器有符号满量程约±3.2767A；这不是模块允许电流或供电容量的认证。沿用NPN反相PWM、继电器高有效、PPR=2。PPR/INA独立测量的默认验证标记仍为0，换算反馈按存疑处理。10月27日r2已烧录镜像仍为100000µΩ/10µA，需更新2/4号板后新参数才在实物生效。修改参数需重建，已验证标记需填写该板的实测引用，不能只改标记让数据显示正常。

保留CTRL-01 O2-02/PA0与WKUP按键负载的已声明核查项；AO-02和MQ仍为原始量，不能显示成可信氧气浓度/ppm。GPIO连接、模拟电压、风机极性/PPR、分流、电流方向及中文屏效果仍需实体测量。编译/纯逻辑测试不证明GPIO、电平、时序和负载已通过。

平台在完成对应硬件验收后再显式切换`CONTROLLER_COMMAND_PROTOCOL=four-controller-v2`，网关服务订阅CTRL-01～04四主题；现有Agent模拟环境继续禁用真实硬件控制。

建议实体顺序：备份原Flash→S3＋4号业务v2→四节点主干→31路逐项正常/触发/恢复→双风机独立反馈→菜单确认/取消→断线/重启/NVS掉电。每块板启动日志中的`UT-IMAGE`应与manifest一致。
