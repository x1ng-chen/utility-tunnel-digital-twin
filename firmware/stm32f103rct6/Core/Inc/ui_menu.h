#ifndef UI_MENU_H
#define UI_MENU_H

#include <stddef.h>
#include <stdint.h>

/*
 * Physical input is deliberately separated from the interface. The three
 * board keys are only a temporary adapter; a joystick can later emit these
 * same events without changing menu or screen code.
 */
typedef enum {
  UI_INPUT_NONE = 0,
  UI_INPUT_UP,
  UI_INPUT_DOWN,
  UI_INPUT_LEFT,
  UI_INPUT_RIGHT,
  UI_INPUT_OK,
  UI_INPUT_BACK,
} UiInput;

typedef struct {
  uint8_t temperature;
  uint8_t humidity;
  uint16_t waterRaw;
  uint8_t dhtOk;
  uint8_t vibrationAlarm;
  uint8_t telemetryTxEnabled;
} UiTelemetry;

void UI_MenuInit(void);
void UI_MenuSetTelemetry(const UiTelemetry *telemetry);
void UI_MenuHandleInput(UiInput input);
void UI_MenuTick(uint32_t nowMs);
size_t UI_MenuDescribeLayout(char *output, size_t outputSize);

#endif /* UI_MENU_H */
