"""Exercise the bench probe's result validator without a serial device."""

import ast
import pathlib


probe = pathlib.Path(__file__).with_name('display_serial_probe.py')
tree = ast.parse(probe.read_text(encoding='utf-8'), filename=str(probe))
validator = next(
    (node for node in tree.body
     if isinstance(node, ast.FunctionDef) and node.name == 'validate_display_stats'),
    None,
)
assert validator is not None, 'missing validate_display_stats'
namespace = {}
exec(compile(ast.Module(body=[validator], type_ignores=[]), str(probe), 'exec'), namespace)
validate = namespace['validate_display_stats']

valid = {
    'sysclk': '72000000', 'spi_hz': '18000000', 'dma_frames': '1003',
    'dma_timeouts': '0', 'dma_errors': '0', 'worst_frame_us': '22000',
}
validate(valid, True)

for field, value in (
    ('dma_frames', '1002'),
    ('dma_frames', '1004'),
    ('dma_timeouts', '1'),
    ('dma_errors', '1'),
    ('worst_frame_us', '22001'),
):
    invalid = dict(valid)
    invalid[field] = value
    try:
        validate(invalid, True)
    except AssertionError:
        pass
    else:
        raise AssertionError(f'accepted invalid {field}={value}')

print('Display serial probe validator test: PASS')
