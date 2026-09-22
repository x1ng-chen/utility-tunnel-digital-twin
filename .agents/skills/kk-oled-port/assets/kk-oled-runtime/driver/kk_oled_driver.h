#ifndef KK_OLED_DRIVER_H
#define KK_OLED_DRIVER_H

#include "kk_oled.h"

#include <stdbool.h>
#include <stdint.h>

/** 当前 CH1116 模组的物理宽度。 */
#define OLED_PHYSICAL_WIDTH 128U
/** 当前 CH1116 模组的物理高度。 */
#define OLED_PHYSICAL_HEIGHT 64U
/** 每页 8 行像素，因此 64 行屏幕共有 8 页。 */
#define OLED_PHYSICAL_PAGES (OLED_PHYSICAL_HEIGHT / 8U)

/** 初始化 CH1116，清空全部页并点亮显示。 */
OLED_Status OLED_DriverInit(void);

/** 阻塞发送核心准备好的全部差异页。 */
OLED_Status OLED_DriverWriteBlocking(void);

/** 使用 HAL I2C 中断依次发送页命令和页数据。 */
OLED_Status OLED_DriverWriteIT(void);

/** 使用中断发送页命令、DMA 发送页数据。 */
OLED_Status OLED_DriverWriteDMA(void);

/** 查询驱动异步状态机是否正在传输。 */
bool OLED_DriverIsBusy(void);

/** 阻塞发送 CH1116 对比度命令。 */
OLED_Status OLED_DriverSetContrast(uint8_t value);

/** 阻塞发送显示关闭 AE 或显示开启 AF。 */
OLED_Status OLED_DriverSetPowerSave(bool enable);

/* 由应用 HAL 回调转发，不直接占用 HAL 全局弱回调。 */
/** 处理一次 I2C Memory Write 完成事件并推进异步状态机。 */
void OLED_DriverHandleMemTxComplete(void);

/** 终止当前异步传输，并向核心报告错误。 */
void OLED_DriverHandleError(void);

#endif
