#ifndef KK_UI_CATALOG_H
#define KK_UI_CATALOG_H

#include <stdint.h>

#include "ui_state.h"

/* Static application topology adapted from KK_UI's page-description model.
 * Strings and routes live for the complete UI lifetime; no heap or runtime
 * registration is used. */
typedef struct {
  UiPage page;
  const char *name;
  const char *diagnostic_title;
  uint8_t row_count;
  uint8_t wraps;
} KkUiPageDescriptor;

const KkUiPageDescriptor *KK_UI_CatalogPage(UiPage page);
UiPage KK_UI_CatalogHomeDestination(uint8_t row);
const char *KK_UI_CatalogHomeLabel(uint8_t row);
const char *KK_UI_CatalogSelectedName(UiPage page, uint8_t row);

#endif /* KK_UI_CATALOG_H */
