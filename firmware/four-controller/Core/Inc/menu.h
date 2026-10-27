#ifndef UT_MENU_H
#define UT_MENU_H
#include <stdint.h>
void Menu_Poll(uint32_t now);
void Menu_Session(uint32_t session);
uint8_t Menu_View(const uint16_t *registers,uint16_t count);
void Menu_Ack(const uint16_t *registers);
void Menu_Registers(uint16_t *registers,uint32_t now);
void Menu_Line(uint8_t row,char *text,unsigned size,uint32_t now);
#endif
