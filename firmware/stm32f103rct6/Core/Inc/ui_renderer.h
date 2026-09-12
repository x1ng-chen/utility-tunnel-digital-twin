#ifndef UI_RENDERER_H
#define UI_RENDERER_H

#include <stddef.h>
#include <stdint.h>

#include "ui_model.h"
#include "ui_state.h"

#define UI_RENDERER_SELECTION_MS 140U
#define UI_RENDERER_PAGE_MS 180U

typedef struct {
  uint32_t rendered_frames;
  uint32_t skipped_frames;
  uint32_t dirty_rectangles;
  uint32_t dirty_pixels;
  uint32_t full_screen_redraws;
  uint16_t last_dirty_rectangles;
  uint32_t last_dirty_pixels;
  int16_t last_selection_y;
  int16_t last_page_offset;
} UiRendererStats;

void UiRenderer_Init(void);
uint8_t UiRenderer_RenderFrame(const UiState *state, const UiSnapshot *snapshot, uint32_t now_ms);
void UiRenderer_GetStats(UiRendererStats *stats);
size_t UiRenderer_DescribeLayout(const UiState *state, const UiSnapshot *snapshot,
                                 char *output, size_t output_size);
uint8_t UiRenderer_PageFromName(const char *name, UiPage *page);
int16_t UiRenderer_InterpolatePixels(int16_t from, int16_t to, uint32_t start_ms,
                                     uint32_t duration_ms, uint32_t now_ms);

#endif /* UI_RENDERER_H */
