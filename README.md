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

## 🏗️ Project Architecture & File Hierarchy

```
tinyqv-full-peripheral-template/
├── 📁 src/                          # Source code directory
│   ├── 🎯 peripheral.v              # 🆕 OUR MAC IMPLEMENTATION
│   ├── 🔗 tt_wrapper.v              # Interface wrapper (updated)
│   ├── ⚙️ config.json               # Project configuration
│   └── 📦 test_harness/             # SPI communication layer
│       ├── 📡 spi_reg.sv            # SPI protocol implementation
│       ├── 🔄 synchronizer.sv       # Signal synchronization
│       ├── ⬆️ rising_edge_detector.sv # Edge detection
│       └── ⬇️ falling_edge_detector.sv # Edge detection
├── 📁 test/                         # Test framework
│   ├── 🧪 test.py                   # 🆕 OUR COMPREHENSIVE TEST SUITE
│   ├── 🔌 tqv.py                    # TinyQV interface class
│   ├── 📊 tqv_reg.py                # SPI communication layer
│   ├── ⚡ tb.v                      # Testbench top-level
│   ├── 📈 tb.gtkw                   # GTKWave configuration
│   └── 🔧 Makefile                  # Build configuration
├── 📁 docs/                         # Documentation
│   └── 📋 info.md                   # Project information
├── 📁 .github/                      # GitHub workflows
├── 📁 .devcontainer/                # Development environment
└── 📄 README.md                     # This file
```

## 🔧 Dependencies & Requirements

### **System Requirements**
- **OS**: Linux (Ubuntu 20.04+ recommended)
- **Python**: 3.11+ (required for cocotb compatibility)
- **Memory**: 4GB+ RAM
- **Storage**: 2GB+ free space

### **Core Dependencies**
```bash
# Python packages (automatically installed)
pytest==8.3.4          # Testing framework
cocotb==1.9.2          # Hardware verification framework

# System packages (install with apt)
iverilog               # Verilog simulator
gtkwave                # Waveform viewer
```

### **Installation Commands**
```bash
# Update package list
sudo apt update

# Install Python 3.11 and tools
sudo apt install python3.11 python3.11-venv

# Install simulation tools
sudo apt install iverilog gtkwave

# Install Python dependencies
pip3 install pytest==8.3.4 cocotb==1.9.2

# Add local bin to PATH
export PATH="$HOME/.local/bin:$PATH"
```
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

### **🎉 Test Results - ALL TESTS PASSED! 🎉**

```
      ***********************************************************************************************************
                         ** TEST    STATUS  SIM TIME (ns)  REAL TIME (s)  RATIO (ns/s) **
      ***********************************************************************************************************
      ** test.test_mac_peripheral                            PASS      111250.00           1.71      65045.27  **
      ** test.test_register_read_write_smoke                 PASS       10430.00          -0.44     -23478.61  **
      ** test.test_mul_unsigned                              PASS       21440.00           0.33      64140.41  **
      ** test.test_mac_signed_accumulate                     PASS       36670.00           0.53      68682.26  **
      ** test.test_saturation_signed                         PASS       36670.00           0.55      67098.77  **
      ** test.test_signed_extremes                           PASS       62250.00           0.93      67114.42  **
      ** test.test_shift_rounding_boundaries                 PASS       31160.00           0.48      64966.68  **
      ** test.test_accumulation_overflow_and_random_stress   PASS       86200.00           1.33      64856.62  **
      ***********************************************************************************************************
      ** TESTS=8 PASS=8 FAIL=0 SKIP=0                                  396070.01           5.51      71936.61  **
      ***********************************************************************************************************
```

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

## 📚 Learning Resources

### **🔍 Key Concepts Covered**
- **Hardware Design**: State machines, counters, edge detection
- **Interface Design**: Memory-mapped registers, CPU communication
- **Testing**: Hardware verification, testbench design
- **System Integration**: Peripheral design, SPI communication

### **📖 Further Reading**
- [Tiny Tapeout Documentation](https://tinytapeout.com/)
- [Verilog Best Practices](https://www.verilog.com/)
- [Hardware Testing with cocotb](https://docs.cocotb.org/)
- [RISC-V Architecture](https://riscv.org/)

## 🤝 Contributing

### **🐛 Bug Reports**
Found an issue? Please report it with:
- Detailed description of the problem
- Steps to reproduce
- Expected vs. actual behavior
- System information

### **💡 Feature Requests**
Have an idea? We'd love to hear it! Consider:
- Use case and motivation
- Implementation approach
- Impact on existing functionality

### **🔧 Pull Requests**
Want to contribute? Great! Please:
- Fork the repository
- Create a feature branch
- Add tests for new functionality
- Ensure all tests pass
- Submit a pull request

## 📄 License

This project is licensed under the **Apache 2.0 License** - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Tiny Tapeout Team** for the amazing platform
- **Michael Bell** for the TinyQV CPU design
- **cocotb Community** for the excellent testing framework
- **Open Source Hardware Community** for inspiration

---



<div align="center">

**Made with ❤️ for the Tiny Tapeout Community**

[⭐ Star this repo](https://github.com/your-repo) | [🐛 Report issues](https://github.com/your-repo/issues) | [💬 Join discussion](https://github.com/your-repo/discussions)

</div>

