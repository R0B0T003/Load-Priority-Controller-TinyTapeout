# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# ui_in bit positions (matches LPC.v: ui_in[0]=undervoltage, [1]=medium, [2]=high)
UNDERVOLTAGE  = 0b00000001  # ui_in[0]
MEDIUM_POWER  = 0b00000010  # ui_in[1]
HIGH_POWER    = 0b00000100  # ui_in[2]

# Expected uo_out[3:0] values per mode
LOW_POWER_OUT    = 0x01  # 0001 — only L1
MEDIUM_POWER_OUT = 0x03  # 0011 — L1 + L2
HIGH_POWER_OUT   = 0x0F  # 1111 — all loads


def load_enable(dut):
    return int(dut.uo_out.value) & 0x0F


async def setup(dut):
    """FIX 3: Shared helper — single source of truth for clock/reset sequence."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    # FIX 1: Always initialize ALL inputs before reset so tests are self-contained.
    dut.ena.value    = 1
    dut.ui_in.value  = 0   # ← was missing in 7/8 tests
    dut.uio_in.value = 0
    dut.rst_n.value  = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value  = 1
    await ClockCycles(dut.clk, 1)  # one settled cycle before any test drives inputs


@cocotb.test()
async def test_reset_state(dut):
    """After reset with no flags, FSM must land in LOW_POWER_MODE."""
    await setup(dut)
    await ClockCycles(dut.clk, 1)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Reset: expected 0001, got {load_enable(dut):04b}"
    )
    dut._log.info("PASS: reset → LOW_POWER_MODE (load_enable=0001)")


@cocotb.test()
async def test_undervoltage_mode(dut):
    """undervoltage_flag=1 → LOW_POWER_MODE."""
    await setup(dut)
    dut.ui_in.value = UNDERVOLTAGE
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Undervoltage: expected 0001, got {load_enable(dut):04b}"
    )
    dut._log.info("PASS: undervoltage_flag=1 → LOW_POWER_MODE")


@cocotb.test()
async def test_medium_power_mode(dut):
    """medium_power_flag=1, undervoltage=0 → MEDIUM_POWER_MODE."""
    await setup(dut)
    dut.ui_in.value = MEDIUM_POWER
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == MEDIUM_POWER_OUT, (
        f"Medium: expected 0011, got {load_enable(dut):04b}"
    )
    dut._log.info("PASS: medium_power_flag=1 → MEDIUM_POWER_MODE")


@cocotb.test()
async def test_high_power_mode(dut):
    """high_power_flag=1, others=0 → HIGH_POWER_MODE."""
    await setup(dut)
    dut.ui_in.value = HIGH_POWER
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == HIGH_POWER_OUT, (
        f"High: expected 1111, got {load_enable(dut):04b}"
    )
    dut._log.info("PASS: high_power_flag=1 → HIGH_POWER_MODE")


@cocotb.test()
async def test_undervoltage_overrides_high(dut):
    """undervoltage_flag beats high_power_flag — safety priority must hold."""
    await setup(dut)
    dut.ui_in.value = UNDERVOLTAGE | HIGH_POWER
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Priority: undervoltage must win → 0001, got {load_enable(dut):04b}"
    )
    dut._log.info("PASS: undervoltage overrides high_power → LOW_POWER_MODE")


@cocotb.test()
async def test_undervoltage_overrides_medium(dut):
    """undervoltage_flag beats medium_power_flag."""
    await setup(dut)
    dut.ui_in.value = UNDERVOLTAGE | MEDIUM_POWER
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Priority: undervoltage must win → 0001, got {load_enable(dut):04b}"
    )
    dut._log.info("PASS: undervoltage overrides medium_power → LOW_POWER_MODE")


@cocotb.test()
async def test_no_flags_defaults_low(dut):
    """No flags asserted → FSM defaults to LOW_POWER_MODE."""
    await setup(dut)
    # ui_in is already 0 from setup() — no extra drive needed
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"No flags: expected 0001, got {load_enable(dut):04b}"
    )
    dut._log.info("PASS: no flags → LOW_POWER_MODE")


@cocotb.test()
async def test_dynamic_transitions(dut):
    """Full ramp-up then emergency drop: LOW → MED → HIGH → LOW(undervoltage)."""
    await setup(dut)
    # FIX 2: ui_in is guaranteed 0 from setup() now — no stale-flag window.

    # Step 1: No flags → LOW
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Step1: expected LOW (0001), got {load_enable(dut):04b}"
    )

    # Step 2: Medium power available → MED
    dut.ui_in.value = MEDIUM_POWER
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == MEDIUM_POWER_OUT, (
        f"Step2: expected MED (0011), got {load_enable(dut):04b}"
    )

    # Step 3: Full power → HIGH
    dut.ui_in.value = HIGH_POWER
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == HIGH_POWER_OUT, (
        f"Step3: expected HIGH (1111), got {load_enable(dut):04b}"
    )

    # Step 4: Voltage collapses mid-flight → emergency drop to LOW
    dut.ui_in.value = UNDERVOLTAGE
    await ClockCycles(dut.clk, 2)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Step4: expected LOW emergency (0001), got {load_enable(dut):04b}"
    )

    dut._log.info("PASS: LOW → MED → HIGH → LOW(emergency) all correct")
