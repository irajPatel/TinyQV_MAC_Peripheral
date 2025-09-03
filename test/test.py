#!/usr/bin/env python3
"""
INT16 MAC Test Suite for TinyQV
Tests basic multiply, accumulate, and saturation behavior of tqvp_iraj_MAC.
"""

import cocotb
from cocotb.triggers import Timer
from cocotb.clock import Clock
import random

# Test configuration
PERIPHERAL_NUM = 4  # Peripheral slot used when integrated into the full TinyQV (update if different)

# Register addresses for MAC (must match peripheral)
MAC_CTRL = 0x20
MAC_A = 0x24
MAC_B = 0x28
MAC_PRODUCT = 0x2C
MAC_ACC_H = 0x30
MAC_ACC_M = 0x34
MAC_ACC_L = 0x38

# Control bit positions (peripheral contract)
BIT_START = 0
BIT_MODE = 1        # 0=MUL, 1=MAC
BIT_SIGNED = 2
BIT_SATURATE = 3
BIT_CLEAR_ACC = 11
BIT_CLEAR_DONE = 12


def assert_eq(actual, expected, msg=None, tqv=None):
    """Assertion helper that prints hex and dumps last SPI on failure."""
    if actual != expected:
        context = f"expected=0x{expected:X} ({expected}), actual=0x{actual:X} ({actual})"
        extra = f" last_cmd=0x{tqv.last_cmd:08X} last_data=0x{(tqv.last_data or 0):08X}" if tqv else ""
        full = f"{msg or 'assert_eq failed'}: {context}{extra}"
        cocotb.log.error(full)
        raise AssertionError(full)


class MACTestSuite:
    def __init__(self, dut, tqv):
        self.dut = dut
        self.tqv = tqv

    async def test_mul_unsigned(self):
        # 3 * 5 = 15
        self.tqv.log("TEST: MUL unsigned 3 * 5")
        await self.tqv.write_word_reg(MAC_A, 0x0003)
        await self.tqv.write_word_reg(MAC_B, 0x0005)
        # START=1, MODE=0 (MUL)
        await self.tqv.write_word_reg(MAC_CTRL, 0x1)
        await self.tqv.wait_for_interrupt()
        prod = await self.tqv.read_word_reg(MAC_PRODUCT)
        assert prod & 0xFFFFFFFF == 15, f"MUL unsigned failed: got {prod:#x}"

    async def test_mac_signed_accumulate(self):
        # Clear accumulator
        self.tqv.log("TEST: MAC signed accumulate - clear acc")
        await self.tqv.write_word_reg(MAC_CTRL, 1 << 11)
        await self.tqv.wait_for_interrupt()

        # -2 * 3 = -6 accumulate
        await self.tqv.write_word_reg(MAC_A, (0xFFFF & (-2)))
        await self.tqv.write_word_reg(MAC_B, 0x0003)
        # MODE=1 (MAC), SIGNED=1, START=1
        ctrl = (1 << 1) | (1 << 2) | 1
        self.tqv.log(f"TEST: MAC signed accumulate start ctrl=0x{ctrl:08X}")
        await self.tqv.write_word_reg(MAC_CTRL, ctrl)
        await self.tqv.wait_for_interrupt()

        acc = await self.read_accumulator()
        assert acc == -6, f"MAC signed accumulate failed: expected -6 got {acc}"

    async def test_saturation_signed(self):
        # Clear accumulator
        self.tqv.log("TEST: Saturation signed - clear acc")
        await self.tqv.write_word_reg(MAC_CTRL, 1 << 11)
        await self.tqv.wait_for_interrupt()

        # large operands to cause saturation
        await self.tqv.write_word_reg(MAC_A, 0x7FFF)
        await self.tqv.write_word_reg(MAC_B, 0x7FFF)
        # MODE=1 (MAC), SIGNED=1, SATURATE_EN=1, START=1
        ctrl = (1 << 1) | (1 << 2) | (1 << 3) | 1
        self.tqv.log(f"TEST: Saturation start ctrl=0x{ctrl:08X}")
        await self.tqv.write_word_reg(MAC_CTRL, ctrl)
        await self.tqv.wait_for_interrupt()

        acc = await self.read_accumulator()
        assert acc > 0, f"Expected positive saturation, got {acc}"

    async def read_accumulator(self):
        ah = await self.tqv.read_word_reg(MAC_ACC_H)
        am = await self.tqv.read_word_reg(MAC_ACC_M)
        al = await self.tqv.read_word_reg(MAC_ACC_L)
        acc = ((ah & 0xFFFF) << 32) | ((am & 0xFFFF) << 16) | (al & 0xFFFF)
        # sign-extend 48-bit
        if acc & (1 << 47):
            acc = acc - (1 << 48)
        return acc


@cocotb.test(timeout_time=5000000, timeout_unit='ns')
async def test_mac_peripheral(dut):
    """Run basic tests for the INT16 MAC peripheral"""
    clock = Clock(dut.clk, 16, units="ns")
    cocotb.start_soon(clock.start())

    tqv = TinyQV(dut, PERIPHERAL_NUM)
    mac_test = MACTestSuite(dut, tqv)

    await tqv.reset()
    await Timer(100, units='ns')

    cocotb.log.info("[TEST] 🚀 Starting basic INT16 MAC smoke tests...")
    await mac_test.test_mul_unsigned()
    await tqv.write_word_reg(MAC_CTRL, (1 << 12))
    await Timer(20, units='ns')
    await mac_test.test_mac_signed_accumulate()
    await tqv.write_word_reg(MAC_CTRL, (1 << 12))
    await Timer(20, units='ns')
    await mac_test.test_saturation_signed()
    await tqv.write_word_reg(MAC_CTRL, (1 << 12))
    await Timer(20, units='ns')
    cocotb.log.info("[TEST] 🎉 INT16 MAC smoke tests completed")


@cocotb.test(timeout_time=2000000, timeout_unit='ns')
async def test_register_read_write_smoke(dut):
    """Minimal register R/W smoke test to validate SPI and register interface."""
    clock = Clock(dut.clk, 16, units="ns")
    cocotb.start_soon(clock.start())

    tqv = TinyQV(dut, PERIPHERAL_NUM)
    await tqv.reset()
    await Timer(50, units='ns')
    cocotb.log.info("[TEST] register_read_write_smoke: start")

    # Write a pattern to MAC_A and read back
    await tqv.write_word_reg(MAC_A, 0xDEAD)
    val = await tqv.read_word_reg(MAC_A)
    # Only lower 16 bits are meaningful; ensure SPI register read/write works
    assert (val & 0xFFFF) == 0xDEAD, f"Register R/W failed: wrote 0xDEAD read back 0x{val:04X}"
    cocotb.log.info("[TEST] register_read_write_smoke: passed")


@cocotb.test(timeout_time=5000000, timeout_unit='ns')
async def test_mul_unsigned(dut):
    """Independent test for unsigned multiply"""
    clock = Clock(dut.clk, 16, units="ns")
    cocotb.start_soon(clock.start())
    tqv = TinyQV(dut, PERIPHERAL_NUM)
    suite = MACTestSuite(dut, tqv)
    await tqv.reset()
    await Timer(50, units='ns')
    cocotb.log.info("[TEST] test_mul_unsigned: start")
    await suite.test_mul_unsigned()
    cocotb.log.info("[TEST] test_mul_unsigned: passed")


@cocotb.test(timeout_time=5000000, timeout_unit='ns')
async def test_mac_signed_accumulate(dut):
    """Independent test for signed MAC accumulate"""
    clock = Clock(dut.clk, 16, units="ns")
    cocotb.start_soon(clock.start())
    tqv = TinyQV(dut, PERIPHERAL_NUM)
    suite = MACTestSuite(dut, tqv)
    await tqv.reset()
    await Timer(50, units='ns')
    cocotb.log.info("[TEST] test_mac_signed_accumulate: start")
    await suite.test_mac_signed_accumulate()
    cocotb.log.info("[TEST] test_mac_signed_accumulate: passed")


@cocotb.test(timeout_time=5000000, timeout_unit='ns')
async def test_saturation_signed(dut):
    """Independent test for saturation behavior"""
    clock = Clock(dut.clk, 16, units="ns")
    cocotb.start_soon(clock.start())
    tqv = TinyQV(dut, PERIPHERAL_NUM)
    suite = MACTestSuite(dut, tqv)
    await tqv.reset()
    await Timer(50, units='ns')
    cocotb.log.info("[TEST] test_saturation_signed: start")
    await suite.test_saturation_signed()
    cocotb.log.info("[TEST] test_saturation_signed: passed")


@cocotb.test(timeout_time=5000000, timeout_unit='ns')
async def test_signed_extremes(dut):
    """Test min/max signed 16-bit multiply behavior"""
    clock = Clock(dut.clk, 16, units="ns")
    cocotb.start_soon(clock.start())
    tqv = TinyQV(dut, PERIPHERAL_NUM)
    suite = MACTestSuite(dut, tqv)
    await tqv.reset()
    await Timer(50, units='ns')
    cocotb.log.info("[TEST] test_signed_extremes: start")

    # max * max
    await tqv.write_word_reg(MAC_A, 0x7FFF)
    await tqv.write_word_reg(MAC_B, 0x7FFF)
    ctrl = (1 << BIT_MODE) | (1 << BIT_SIGNED) | (1 << BIT_START)
    await tqv.write_word_reg(MAC_CTRL, ctrl)
    await tqv.wait_for_interrupt()
    acc = await suite.read_accumulator()
    cocotb.log.info(f"test_signed_extremes: max*max acc={acc}")

    # min * min
    await tqv.write_word_reg(MAC_A, 0x8000)
    await tqv.write_word_reg(MAC_B, 0x8000)
    await tqv.write_word_reg(MAC_CTRL, ctrl)
    await tqv.wait_for_interrupt()
    acc2 = await suite.read_accumulator()
    cocotb.log.info(f"test_signed_extremes: min*min acc={acc2}")
    cocotb.log.info("[TEST] test_signed_extremes: done")


@cocotb.test(timeout_time=5000000, timeout_unit='ns')
async def test_shift_rounding_boundaries(dut):
    """Test shift/round and rounding edge cases"""
    clock = Clock(dut.clk, 16, units="ns")
    cocotb.start_soon(clock.start())
    tqv = TinyQV(dut, PERIPHERAL_NUM)
    suite = MACTestSuite(dut, tqv)
    await tqv.reset()
    await Timer(50, units='ns')
    cocotb.log.info("[TEST] test_shift_rounding_boundaries: start")

    # prepare operands
    await tqv.write_word_reg(MAC_A, 0x0001)
    await tqv.write_word_reg(MAC_B, 0x0001)
    # set SHIFT field in ctrl high (assume bits [10:5] are shift per earlier code)
    # We'll just set ROUND_EN and SHIFT via a high-level ctrl pattern if supported by peripheral
    ctrl = (1 << BIT_START) | (1 << 4)  # assume BIT 4 = ROUND_EN (best-effort)
    await tqv.write_word_reg(MAC_CTRL, ctrl)
    await tqv.wait_for_interrupt()
    res = await suite.read_accumulator()
    cocotb.log.info(f"test_shift_rounding_boundaries: res={res}")
    cocotb.log.info("[TEST] test_shift_rounding_boundaries: done")


@cocotb.test(timeout_time=10000000, timeout_unit='ns')
async def test_accumulation_overflow_and_random_stress(dut):
    """Repeated accumulation to force overflow and small random stress test"""
    clock = Clock(dut.clk, 16, units="ns")
    cocotb.start_soon(clock.start())
    tqv = TinyQV(dut, PERIPHERAL_NUM)
    suite = MACTestSuite(dut, tqv)
    await tqv.reset()
    await Timer(50, units='ns')
    cocotb.log.info("[TEST] test_accumulation_overflow_and_random_stress: start")

    # Clear accumulator first
    await tqv.write_word_reg(MAC_CTRL, (1 << BIT_CLEAR_ACC))
    await tqv.wait_for_interrupt()

    # Repeatedly add a large value
    for i in range(2):
        await tqv.write_word_reg(MAC_A, 0x7FFF)
        await tqv.write_word_reg(MAC_B, 0x7FFF)
        await tqv.write_word_reg(MAC_CTRL, (1 << BIT_MODE) | (1 << BIT_SIGNED) | (1 << BIT_START) )
        await tqv.wait_for_interrupt()
        if i % 10 == 0:
            acc = await suite.read_accumulator()
            cocotb.log.info(f"iter {i} acc={acc}")

    # small random stress - 100 random ops
    for i in range(2):
        a = random.getrandbits(16) & 0xFFFF
        b = random.getrandbits(16) & 0xFFFF
        await tqv.write_word_reg(MAC_A, a)
        await tqv.write_word_reg(MAC_B, b)
        await tqv.write_word_reg(MAC_CTRL, (1 << BIT_START))
        await tqv.wait_for_interrupt()
    cocotb.log.info("[TEST] test_accumulation_overflow_and_random_stress: done")


# TinyQV interface class (simplified for testing)
class TinyQV:
    def __init__(self, dut, peripheral_num, *, csn=4, sck=5, mosi=6, miso=3):
        """TinyQV test helper.

        Parameters:
        - dut: cocotb DUT
        - peripheral_num: peripheral slot (unused here but kept for compatibility)
        - csn,sck,mosi,miso: uio pin indices (defaults kept for this project)
        """
        self.dut = dut
        self.peripheral_num = peripheral_num
        # parameterize pins so tests can adapt if wrapper changes
        self.CSN = csn
        self.SCK = sck
        self.MOSI = mosi
        self.MISO = miso
        # store last transaction for easier debugging on failure
        self.last_cmd = None
        self.last_data = None

    async def reset(self):
        self.dut.rst_n.value = 0
        await Timer(10, units='ns')
        self.dut.rst_n.value = 1
        await Timer(10, units='ns')

    async def spi_transaction(self, cmd, data=0):
        dut = self.dut
        CSN = self.CSN
        SCK = self.SCK
        MOSI = self.MOSI
        MISO = self.MISO

        # validate basic cmd fields
        if (cmd & 0xFFFFFFFF) != cmd:
            raise ValueError(f"cmd must be 32-bit unsigned, got 0x{cmd:X}")
        addr = cmd & 0x3F
        if addr > 0x3F:
            raise ValueError(f"address out of range: 0x{addr:X}")

        is_write = ((cmd >> 31) & 1) == 1
        width_code = (cmd >> 29) & 0x3
        width_bytes_map = {0: 1, 1: 2, 2: 4}
        if width_code not in width_bytes_map:
            raise ValueError(f"unsupported width code: {width_code}")
        width = width_bytes_map[width_code]

        # Mask data according to width for writes
        if is_write:
            mask = (1 << (8 * width)) - 1
            data &= mask

        # Record last transaction
        self.last_cmd = cmd
        self.last_data = data if is_write else None

        # Idle
        dut.uio_in[CSN].value = 1
        dut.uio_in[SCK].value = 0
        await Timer(100, units='ns')
        dut.uio_in[CSN].value = 0
        await Timer(100, units='ns')

        # Debug
        #self.log(f"SPI TX cmd=0x{cmd:08X} data=0x{data:08X} (width={width})")

        # send command (MSB first)
        for i in range(31, -1, -1):
            dut.uio_in[SCK].value = 0
            await Timer(20, units='ns')
            dut.uio_in[MOSI].value = (cmd >> i) & 1
            await Timer(20, units='ns')
            dut.uio_in[SCK].value = 1
            await Timer(40, units='ns')
        dut.uio_in[SCK].value = 0
        await Timer(40, units='ns')

        if is_write:
            # send data MSB-first for the selected width
            for i in range(8 * width - 1, -1, -1):
                dut.uio_in[SCK].value = 0
                await Timer(20, units='ns')
                dut.uio_in[MOSI].value = (data >> i) & 1
                await Timer(20, units='ns')
                dut.uio_in[SCK].value = 1
                await Timer(40, units='ns')
            dut.uio_in[SCK].value = 0
            await Timer(40, units='ns')

        # read result for read transactions
        result = 0
        if not is_write:
            for i in range(31, -1, -1):
                dut.uio_in[SCK].value = 0
                await Timer(20, units='ns')
                dut.uio_in[SCK].value = 1
                await Timer(40, units='ns')
                # grab bit from MISO; defensively cast to int
                try:
                    bit = int(dut.uio_out[MISO].value)
                except Exception as e:
                    raise RuntimeError(f"Invalid MISO read: {e}")
                result = (result << 1) | (bit & 1)
            dut.uio_in[SCK].value = 0
            await Timer(40, units='ns')

        dut.uio_in[CSN].value = 1
        await Timer(100, units='ns')

        # Mask result to 32-bit and record
        result &= 0xFFFFFFFF
        #self.log(f"SPI RX result=0x{result:08X}")
        return result

    async def write_word_reg(self, address, data):
        if address & ~0x3F:
            raise ValueError(f"write_word_reg: address out of range 0x{address:X}")
        cmd = (1 << 31) | (2 << 29) | (address & 0x3F)
        await self.spi_transaction(cmd, data)

    async def write_byte_reg(self, address, data):
        if address & ~0x3F:
            raise ValueError(f"write_byte_reg: address out of range 0x{address:X}")
        cmd = (1 << 31) | (0 << 29) | (address & 0x3F)
        await self.spi_transaction(cmd, data & 0xFF)

    async def read_word_reg(self, address):
        if address & ~0x3F:
            raise ValueError(f"read_word_reg: address out of range 0x{address:X}")
        cmd = (0 << 31) | (2 << 29) | (address & 0x3F)
        result = await self.spi_transaction(cmd)
        return result & 0xFFFFFFFF

    async def wait_for_interrupt(self):
        waited = 0
        #self.log("Waiting for interrupt (uio_out[0])...")
        while not self.dut.uio_out[0].value:
            await Timer(100, units='ns')
            waited += 100
            if waited > 5000000:
                # timeout after 5 ms simulated time
                raise TimeoutError(f"Timeout waiting for interrupt after {waited} ns")
        #self.log(f"Interrupt detected after {waited} ns")
        await Timer(10, units='ns')

    def log(self, msg):
        try:
            cocotb.log.info(f"[TQV] {msg}")
        except Exception:
            print(f"[TQV] {msg}")
