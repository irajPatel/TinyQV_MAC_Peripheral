![](../../workflows/gds/badge.svg) ![](../../workflows/docs/badge.svg) ![](../../workflows/test/badge.svg) ![](../../workflows/fpga/badge.svg)

# INT16 MAC Peripheral for TinyQV — Compact Accelerator for Tiny Tapeout 🚀

This repository contains a complete TinyQV peripheral: a compact INT16 Multiply-Accumulate (MAC) accelerator designed for Tiny Tapeout and the RISC-V peripheral challenge. It includes RTL, documentation, and a cocotb testbench so you can run thorough verification locally.

Why this is exciting
- Small, fast hardware MAC: 16×16 multiply with optional accumulate into a 48-bit signed accumulator.
- Useful for DSP-like tasks, sensor fusion, or as a building block for more advanced accelerators.
- Ready for Tiny Tapeout submission with docs, tests, and integration notes.

Quick links
- Docs/datasheet: `docs/info.md`
- RTL: `src/peripheral.v`
- Testbench & sims: `test/test.py`, `test/Makefile`

## Repo structure (what each thing does)
- `src/`
  - `peripheral.v` — The INT16 MAC RTL (control, product, 48-bit accumulator, saturation, rounding).
  - `tt_wrapper.v` — Test wrapper exposing SPI pins and mapping `user_interrupt`/`data_ready` to `uio` lines for the testbench.
  - `test_harness/` — Helper SV modules used by the wrapper (SPI shift register, synchronizers, edge detectors).
- `test/`
  - `test.py` — cocotb test suite that drives the peripheral over the wrapper's SPI interface.
  - `Makefile`, `tb.v`, and simulation build artifacts are managed here.
- `docs/`
  - `info.md` — Peripheral datasheet and register map (updated to describe the INT16 MAC).
- `info.yaml` — Project metadata used by Tiny Tapeout tools and CI.

## Peripheral capabilities (short)
- Operands: `MAC_A` and `MAC_B` (lower 16 bits used)
- Product: 32-bit at `MAC_PRODUCT` (0x2C)
- Accumulator: 48-bit signed (`MAC_ACC_H/M/L` at 0x30/0x34/0x38)
- Control at `MAC_CTRL` (0x20): START, MODE (MUL vs MAC), SIGNED, SATURATE_EN, ROUND_EN, SHIFT[10:5], CLEAR_ACC, CLEAR_DONE
- Status overlay on read of `MAC_CTRL`: BUSY (bit16), DONE (bit17, sticky), SAT (bit18)
- Interrupt asserted when DONE or SAT (mapped to `uio_out[0]` in the wrapper)

## How testing works
- The wrapper converts SPI transactions on `uio` pins into register reads/writes for the peripheral.
- The cocotb testbench (`test/test.py`) bit-bangs SPI over `uio_in` and `uio_out` to exercise registers and waits for `user_interrupt`.
- Tests are split into independent `@cocotb.test()` functions with timeouts and include corner case checks (saturation, signed edge cases, rounding).

SPI command format (used by test harness)
- 32-bit command word:
  - bit31: R/W (1 = write, 0 = read)
  - bits30-29: width (0 = 8b, 1 = 16b, 2 = 32b)
  - bits5-0: register address (6-bit)
- For writes, a 32-bit data word follows. Reads return a 32-bit value (masked by the wrapper for narrower widths).

## How to run the tests locally
1. Initialize submodules:
```
git submodule update --init --recursive
```
2. Install Python deps (from repo root):
```
pip install -r test/requirements.txt
```
3. Run the RTL sim from `test/`:
```
make -B
```
- Waveforms and logs are produced under `test/sim_build`.

## Important behavior notes (read before testing)
- `MAC_CTRL` readback overlays BUSY/DONE/SAT status bits into the control register for easy polling.
- `CLEAR_ACC` clears the accumulator and SAT flag, and intentionally sets DONE (documented W1 behavior) so tests can observe completion via the interrupt. Use `CLEAR_DONE` (bit 12) to clear the sticky DONE bit.
- Partial writes are supported (8/16/32 bits) through the wrapper's `data_write_n` signals.

## Dependencies
- cocotb (Python verification framework)
- Icarus Verilog (`iverilog`, `vvp`) for RTL sim
- Python 3.8+ and packages from `test/requirements.txt`
- GTKWave (optional) to view waveforms

## Contribution & extension ideas
- Add more unit tests or formal properties.
- Expose extra status registers for improved observability.
- Pipeline the MAC for higher throughput.

## Acknowledgements
Thanks to the many projects and people that make this possible:
- Tiny Tapeout and the TinyQV project for the platform and competition (https://tinytapeout.com)
- cocotb authors and maintainers for the Python verification framework (https://docs.cocotb.org)
- Icarus Verilog for RTL simulation
- GTKWave for waveform viewing
- The TinyQV community and examples from Michael Bell and contributors

Maintainer: Iraj Patel — see `info.yaml` for contact metadata.

Happy hacking — good luck with your Tiny Tapeout submission! 🎯
