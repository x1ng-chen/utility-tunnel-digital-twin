# CTRL-02 温湿度最小隔离诊断

这是独立、临时诊断目标，不是四主控业务固件，不由业务发布构建器生成。只用于已确认的 STM32F103RCT6 / CTRL-02；PB10=SCL、PB11=SDA、USART1 PA9/PA10 115200 8N1。

## 目的及边界

在不变更传感器接线、地址焊桥或供电的条件下，交替运行两种读取路径：

1. `SOFT`：编译当前 `Core/Src/board_io.c` 的原始软件 I²C 和 SHT 函数，保持原位时序，命令完成后等待50 ms。没有屏幕、摇杆、ADC、INA或Modbus任务。
2. `HARD`：同一对引脚改为I²C2，由ST HAL v1.1.10以100 kHz读取，命令后也等待50 ms。

每个阶段30轮、每轮至少2秒，循环进行；每阶段计数独立。初次依次试0x44、0x45，有效读取后固定本阶段地址。`fail`是没有获得有效测量的轮数；寻找另一个地址时的单次NACK不能当作传感器测量失败率。两个地址均失败时，`err0/err1`分别属于0x44/0x45；固定地址后仅使用`err0`。

只有完整读回6字节且温度、湿度两段CRC均通过，才输出`valid=1`和温湿度。失败行不输出测量值。没有通用复位、SHT软复位或INA访问。业务遥测暂时中断，平台可能显示CTRL-02离线；其他板不变。

PA1保持低电平，按当前高电平继电器约定为关闭。烧录和测试前关闭风机12V，INA信号线保持已确认的隔离状态。只运行这一诊断并不能证明引脚电压、传感器精度或整机联调通过。

## 结果解释

| 对照 | 可支持的方向 |
|---|---|
| SOFT和HARD均连续成功，业务固件失败 | 优先查业务任务交互；本诊断等待50 ms，也需独立比较转换时间，不能直接断言屏幕根因 |
| SOFT失败、HARD成功 | 优先查软件位时序/软件驱动与当前电气条件的组合；硬件I²C可作为候选修正路径 |
| SOFT成功、HARD失败 | 查硬件I²C初始化、HAL错误及芯片限制；不能认定板损坏 |
| 两者均失败 | 继续量测板2供电、PB10/PB11线路及模块电平/波形；不能仅凭结果宣告板坏或软件无误 |

SOFT错误使用原驱动stage（1写地址、2/3命令、4读地址、5/6 CRC、7 SCL超时）。HARD错误低16位为HAL错误；`0x10000`标记接收阶段、`0x20000`标记CRC失败。CRC通过的测量也不能反过来证明此前所有接线稳定。

## 构建与依赖

当前业务工程未带HAL I²C模块源码。此诊断仅补用ST官方同版本文件，隔离于业务HAL目录：

- 仓库：<https://github.com/STMicroelectronics/stm32f1xx-hal-driver/tree/77fbb30b7a1d02533980400083e48c559aae5a4f>
- 版本：v1.1.10，固定提交`77fbb30b7a1d02533980400083e48c559aae5a4f`。
- 文件：`Src/stm32f1xx_hal_i2c.c`、`Inc/stm32f1xx_hal_i2c.h`、`LICENSE.md`。
- 交付包`vendor/dependency-manifest.json`记录URL、文件散列和许可；未替换业务HAL。

从交付包中的冻结源码构建（PowerShell，当前目录为交付包）：

```powershell
cmake -S ./source/firmware/four-controller/diagnostics/sht-isolation -B ./rebuild -G Ninja "-DDIAG_I2C_HAL_DIR=$((Get-Location).Path)/vendor" '-DDIAG_BUILD_ID=ctrl02-isolation-20261030-1'
cmake --build ./rebuild
```

应先检查配置成功，再构建。编译、镜像指纹和脚本GPIO测试均不代替现场对照。

## 烧录、观测与回退

先确认2号UID为`05D7FF35 / 3930414D / 51145832`，备份Flash，下载地址`0x08000000`，写后校验及独立回读。恢复BOOT0/BOOT1均0并复位后，必须捕获`UT-DIAGNOSTIC:SHT:CTRL-02:ctrl02-isolation-20261030-1`，再连续观察至少两个完整阶段，不能把一次成功当作稳定恢复。

测试完成后，恢复`D:/shixi/deliverables/utility-tunnel-ctrl02-i2c-fix-20261030/CTRL-02/four_ctrl02.bin`（构建df9e8000f24e700c），再次写后回读并核对业务启动标识。最小诊断不能留作最终业务固件。
