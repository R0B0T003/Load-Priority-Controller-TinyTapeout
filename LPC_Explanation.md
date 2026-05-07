# Load Priority Controller (LPC) — Detailed Explanation

**Authors:** Abiola Enoch, Omotosho Enoch, Esabu Blessing
**Platform:** Tiny Tapeout (Sky130A 130 nm CMOS PDK)
**Language:** Verilog
**Tile Size:** 1×1
**Version:** Smart Edition (6-state FSM with sync, stability filter, WAIT states, delay timer)

---

## Table of Contents

1. [What Is This Project?](#1-what-is-this-project)
2. [The Problem It Solves](#2-the-problem-it-solves)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [Signal Descriptions (Pin Map)](#4-signal-descriptions-pin-map)
5. [The Finite State Machine (FSM)](#5-the-finite-state-machine-fsm)
6. [Four Protection Mechanisms](#6-four-protection-mechanisms)
7. [Verilog Implementation Walkthrough](#7-verilog-implementation-walkthrough)
8. [Power States at a Glance](#8-power-states-at-a-glance)
9. [State Transition Table](#9-state-transition-table)
10. [Timing and Clocking](#10-timing-and-clocking)
11. [External Hardware Context](#11-external-hardware-context)
12. [Tiny Tapeout Integration](#12-tiny-tapeout-integration)
13. [Testing Infrastructure](#13-testing-infrastructure)
14. [CI/CD Pipeline (GitHub Actions)](#14-cicd-pipeline-github-actions)
15. [Build Configuration](#15-build-configuration)

---

## 1. What Is This Project?

The **Load Priority Controller (LPC)** is a digital hardware circuit designed and submitted to the [Tiny Tapeout](https://tinytapeout.com/) programme — an initiative that lets students and hobbyists design chips that are physically manufactured on real silicon using the open-source **Sky130A** process node (developed by SkyWater Technology and Google).

The LPC is a **smart power management controller**: it monitors how much electrical power is available in a system, decides which electrical loads (devices, subsystems, or circuits) should be switched ON or OFF, and does so with built-in protection against electrical hazards — all in hardware, without any software or firmware.

Think of it like a triage system for electricity. A hospital during a blackout keeps the ICU running before the cafeteria. This circuit does the same thing automatically, in real time, and safely — preventing inrush current spikes, filtering noise, and stepping loads up and down gradually.

---

## 2. The Problem It Solves

In embedded systems, renewable energy setups (solar, battery, inverter), or any power-constrained environment, several failure modes exist:

| Problem | Description |
|---|---|
| **Overload** | Too many loads switch ON at once, collapsing the supply voltage |
| **Inrush current** | Capacitive/inductive loads draw large spike current at turn-on |
| **Load hunting** | Noisy power rails cause loads to rapidly toggle ON/OFF |
| **Metastability** | Asynchronous flag signals sampled at the wrong moment corrupt digital logic |

Traditional solutions require a microcontroller running firmware. The LPC solves all four problems in **pure combinational + sequential logic**: no software, no processor, no firmware update needed. It is intrinsically fast, reliable, and deterministic.

---

## 3. System Architecture Overview

```
                        ┌────────────────────────────────────────────────────────┐
 undervoltage_flag ────►│  2-STAGE       STABILITY      6-STATE    DELAY         │
 medium_power_flag ────►│  SYNC          FILTER         FSM        TIMER         ├──► L1 (uo_out[0])
 high_power_flag   ────►│  (metastab.)   (anti-hunt)    (WAIT      (inrush       ├──► L2 (uo_out[1])
                        │                               states)    guard)        ├──► L3 (uo_out[2])
         clk       ────►│                                                        │
         rst_n     ────►│                                                        │
                        └────────────────────────────────────────────────────────┘
```

The design is built from seven sequential blocks inside a single Verilog module:

| Section | Type | Responsibility |
|---|---|---|
| Flag extraction + encoding | Combinational | Maps 3 flags → 2-bit `power_level` |
| 2-stage synchronizer | Sequential (2 FFs) | Eliminates metastability on async inputs |
| Stability detection | Sequential (counter) | Holds `stable=1` after 20 unchanged cycles |
| FSM state register | Sequential (FF) | Holds current state, updates on clock edge |
| Delay timer | Sequential (counter) | Counts 50 cycles during WAIT states |
| Next-state logic | Combinational | Computes next state from `power_sync` + `stable` + `delay_done` |
| Output logic | Combinational | Drives L1, L2, L3 based on current state |

---

## 4. Signal Descriptions (Pin Map)

### Inputs (via TinyTapeout `ui_in[7:0]`)

| Signal | Pin | Description |
|---|---|---|
| `undervoltage_flag` | `ui_in[0]` | Power critically low — highest priority safety signal |
| `medium_power_flag` | `ui_in[1]` | Moderate power available (enough for L1 + L2) |
| `high_power_flag` | `ui_in[2]` | Full power available (all loads can run) |
| `ui_in[7:3]` | — | Unused (tied to 0 internally) |
| `clk` | dedicated pin | Rising edge drives all state registers |
| `rst_n` | dedicated pin | Active-LOW asynchronous reset → L1_STATE |

### Outputs (via TinyTapeout `uo_out[7:0]`)

| Signal | Pin | Description |
|---|---|---|
| `L1` | `uo_out[0]` | Enable for Load 1 — highest priority, ON from reset |
| `L2` | `uo_out[1]` | Enable for Load 2 — ON in L2_STATE and L3_STATE |
| `L3` | `uo_out[2]` | Enable for Load 3 — ON only in L3_STATE |
| `uo_out[7:3]` | — | Unused (tied to 0) |

The `uio` bidirectional bus is entirely unused in this design.

---

## 5. The Finite State Machine (FSM)

The LPC uses a **6-state FSM encoded in 3 bits**.

### States

| State | Encoding | Outputs | Description |
|---|---|---|---|
| `IDLE` | `3'd0` | L1=0, L2=0, L3=0 | No power — all loads OFF. Transient; skipped after rst_n. |
| `L1_STATE` | `3'd1` | L1=1, L2=0, L3=0 | Safe minimum. Only L1 (highest priority) ON. Reset default. |
| `WAIT_L2` | `3'd2` | L1=1, L2=0, L3=0 | Holding before enabling L2. Timer counting 50 cycles. |
| `L2_STATE` | `3'd3` | L1=1, L2=1, L3=0 | L1 and L2 ON. Stable medium power. |
| `WAIT_L3` | `3'd4` | L1=1, L2=1, L3=0 | Holding before enabling L3. Timer counting 50 cycles. |
| `L3_STATE` | `3'd5` | L1=1, L2=1, L3=1 | All loads ON. Full power available. |

### State Transition Diagram

```
 rst_n LOW ──────────────────────────────────────────► L1_STATE
                                                           │
                                             power_sync == 2'b00
                                                           │
                                                           ▼
                                                         IDLE
                                                           │
                                                    stable == 1
                                                           │
                                                           ▼
                          ┌──── power_sync < 2'b10 ──── L1_STATE
                          │                                │
                          │                    power_sync >= 2'b10
                          │                    AND stable == 1
                          │                                │
                          │                                ▼
                          │                           WAIT_L2
                          │               (hold 50 clock cycles)
                          │                                │
                          │               power drop ──────┤── delay_done
                          │                   │            │
                          │                   ▼            ▼
                          └──────────── L1_STATE       L2_STATE
                                                           │
                          ┌──── power_sync < 2'b10 ────────┤
                          │                    power_sync == 2'b11
                          │                    AND stable == 1
                          │                                │
                          ▼                                ▼
                       L1_STATE                        WAIT_L3
                                           (hold 50 clock cycles)
                                                           │
                                           power drop ─────┤── delay_done
                                               │            │
                                               ▼            ▼
                                          L2_STATE      L3_STATE
                                               │            │
                          ┌────────────────────┘            │
                          │                    power_sync < 2'b11
                          │                                 │
                          ▼                                 │
                       L1_STATE ◄────────────── L2_STATE ◄─┘
```

### Reset Behaviour

`rst_n` (active-LOW, asynchronous) forces the FSM to `L1_STATE`, not `IDLE`. This guarantees that the highest-priority load (L1) is immediately active after power-on or an emergency reset, without waiting for the stability counter.

---

## 6. Four Protection Mechanisms

### 6.1 — 2-Stage Input Synchronizer

The three comparator flag signals (`undervoltage_flag`, `medium_power_flag`, `high_power_flag`) are **asynchronous** — they can change at any time, with no relationship to the rising edge of `clk`. If the FSM flip-flops sample one of these signals while it is mid-transition, the output could be neither 0 nor 1 — this is **metastability**. A metastable flip-flop can output an indeterminate voltage that corrupts all downstream logic.

The solution is a two-stage synchronizer: two D flip-flops in series, both clocked by `clk`. The first FF may go metastable, but it has a full clock period to resolve before the second FF samples it. The resolved, clean version (`power_sync`) is what the FSM uses.

```
power_level ──► [FF: p_s1] ──► [FF: p_s2] ──► power_sync ──► FSM
                    ↑               ↑
                   clk             clk
```

Cost: 2 cycles of latency. Benefit: metastability-free operation on real silicon.

### 6.2 — Stability Detection (Anti-Hunting Filter)

Power rails fluctuate. Without filtering, a 1-cycle glitch on the `high_power_flag` line would immediately trigger `WAIT_L3` and begin energising L3. This causes **load hunting** — rapid ON/OFF toggling that stresses the power supply and shortens component life.

The stability block maintains an 8-bit counter (`stable_count`) that increments each cycle `power_sync` matches its previous value (`prev_power`). When `power_sync` changes, the counter resets. The `stable` signal only goes HIGH after 20 consecutive identical readings.

**Escalation requires `stable=1`.** De-escalation does not — shedding loads on a power drop is time-critical and should never be delayed.

At 50 MHz: 20 cycles = **400 ns** minimum signal hold time before any load is added.

### 6.3 — WAIT States with Delay Timer

Even after stability, the FSM does not enable the next load immediately. It enters a WAIT state (`WAIT_L2` or `WAIT_L3`) where the current outputs are frozen while a delay counter runs.

During WAIT, the delay counter increments each clock cycle. When it reaches `DELAY_THRESHOLD = 50`, `delay_done` fires and the FSM advances to the next load state.

At 50 MHz: 50 cycles = **1 µs stagger** between each load pair.

This stagger is the difference between "three loads turning on simultaneously" (large current spike, possible voltage collapse) and "loads energising one at a time" (controlled ramp, stable supply).

If power drops **during** a WAIT state, the FSM immediately aborts back to the previous safe state — L2 or L1 never gets enabled from a cancelled sequence.

### 6.4 — Stepped De-Escalation

When power drops from `L3_STATE`:
- `power_sync < 2'b11` → next state = `L2_STATE` (L3 shed, L1+L2 kept)
- If power is still insufficient: `power_sync < 2'b10` → next state = `L1_STATE` (L2 shed too)

This two-step drop is gentler on inductive loads (motors, relays) which generate back-EMF when switched off. An abrupt full cut-off (L3→L1 in one cycle) causes a larger voltage spike than a stepped removal.

`undervoltage_flag` still has absolute priority — it encodes to `power_level=2'b01` regardless of all other flags, so de-escalation always ultimately reaches `L1_STATE` when undervoltage is asserted.

---

## 7. Verilog Implementation Walkthrough

The main module is [src/LPC.v](src/LPC.v).

### Module Interface

```verilog
module tt_um_load_priority_controller (
    input  wire [7:0] ui_in,    // flags on [2:0]
    output wire [7:0] uo_out,   // L1/L2/L3 on [2:0]
    input  wire [7:0] uio_in,   // unused
    output wire [7:0] uio_out,  // tied 0
    output wire [7:0] uio_oe,   // tied 0
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n     // active-LOW async reset
);
```

### Power Level Encoding

```verilog
wire [1:0] power_level;
assign power_level = undervoltage_flag ? 2'b01 :
                     high_power_flag   ? 2'b11 :
                     medium_power_flag ? 2'b10 :
                                        2'b01;
```

`undervoltage_flag` is first in the priority chain — it overrides high and medium flags even if they are simultaneously asserted.

### 2-Stage Synchronizer

```verilog
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        p_s1 <= 2'b01;  p_s2 <= 2'b01;
    end else begin
        p_s1 <= power_level;
        p_s2 <= p_s1;
    end
end
wire [1:0] power_sync = p_s2;
```

### Stability Counter

```verilog
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        prev_power <= 2'b01; stable_count <= 0;
    end else begin
        if (power_sync == prev_power)
            stable_count <= (stable_count == 8'hFF) ? 8'hFF : stable_count + 1;
        else begin
            stable_count <= 0;
            prev_power   <= power_sync;
        end
    end
end
wire stable = (stable_count >= 20);
```

The saturation at `8'hFF` prevents the counter wrapping to 0 (which would briefly clear `stable` every 256 cycles).

### Delay Timer

```verilog
always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        delay_count <= 0;
    else if ((state == WAIT_L2) || (state == WAIT_L3))
        delay_count <= delay_count + 1;
    else
        delay_count <= 0;  // resets whenever not in a WAIT state
end
wire delay_done = (delay_count >= 50);
```

### State Register

```verilog
always @(posedge clk or negedge rst_n) begin
    if (!rst_n)
        state <= L1_STATE;  // not IDLE — L1 is safe immediately after reset
    else
        state <= next_state;
end
```

### Next-State Logic (key excerpts)

```verilog
L1_STATE: begin
    if (power_sync == 2'b00)             next_state = IDLE;
    else if ((power_sync >= 2'b10) && stable) next_state = WAIT_L2;
end
WAIT_L2: begin
    if (power_sync < 2'b10)             next_state = L1_STATE;  // abort
    else if (delay_done)                next_state = L2_STATE;
end
L3_STATE: begin
    if (power_sync < 2'b11)             next_state = L2_STATE;  // stepped drop
end
```

### Output Logic

```verilog
always @(*) begin
    L1 = 0; L2 = 0; L3 = 0;
    case (state)
        L1_STATE, WAIT_L2:  L1 = 1;
        L2_STATE, WAIT_L3:  begin L1 = 1; L2 = 1; end
        L3_STATE:           begin L1 = 1; L2 = 1; L3 = 1; end
    endcase
end
```

WAIT states produce the same output as the preceding load state — existing loads stay ON while the timer counts, and the new load only appears when the FSM leaves the WAIT state.

---

## 8. Power States at a Glance

| State | `uo_out[2:0]` | L1 | L2 | L3 |
|---|---|---|---|---|
| IDLE | `000` | OFF | OFF | OFF |
| L1_STATE | `001` | ON | OFF | OFF |
| WAIT_L2 | `001` | ON | OFF | OFF |
| L2_STATE | `011` | ON | ON | OFF |
| WAIT_L3 | `011` | ON | ON | OFF |
| L3_STATE | `111` | ON | ON | ON |

L1 is the highest-priority load. It is ON in every valid operating state above IDLE and is the first to come back online after any reset or de-escalation.

---

## 9. State Transition Table

### Escalation (requires `stable=1` and `delay_done=1` for WAIT exits)

| Current State | Condition | Next State |
|---|---|---|
| IDLE | `stable` | L1_STATE |
| L1_STATE | `power_sync >= 2'b10` AND `stable` | WAIT_L2 |
| WAIT_L2 | `delay_done` AND `power_sync >= 2'b10` | L2_STATE |
| L2_STATE | `power_sync == 2'b11` AND `stable` | WAIT_L3 |
| WAIT_L3 | `delay_done` AND `power_sync == 2'b11` | L3_STATE |

### De-escalation (immediate — no stability filter)

| Current State | Condition | Next State |
|---|---|---|
| WAIT_L2 | `power_sync < 2'b10` | L1_STATE |
| L2_STATE | `power_sync < 2'b10` | L1_STATE |
| WAIT_L3 | `power_sync < 2'b11` | L2_STATE |
| L3_STATE | `power_sync < 2'b11` | L2_STATE |
| L1_STATE | `power_sync == 2'b00` | IDLE |

---

## 10. Timing and Clocking

- **Clock:** External, driven via dedicated `clk` pin. All state transitions happen on the **rising edge**.
- **Reset:** Asynchronous, active-LOW (`rst_n`). Takes effect immediately, forces `L1_STATE`.
- **Target Clock:** 50 MHz (20 ns period), configured in `src/config.json`.

### Latency Analysis

| Operation | Latency |
|---|---|
| Sync latency (async flag → FSM) | 2 clock cycles |
| Stability filter (before escalation) | 20 clock cycles = 400 ns at 50 MHz |
| WAIT state (per load step) | 50 clock cycles = 1 µs at 50 MHz |
| L1 → L2 total | ~72 cycles = 1.44 µs |
| L1 → L3 total | ~123 cycles = 2.46 µs |
| De-escalation (1 step, sync included) | ~4 cycles = 80 ns |

The critical path through the combinational logic is extremely shallow (a priority chain and a case statement), well within the 20 ns clock budget.

---

## 11. External Hardware Context

### Voltage Comparator Front-End

```
  Battery / Power Bus (V_BUS)
          │
          ▼
  ┌──────────────────────────────┐
  │  Resistive voltage divider   │
  │  + LM393 or LM339 comparator │──► undervoltage_flag  (threshold: e.g., < 3.0 V)
  │  Three reference thresholds  │──► medium_power_flag  (threshold: e.g., 3.5 V)
  │  set via R divider network   │──► high_power_flag    (threshold: e.g., 4.0 V)
  └──────────────────────────────┘
```

The comparator open-collector outputs are pulled up and wire directly to `ui_in[0:2]`. They change asynchronously with respect to the chip's clock — which is exactly why the 2-stage synchronizer exists.

### Load Switching Circuit

```
  uo_out[0] (L1) ──► ULN2003A gate driver ──► IRLZ44N N-MOSFET ──► Load 1 (e.g., control board)
  uo_out[1] (L2) ──► ULN2003A gate driver ──► IRLZ44N N-MOSFET ──► Load 2 (e.g., sensors)
  uo_out[2] (L3) ──► ULN2003A gate driver ──► IRLZ44N N-MOSFET ──► Load 3 (e.g., actuators)
```

Add flyback diodes (1N4007) across each inductive load. The 1 µs WAIT delay between load turn-ons limits peak inrush current well below the MOSFET gate driver rating.

### Power-On Reset Circuit

```
  3.3 V supply ──► 10 kΩ ──►rst_n pin
                               │
                             10 µF
                               │
                              GND
```

The RC circuit holds `rst_n` LOW for ~100 µs after power-on, ensuring the FSM starts in `L1_STATE` before the supply rail is stable enough to drive comparator flags. For a more precise POR, use MCP101 or DS1233 supervisor ICs.

---

## 12. Tiny Tapeout Integration

### How It Works

1. Designers submit Verilog with a standardised `tt_um_*` top-level wrapper interface.
2. All submissions are stitched into a single GDS file (GDSII — the chip layout format).
3. The chip is manufactured by SkyWater using the Sky130A 130 nm CMOS process.
4. Manufactured chips are returned to each designer.

### Module Name

The TinyTapeout-required top-level module name is `tt_um_load_priority_controller`, defined in `src/LPC.v` and declared in `info.yaml` as `top_module`.

### Pin Wiring

```
TT dedicated clk  → clk  (synchronous clock for all FFs)
TT dedicated rst_n → rst_n (active-LOW async reset)
ui_in[0] → undervoltage_flag
ui_in[1] → medium_power_flag
ui_in[2] → high_power_flag
uo_out[0] ← L1
uo_out[1] ← L2
uo_out[2] ← L3
uo_out[7:3] ← 5'b0 (unused, tied low)
uio_out, uio_oe ← 8'b0 (all bidirectional pins unused)
```

---

## 13. Testing Infrastructure

### Testbench: [test/tb.v](test/tb.v)

Standard TinyTapeout Verilog testbench. Instantiates `tt_um_load_priority_controller`, dumps signals to an FST waveform file for viewing in GTKWave or Surfer.

### Python Test Harness: [test/test.py](test/test.py)

Uses [cocotb](https://www.cocotb.org/) — Python-based hardware verification framework. 9 test cases covering all major behaviours:

| Test | What it verifies |
|---|---|
| `test_reset_state` | FSM lands in L1_STATE after rst_n |
| `test_undervoltage_mode` | undervoltage_flag → L1_STATE |
| `test_medium_power_mode` | medium_power stable 80+ cycles → L2_STATE |
| `test_high_power_mode` | high_power stable 130+ cycles → L3_STATE |
| `test_undervoltage_overrides_high` | undervoltage wins over high_power immediately |
| `test_undervoltage_overrides_medium` | undervoltage wins over medium_power immediately |
| `test_no_flags_defaults_low` | no flags → stays in L1_STATE |
| `test_dynamic_transitions` | Full L1→L2→L3→L2→L1 ramp with stepped de-escalation |
| `test_wait_state_abort` | Power drop during WAIT_L2 reverts to L1 without enabling L2 |

### Timing Constants in test.py

```python
CYCLES_TO_MEDIUM = 80   # 2 sync + 20 stable + 50 WAIT_L2
CYCLES_TO_HIGH   = 130  # above + 50 WAIT_L3 (stable already built)
CYCLES_TO_DROP   = 10   # 2 sync + 2 state steps for stepped de-escalation
HIGH_POWER_OUT   = 0x07 # uo_out[2:0] = 111 (L1+L2+L3, no L4)
```

### Running Tests

```bash
cd test && make -B          # RTL simulation (Icarus Verilog)
make -B GATES=yes           # Gate-level simulation (after GDS build)
gtkwave tb.fst              # View waveforms
```

---

## 14. CI/CD Pipeline (GitHub Actions)

| Workflow | Trigger | What It Does |
|---|---|---|
| [test.yaml](.github/workflows/test.yaml) | Push | Runs cocotb simulation, uploads FST waveform artifact |
| [gds.yaml](.github/workflows/gds.yaml) | Push | Full ASIC flow: synthesis → P&R → GDS → DRC/LVS → GL test → layout viewer |
| [docs.yaml](.github/workflows/docs.yaml) | Push | Generates project documentation page from `docs/info.md` |
| [fpga.yaml](.github/workflows/fpga.yaml) | Manual | Synthesises ICE40UP5K FPGA bitstream for prototyping |

---

## 15. Build Configuration

[src/config.json](src/config.json) configures the LibreLane/OpenLane ASIC build:

| Parameter | Value | Meaning |
|---|---|---|
| `CLOCK_PERIOD` | 20 ns | Target 50 MHz operation |
| `PL_TARGET_DENSITY_PCT` | 60 | 60% cell placement density within the 1×1 tile |
| `CLOCK_PORT` | `clk` | Signal used for clock tree synthesis |
| `RUN_LINTER` | 1 | Enable Verilog linting during synthesis |
| PDK | Sky130A | Open-source 130 nm CMOS process |

---

*This document reflects the Smart Edition of the LPC — the fully merged design including all four protection mechanisms (synchronizer, stability filter, WAIT states, delay timer). For the latest source, refer to [src/LPC.v](src/LPC.v) and [docs/info.md](docs/info.md).*
