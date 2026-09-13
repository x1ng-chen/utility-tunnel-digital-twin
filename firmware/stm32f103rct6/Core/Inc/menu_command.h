#ifndef MENU_COMMAND_H
#define MENU_COMMAND_H

#include <stddef.h>
#include <stdint.h>

#include "ui_state.h"

#define MENU_COMMAND_ID_SIZE 40U
#define MENU_COMMAND_LINE_SIZE 256U
#define MENU_COMMAND_ACK_LINE_SIZE 768U
#define MENU_COMMAND_TTL_MS 10000U
#define MENU_COMMAND_TIMEOUT_MS 5000U
#define MENU_COMMAND_TX_CAPACITY MENU_COMMAND_LINE_SIZE

typedef struct {
  char active_command_id[MENU_COMMAND_ID_SIZE];
  uint32_t boot_id;
  uint32_t sequence;
  uint8_t pending;
} MenuCommandContext;

typedef struct {
  char command_id[MENU_COMMAND_ID_SIZE];
  uint8_t accepted;
  int32_t applied_value;
} MenuCommandAck;

typedef struct {
  uint8_t bytes[MENU_COMMAND_TX_CAPACITY];
  uint16_t length;
  uint16_t offset;
  uint8_t active;
  uint8_t failed;
} MenuCommandTxQueue;

/* The node stores the 16-bit counter in the STM32 backup domain (VBAT). */
uint32_t MenuCommand_NextBootId(uint16_t persisted_counter, uint32_t uid_mix);
void MenuCommand_Init(MenuCommandContext *context, uint32_t boot_id);
uint8_t MenuCommand_Begin(MenuCommandContext *context, UiAction action, uint8_t value,
                          uint64_t created_at_ms, char *line, size_t line_capacity,
                          size_t *written);
uint8_t MenuCommand_ParseAck(const char *line, size_t length, MenuCommandAck *ack);
uint8_t MenuCommand_AcceptAck(MenuCommandContext *context, const MenuCommandAck *ack);
void MenuCommandTx_Init(MenuCommandTxQueue *queue);
uint8_t MenuCommandTx_Enqueue(MenuCommandTxQueue *queue, const char *line, size_t length);
uint8_t MenuCommandTx_Peek(const MenuCommandTxQueue *queue, uint8_t *byte);
void MenuCommandTx_Commit(MenuCommandTxQueue *queue);
void MenuCommandTx_Fail(MenuCommandTxQueue *queue);

#endif /* MENU_COMMAND_H */
