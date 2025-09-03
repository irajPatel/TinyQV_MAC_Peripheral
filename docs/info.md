<!---

```markdown
<!--

This datasheet describes the INT16 Multiply-Accumulate (MAC) peripheral implemented in `src/peripheral.v`.
Fill in the peripheral index (slot) when you add this peripheral to the full TinyQV integration and set
`PERIPHERAL_NUM` in `test/test.py` to that slot.

-->

# INT16 Multiply-Accumulate (MAC) Peripheral for TinyQV

## Overview

This peripheral implements a 16×16 multiply and optional accumulate unit with a 48-bit signed accumulator. It supports signed/unsigned inputs, optional right-shift with rounding, and optional saturation. The peripheral is memory-mapped and integrates with the TinyQV SPI test harness.

## Features

- 16×16 multiply (32-bit product)
- 48-bit signed accumulator for MAC mode
- Signed/unsigned input selection
- Configurable right-shift amount (6 bits) with optional rounding
- Optional saturation with sticky flag
- Sticky DONE status and explicit CLEAR_DONE/CLEAR_ACC controls
- SPI-accessible registers and interrupt support

## Register map (addresses in `src/peripheral.v`)

| Address | Name       | Access | Description |
|---------|------------|--------|-------------|
| 0x20    | MAC_CTRL   | R/W    | Control register (see bitfields) |
| 0x24    | MAC_A      | R/W    | Operand A (lower 16 bits used) |
| 0x28    | MAC_B      | R/W    | Operand B (lower 16 bits used) |
| 0x2C    | MAC_PRODUCT| R      | Last product (32-bit) |
| 0x30    | MAC_ACC_H  | R      | Accumulator[47:32] (upper 16 bits) |
| 0x34    | MAC_ACC_M  | R      | Accumulator[31:16] (middle 16 bits) |
| 0x38    | MAC_ACC_L  | R      | Accumulator[15:0] (lower 16 bits) |

### MAC_CTRL bitfields

- bit 0: START — write 1 to start operation (when not busy)
- bit 1: MODE — 0 = MUL (product only), 1 = MAC (accumulate)
- bit 2: SIGNED — 1 = interpret operands as signed 16-bit
- bit 3: SATURATE_EN — saturate accumulator on overflow/underflow
- bit 4: ROUND_EN — enable rounding when right-shifting the product
- bits [10:5]: SHIFT — 6-bit right-shift amount applied to product before accumulation
- bit 11: CLEAR_ACC — write 1 to clear accumulator (clears SAT flag and sets DONE)
- bit 12: CLEAR_DONE — write 1 to clear the sticky DONE bit

Status overlay on read of `MAC_CTRL` (readback):
- bit 16: BUSY (1 when operation in progress)
- bit 17: DONE (sticky completion flag; W1 to clear via CLEAR_DONE)
- bit 18: SAT (saturation occurred on last commit)

Note: The control register readback overlays these status bits so software can poll the status
by reading `MAC_CTRL`.

## Behavior and semantics

- START: software writes START=1 to begin an operation if the peripheral is not busy. The START write sets an internal latch consumed by the core.
- DONE: the peripheral sets DONE = 1 when the operation commits; DONE is sticky and must be cleared by writing CLEAR_DONE = 1.
- CLEAR_ACC: writing CLEAR_ACC clears the accumulator and SAT flag, and (deliberately) sets DONE so software can observe completion. This W1-style semantics is documented and used by the testbench.
- SHIFT and ROUND: if SHIFT != 0 and ROUND_EN is set, the peripheral adds a rounding constant (1 << (SHIFT-1)) before arithmetic right shift. Negative products are rounded-away-from-zero accordingly.
- SATURATE: when SATURATE_EN is enabled and the accumulator would exceed representable 48-bit signed range, the accumulator saturates to defined SAT_MAX/SAT_MIN and the SAT status bit is set.
- Interrupt: `user_interrupt` is asserted when DONE or SAT is set; test harness maps this to `uio_out[0]` for tests.

## Pin usage

- `ui_in`: not used for start/stop in this design (control is via SPI register writes); avoid using `ui_in[7]` which is reserved for UART.
- `uo_out[1]`: DONE status
- `uo_out[2]`: SAT flag (saturation)
- SPI pins: `uio_out[0]` = user_interrupt (mapped in wrapper), `uio_out[1]` = data_ready, `uio_out[3]` = spi_miso, `uio_in[4]` = spi_cs_n, `uio_in[5]` = spi_clk, `uio_in[6]` = spi_mosi.

## Test notes

- Update `test/test.py` `PERIPHERAL_NUM` to the slot you will use in the full TinyQV integration. The included tests assume `MAC_CTRL` bit assignments and the CLEAR_ACC/CLEAR_DONE semantics described above.
- The SPI-based test harness performs 32-bit command transfers; shorter transactions zero-extend on the peripheral side.

## Quick integration checklist

1. Ensure `top_module` in `info.yaml` and `tt_wrapper.v` are consistent with this peripheral.
2. Set `PERIPHERAL_NUM` in `test/test.py` to the chosen slot.
3. Add this peripheral to the full TinyQV `src/peripherals.v` slot and update `docs` filename with the peripheral index when submitting.

``` 
| `0x14` | `CONTROL` | R | Control register and busy flag | `0x00000000` |
