"""Compile the exact Node B display-run accounting helpers on the host."""

import pathlib
import re
import subprocess
import tempfile


root = pathlib.Path(__file__).resolve().parent.parent
source = (root / 'Core/Src/node_b.c').read_text(encoding='utf-8')


def function(name):
    match = re.search(r'static (?:void|uint8_t) ' + name + r'\([^)]*\)\s*\{', source)
    assert match, f'missing production helper {name}'
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]


constants = re.findall(
    r'^#define DISPLAY_TEST_(?:DIRTY|COLOR|PRIMITIVE)_COUNT .+$',
    source, flags=re.MULTILINE,
)
assert len(constants) == 3, 'missing production display primitive counts'

harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "st7735_bus.h"
static uint16_t display_test_completed;
static uint8_t display_test_active;
static unsigned reset_calls;
void St7735Bus_ResetStats(void) { ++reset_calls; }
'''
harness += '\n'.join(constants) + '\n'
harness += function('DisplayTest_BeginRun') + '\n'
harness += function('DisplayTest_RecordPrimitive') + '\n'
harness += r'''
int main(void) {
  St7735BusStats before = {0}, after = {0};

  DisplayTest_BeginRun();
  assert(reset_calls == 1 && display_test_active && display_test_completed == 0);
  before.dma_frames = UINT32_MAX;
  after.dma_frames = 0;
  assert(!DisplayTest_RecordPrimitive(&before, &after));
  assert(display_test_active && display_test_completed == 1);

  before = after;
  assert(DisplayTest_RecordPrimitive(&before, &after));
  assert(!display_test_active && display_test_completed == 1);

  DisplayTest_BeginRun();
  before = (St7735BusStats){.dma_frames = 10};
  after = (St7735BusStats){.dma_frames = 11, .dma_errors = 1};
  assert(DisplayTest_RecordPrimitive(&before, &after));
  assert(!display_test_active && display_test_completed == 0);

  DisplayTest_BeginRun();
  before = (St7735BusStats){.dma_frames = 20};
  after = (St7735BusStats){.dma_frames = 20, .dma_timeouts = 1};
  assert(DisplayTest_RecordPrimitive(&before, &after));
  assert(!display_test_active && display_test_completed == 0);

  DisplayTest_BeginRun();
  for (uint32_t i = 0; i < 1003; ++i) {
    before = (St7735BusStats){.dma_frames = i};
    after = (St7735BusStats){.dma_frames = i + 1};
    const uint8_t terminal = DisplayTest_RecordPrimitive(&before, &after);
    assert(terminal == (i == 1002));
  }
  assert(!display_test_active && display_test_completed == 1003);
  puts("Display run accounting test: PASS");
}
'''

with tempfile.TemporaryDirectory() as tmp:
    binary = str(pathlib.Path(tmp) / 'display_run_test')
    subprocess.run(
        ['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-ICore/Inc',
         '-x', 'c', '-', '-o', binary],
        input=harness, text=True, cwd=root, check=True,
    )
    subprocess.run([binary], check=True)
