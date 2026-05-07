# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# ui_in bit positions
UNDERVOLTAGE  = 0b00000001  # ui_in[0]
MEDIUM_POWER  = 0b00000010  # ui_in[1]
HIGH_POWER    = 0b00000100  # ui_in[2]

# Expected uo_out[2:0] values per state
#   Reset / undervoltage / no flags → L1_STATE → only L1 ON
#   Medium power (stable)           → L2_STATE → L1 + L2 ON
#   High power   (stable + delay)   → L3_STATE → L1 + L2 + L3 ON
LOW_POWER_OUT    = 0x01  # 001 — L1 only
MEDIUM_POWER_OUT = 0x03  # 011 — L1 + L2
HIGH_POWER_OUT   = 0x07  # 111 — L1 + L2 + L3

# Cycle budgets (at 50 MHz / 10 µs sim period):
#   Sync latency:      2 cycles
#   Stability filter: 20 cycles  (STABLE_THRESHOLD)
#   WAIT state delay: 50 cycles  (DELAY_THRESHOLD)
#
#   Medium from L1:  2 + 20 + 50 = 72 cycles minimum → use 80
#   High from L1:    72 (WAIT_L2→L2) + 1 (L2 immediate stable) + 50 (WAIT_L3) = 123 → use 130
#   High from L2:    2 + 20 (restability on new flag) + 50 = 72 → use 80
#   Drop (de-esc):   2 (sync) + 2 (state steps) = 4 cycles → use 10
CYCLES_TO_MEDIUM = 80
CYCLES_TO_HIGH   = 130
CYCLES_TO_DROP   = 10


def load_enable(dut):
    return int(dut.uo_out.value) & 0x07


async def setup(dut):
    """Single source of truth for clock/reset. Guarantees all inputs start clean."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    dut.rst_n.value  = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value  = 1
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_reset_state(dut):
    """After reset with no flags, FSM must be in L1_STATE (L1 only)."""
    await setup(dut)
    await ClockCycles(dut.clk, 1)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Reset: expected 001, got {load_enable(dut):03b}"
    )
    dut._log.info("PASS: reset → L1_STATE (uo_out[2:0]=001)")


@cocotb.test()
async def test_undervoltage_mode(dut):
    """undervoltage_flag=1 → stay in L1_STATE (immediate, no stability needed to shed)."""
    await setup(dut)
    dut.ui_in.value = UNDERVOLTAGE
    await ClockCycles(dut.clk, 5)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Undervoltage: expected 001, got {load_enable(dut):03b}"
    )
    dut._log.info("PASS: undervoltage_flag=1 → L1_STATE")


@cocotb.test()
async def test_medium_power_mode(dut):
    """medium_power_flag stable for 20+ cycles + 50 WAIT cycles → L2_STATE."""
    await setup(dut)
    dut.ui_in.value = MEDIUM_POWER
    await ClockCycles(dut.clk, CYCLES_TO_MEDIUM)
    assert load_enable(dut) == MEDIUM_POWER_OUT, (
        f"Medium: expected 011, got {load_enable(dut):03b}"
    )
    dut._log.info("PASS: medium_power stable → L2_STATE (uo_out[2:0]=011)")


@cocotb.test()
async def test_high_power_mode(dut):
    """high_power_flag stable → through WAIT_L2 → L2 → WAIT_L3 → L3_STATE."""
    await setup(dut)
    dut.ui_in.value = HIGH_POWER
    await ClockCycles(dut.clk, CYCLES_TO_HIGH)
    assert load_enable(dut) == HIGH_POWER_OUT, (
        f"High: expected 111, got {load_enable(dut):03b}"
    )
    dut._log.info("PASS: high_power stable → L3_STATE (uo_out[2:0]=111)")


@cocotb.test()
async def test_undervoltage_overrides_high(dut):
    """undervoltage_flag beats high_power_flag immediately — safety priority holds."""
    await setup(dut)
    dut.ui_in.value = UNDERVOLTAGE | HIGH_POWER
    await ClockCycles(dut.clk, 5)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Priority: undervoltage must win → 001, got {load_enable(dut):03b}"
    )
    dut._log.info("PASS: undervoltage overrides high_power → L1_STATE")


@cocotb.test()
async def test_undervoltage_overrides_medium(dut):
    """undervoltage_flag beats medium_power_flag immediately."""
    await setup(dut)
    dut.ui_in.value = UNDERVOLTAGE | MEDIUM_POWER
    await ClockCycles(dut.clk, 5)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Priority: undervoltage must win → 001, got {load_enable(dut):03b}"
    )
    dut._log.info("PASS: undervoltage overrides medium_power → L1_STATE")


@cocotb.test()
async def test_no_flags_defaults_low(dut):
    """No flags → FSM stays in L1_STATE (safe default)."""
    await setup(dut)
    await ClockCycles(dut.clk, 5)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"No flags: expected 001, got {load_enable(dut):03b}"
    )
    dut._log.info("PASS: no flags → L1_STATE")


@cocotb.test()
async def test_dynamic_transitions(dut):
    """Full ramp-up then emergency drop: L1 → L2 → L3 → L2 → L1 (stepped de-escalation)."""
    await setup(dut)

    # Step 1: No flags → L1_STATE
    await ClockCycles(dut.clk, 5)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Step1: expected L1 (001), got {load_enable(dut):03b}"
    )

    # Step 2: Medium power stable → L2_STATE
    dut.ui_in.value = MEDIUM_POWER
    await ClockCycles(dut.clk, CYCLES_TO_MEDIUM)
    assert load_enable(dut) == MEDIUM_POWER_OUT, (
        f"Step2: expected L2 (011), got {load_enable(dut):03b}"
    )

    # Step 3: High power from L2_STATE → WAIT_L3 → L3_STATE
    dut.ui_in.value = HIGH_POWER
    await ClockCycles(dut.clk, CYCLES_TO_MEDIUM)
    assert load_enable(dut) == HIGH_POWER_OUT, (
        f"Step3: expected L3 (111), got {load_enable(dut):03b}"
    )

    # Step 4: Drop to medium only (clear high flag).
    # L3_STATE sees power_sync=2'b10 < 2'b11 -> steps to L2_STATE and HOLDS there
    # (medium power still present, so no further drop).
    dut.ui_in.value = MEDIUM_POWER
    await ClockCycles(dut.clk, CYCLES_TO_DROP)
    assert load_enable(dut) == MEDIUM_POWER_OUT, (
        f"Step4: expected L2 (011) after L3->L2 step-down, got {load_enable(dut):03b}"
    )

    # Step 5: Now drop medium too -> L2_STATE sees power_sync=2'b01 < 2'b10 -> L1_STATE
    dut.ui_in.value = UNDERVOLTAGE
    await ClockCycles(dut.clk, CYCLES_TO_DROP)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Step5: expected L1 (001) after L2->L1 step-down, got {load_enable(dut):03b}"
    )

    dut._log.info("PASS: L1->L2->L3->L2->L1 stepped de-escalation all correct")


@cocotb.test()
async def test_wait_state_abort(dut):
    """Power drop during WAIT_L2 must abort and return to L1_STATE without enabling L2."""
    await setup(dut)

    # Start escalation toward L2 (2 sync + 20 stable = 22 to enter WAIT_L2, then 10 inside)
    dut.ui_in.value = MEDIUM_POWER
    await ClockCycles(dut.clk, 35)

    # Pull power while WAIT_L2 is still counting — L2 must NOT have enabled
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, CYCLES_TO_DROP)
    assert load_enable(dut) == LOW_POWER_OUT, (
        f"Abort: WAIT_L2 must revert to L1, got {load_enable(dut):03b}"
    )
    dut._log.info("PASS: power drop during WAIT_L2 correctly aborted to L1_STATE")
