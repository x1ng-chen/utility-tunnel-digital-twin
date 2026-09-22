#include "kk_oled_driver.h"

#include "i2c.h"
#include "kk_oled_internal.h"

#include <string.h>

/* 当前文件是固定硬件适配边界：STM32 HAL、I2C1 与 CH1116 参数均集中在此。 */

/** HAL 使用左移一位后的 8 位形式设备地址。 */
#define OLED_I2C_ADDRESS ((uint16_t)(0x3DU << 1U))
/** I2C Memory Address 字节：后续内容为 CH1116 命令。 */
#define OLED_CONTROL_COMMAND 0x00U
/** I2C Memory Address 字节：后续内容为显示数据。 */
#define OLED_CONTROL_DATA 0x40U
/** 模组可见第 0 列相对 CH1116 内部显存的列偏移。 */
#define OLED_COLUMN_OFFSET 2U
/** 所有阻塞 I2C 调用的最长等待时间。 */
#define OLED_BLOCKING_TIMEOUT_MS 100U

/** 当前异步刷新采用的数据发送方式。 */
typedef enum {
    OLED_DRIVER_MODE_NONE = 0, /**< 没有异步任务，或正在阻塞调用。 */
    OLED_DRIVER_MODE_IT,       /**< 页命令和页数据都使用中断。 */
    OLED_DRIVER_MODE_DMA       /**< 页命令用中断，页数据用 DMA。 */
} OLED_DriverMode;

/** 单个脏页的异步发送阶段。 */
typedef enum {
    OLED_DRIVER_PHASE_COMMAND = 0, /**< 正在发送页号和起始列。 */
    OLED_DRIVER_PHASE_DATA          /**< 正在发送该页的连续差异数据。 */
} OLED_DriverPhase;

static volatile bool oled_driver_busy;              /**< 驱动状态机是否占用 I2C。 */
static volatile uint8_t oled_driver_page;            /**< 当前正在发送的物理页。 */
static volatile OLED_DriverPhase oled_driver_phase;  /**< 当前页的命令/数据阶段。 */
static volatile OLED_DriverMode oled_driver_mode;    /**< 当前 IT 或 DMA 模式。 */
static uint8_t oled_driver_command[3];               /**< 页号、列低位、列高位命令。 */

/** 将 STM32 HAL 状态转换为库的统一状态。 */
static OLED_Status oled_hal_status(HAL_StatusTypeDef status)
{
    if (status == HAL_OK) {
        return OLED_OK;
    }
    if (status == HAL_BUSY) {
        return OLED_BUSY;
    }
    return OLED_ERROR;
}

/** 通过控制字节 0x00 阻塞发送一组 CH1116 命令。 */
static HAL_StatusTypeDef oled_send_command_blocking(const uint8_t *command,
                                                     uint16_t length)
{
    return HAL_I2C_Mem_Write(&hi2c1, OLED_I2C_ADDRESS, OLED_CONTROL_COMMAND,
                             I2C_MEMADD_SIZE_8BIT, (uint8_t *)command, length,
                             OLED_BLOCKING_TIMEOUT_MS);
}

/** 通过控制字节 0x40 阻塞发送连续显存数据。 */
static HAL_StatusTypeDef oled_send_data_blocking(const uint8_t *data,
                                                  uint16_t length)
{
    return HAL_I2C_Mem_Write(&hi2c1, OLED_I2C_ADDRESS, OLED_CONTROL_DATA,
                             I2C_MEMADD_SIZE_8BIT, (uint8_t *)data, length,
                             OLED_BLOCKING_TIMEOUT_MS);
}

/** 根据当前页的首个差异列生成三字节页寻址命令。 */
static void oled_prepare_page_command(uint8_t page)
{
    uint8_t visible_column = (uint8_t)(OLED_InternalGetTransferMinX(page) +
                                       OLED_COLUMN_OFFSET); /* 加上模组列偏移后的控制器列号。 */

    /* CH1116 页寻址模式分别设置页号、列地址低四位和高四位。 */
    oled_driver_command[0] = (uint8_t)(0xB0U | page);
    oled_driver_command[1] = (uint8_t)(visible_column & 0x0FU);
    oled_driver_command[2] = (uint8_t)(0x10U | (visible_column >> 4U));
}

/** 从 first 开始寻找下一个存在差异区间的物理页。 */
static bool oled_find_next_page(uint8_t first, uint8_t *page)
{
    uint8_t candidate; /* 正在检查的候选页号。 */

    for (candidate = first; candidate < OLED_PHYSICAL_PAGES; ++candidate) {
        if (OLED_InternalGetTransferMinX(candidate) < OLED_PHYSICAL_WIDTH) {
            *page = candidate;
            return true;
        }
    }
    return false;
}

/**
 * 等待屏幕上电稳定，发送已验证初始化序列，逐页清零后再点亮。
 * 初始化阶段故意使用阻塞调用，保证返回时屏幕处于确定状态。
 */
OLED_Status OLED_DriverInit(void)
{
    /* 实物验证过的 CH1116 初始化序列，首字节 AE 保持显示关闭。 */
    static const uint8_t init_commands[] = {
        0xAEU,
        0x02U, 0x10U,
        0x40U,
        0xB0U,
        0x81U, 0xCFU,
        0xA1U,
        0xA6U,
        0xA8U, 0x3FU,
        0xADU, 0x8BU,
        0x33U,
        0xC8U,
        0xD3U, 0x00U,
        0xD5U, 0xC0U,
        0xD9U, 0x1FU,
        0xDAU, 0x12U,
        0xDBU, 0x40U
    };
    static const uint8_t zeros[OLED_PHYSICAL_WIDTH] = {0}; /**< 初始化清屏数据。 */
    uint8_t page; /**< 当前清零页。 */

    if (oled_driver_busy) {
        return OLED_BUSY;
    }
    oled_driver_busy = true;
    oled_driver_mode = OLED_DRIVER_MODE_NONE;
    HAL_Delay(20U);

    if (oled_send_command_blocking(init_commands, sizeof(init_commands)) != HAL_OK) {
        oled_driver_busy = false;
        return OLED_ERROR;
    }
    /* CH1116 采用页寻址，必须逐页设置地址并写入 128 个零字节。 */
    for (page = 0U; page < OLED_PHYSICAL_PAGES; ++page) {
        uint8_t command[3] = {
            (uint8_t)(0xB0U | page),
            (uint8_t)(OLED_COLUMN_OFFSET & 0x0FU),
            (uint8_t)(0x10U | (OLED_COLUMN_OFFSET >> 4U))
        };
        if (oled_send_command_blocking(command, sizeof(command)) != HAL_OK ||
            oled_send_data_blocking(zeros, sizeof(zeros)) != HAL_OK) {
            oled_driver_busy = false;
            return OLED_ERROR;
        }
    }
    {
        /* 所有页清零成功后才发送 AF，避免上电随机画面。 */
        const uint8_t display_on = 0xAFU;
        if (oled_send_command_blocking(&display_on, 1U) != HAL_OK) {
            oled_driver_busy = false;
            return OLED_ERROR;
        }
    }
    oled_driver_busy = false;
    return OLED_OK;
}

/** 按页阻塞发送核心生成的连续差异区间。 */
OLED_Status OLED_DriverWriteBlocking(void)
{
    const uint8_t *buffer = OLED_InternalGetTransferBuffer(); /**< 冻结的传输帧。 */
    uint8_t page; /**< 当前检查或发送的物理页。 */

    if (oled_driver_busy) {
        return OLED_BUSY;
    }
    oled_driver_busy = true;
    oled_driver_mode = OLED_DRIVER_MODE_NONE;
    for (page = 0U; page < OLED_PHYSICAL_PAGES; ++page) {
        uint8_t min_x = OLED_InternalGetTransferMinX(page); /**< 本页首个差异列。 */
        uint8_t max_x = OLED_InternalGetTransferMaxX(page); /**< 本页最后差异列。 */
        uint16_t length; /**< 本页需要连续发送的字节数。 */

        if (min_x >= OLED_PHYSICAL_WIDTH) {
            continue;
        }
        /* 每个脏页先重新定位，再从 min_x 连续写到 max_x。 */
        oled_prepare_page_command(page);
        length = (uint16_t)max_x - min_x + 1U;
        if (oled_send_command_blocking(oled_driver_command,
                                       sizeof(oled_driver_command)) != HAL_OK ||
            oled_send_data_blocking(buffer + (uint16_t)page * OLED_PHYSICAL_WIDTH + min_x,
                                    length) != HAL_OK) {
            oled_driver_busy = false;
            return OLED_ERROR;
        }
    }
    oled_driver_busy = false;
    return OLED_OK;
}

/** 使用中断启动当前页的三字节寻址命令。 */
static HAL_StatusTypeDef oled_start_async_command(void)
{
    oled_prepare_page_command(oled_driver_page);
    oled_driver_phase = OLED_DRIVER_PHASE_COMMAND;
    return HAL_I2C_Mem_Write_IT(&hi2c1, OLED_I2C_ADDRESS, OLED_CONTROL_COMMAND,
                                I2C_MEMADD_SIZE_8BIT, oled_driver_command,
                                sizeof(oled_driver_command));
}

/** 初始化异步状态机并启动第一个脏页的命令阶段。 */
static OLED_Status oled_start_async(OLED_DriverMode mode)
{
    HAL_StatusTypeDef hal_status; /* 首次 HAL 异步启动结果。 */
    uint8_t first_page;          /* 本次刷新首个需要发送的页。 */

    if (oled_driver_busy) {
        return OLED_BUSY;
    }
    if (!oled_find_next_page(0U, &first_page)) {
        return OLED_OK;
    }
    /* 状态必须在调用 HAL 前写好，完成回调才能正确识别当前阶段。 */
    oled_driver_busy = true;
    oled_driver_page = first_page;
    oled_driver_mode = mode;
    hal_status = oled_start_async_command();
    if (hal_status != HAL_OK) {
        oled_driver_busy = false;
        oled_driver_mode = OLED_DRIVER_MODE_NONE;
        return oled_hal_status(hal_status);
    }
    return OLED_OK;
}

OLED_Status OLED_DriverWriteIT(void)
{
    return oled_start_async(OLED_DRIVER_MODE_IT);
}

OLED_Status OLED_DriverWriteDMA(void)
{
    return oled_start_async(OLED_DRIVER_MODE_DMA);
}

bool OLED_DriverIsBusy(void)
{
    return oled_driver_busy;
}

OLED_Status OLED_DriverSetContrast(uint8_t value)
{
    const uint8_t command[2] = {0x81U, value}; /* 对比度命令及参数。 */

    if (oled_driver_busy) {
        return OLED_BUSY;
    }
    return oled_hal_status(oled_send_command_blocking(command, sizeof(command)));
}

OLED_Status OLED_DriverSetPowerSave(bool enable)
{
    uint8_t command = enable ? 0xAEU : 0xAFU; /* AE 关屏，AF 开屏。 */

    if (oled_driver_busy) {
        return OLED_BUSY;
    }
    return oled_hal_status(oled_send_command_blocking(&command, 1U));
}

/** 释放异步状态并把最终结果交回图形核心。 */
static void oled_finish_async(OLED_Status status)
{
    /* 先释放驱动 Busy，再通知核心完成缓冲区状态收尾。 */
    oled_driver_busy = false;
    oled_driver_mode = OLED_DRIVER_MODE_NONE;
    OLED_InternalTransferFinished(status);
}

/**
 * HAL 发送完成入口：命令完成后启动数据，数据完成后切换到下一脏页。
 * DMA 模式只改变数据阶段，页寻址命令始终由 IT 发送。
 */
void OLED_DriverHandleMemTxComplete(void)
{
    HAL_StatusTypeDef hal_status; /* 启动下一异步阶段的 HAL 返回值。 */

    if (!oled_driver_busy || oled_driver_mode == OLED_DRIVER_MODE_NONE) {
        return;
    }
    if (oled_driver_phase == OLED_DRIVER_PHASE_COMMAND) {
        const uint8_t *buffer = OLED_InternalGetTransferBuffer(); /**< 冻结帧首地址。 */
        uint8_t min_x = OLED_InternalGetTransferMinX(oled_driver_page); /**< 起始差异列。 */
        uint8_t max_x = OLED_InternalGetTransferMaxX(oled_driver_page); /**< 结束差异列。 */
        uint16_t length = (uint16_t)max_x - min_x + 1U; /**< 页数据长度。 */
        uint8_t *data = (uint8_t *)(buffer +
                                    (uint16_t)oled_driver_page * OLED_PHYSICAL_WIDTH + min_x); /**< 页数据首地址。 */

        /* 页地址已经发送完成，现在按模式启动本页数据传输。 */
        oled_driver_phase = OLED_DRIVER_PHASE_DATA;
        if (oled_driver_mode == OLED_DRIVER_MODE_DMA) {
            hal_status = HAL_I2C_Mem_Write_DMA(&hi2c1, OLED_I2C_ADDRESS,
                                               OLED_CONTROL_DATA,
                                               I2C_MEMADD_SIZE_8BIT, data, length);
        } else {
            hal_status = HAL_I2C_Mem_Write_IT(&hi2c1, OLED_I2C_ADDRESS,
                                              OLED_CONTROL_DATA,
                                              I2C_MEMADD_SIZE_8BIT, data, length);
        }
        if (hal_status != HAL_OK) {
            oled_finish_async(OLED_ERROR);
        }
        return;
    }

    {
        /* 页数据完成：没有后续脏页则结束，否则发送下一页地址。 */
        uint8_t next_page;
        if (!oled_find_next_page((uint8_t)(oled_driver_page + 1U), &next_page)) {
            oled_finish_async(OLED_OK);
            return;
        }
        oled_driver_page = next_page;
    }
    if (oled_start_async_command() != HAL_OK) {
        oled_finish_async(OLED_ERROR);
    }
}

/** HAL 错误入口，仅终止真正处于异步模式的传输。 */
void OLED_DriverHandleError(void)
{
    if (oled_driver_busy && oled_driver_mode != OLED_DRIVER_MODE_NONE) {
        oled_finish_async(OLED_ERROR);
    }
}
