# CTRL-02 共用 I²C 诊断

独立诊断固件对比 PB10/PB11 上的 SHT30 和 INA226，使用软件 I²C 与硬件 I²C2 分阶段读取。USART1 115200 8N1 输出诊断结果。INA226 仅执行寄存器读取。CTRL-02 已恢复完整业务镜像，现场状态见[验收记录](../../../../docs/hardware/commissioning-20261103.md)。

诊断依赖 ST HAL v1.1.10 的 `Src/stm32f1xx_hal_i2c.c` 和 `Inc/stm32f1xx_hal_i2c.h`。依照[温湿度隔离诊断的依赖说明](../sht-isolation/README.md)从固定提交取得文件，按原目录结构放在同一个外部目录内。将该目录传给 CMake 的 `DIAG_I2C_HAL_DIR`。

```powershell
cmake -S firmware/four-controller/diagnostics/i2c-shared -B build/ctrl02-i2c-shared -G Ninja "-DDIAG_I2C_HAL_DIR=<HAL目录>"
cmake --build build/ctrl02-i2c-shared
```
