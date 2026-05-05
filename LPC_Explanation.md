# Load Priority Controller (LPC) — Detailed Explanation

**Authors:** Abiola Enoch, Omotosho Enoch, Esabu Blessing. 
**Platform:** Tiny Tapeout (TinyTapeout / tt-gds, Sky130A PDK)  
**Language:** Verilog  
**Tile Size:** 1×1  

---

## Table of Contents

1. [What Is This Project?](#1-what-is-this-project)
2. [The Problem It Solves](#2-the-problem-it-solves)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [Signal Descriptions (Pin Map)](#4-signal-descriptions-pin-map)
5. [The Finite State Machine (FSM)](#5-the-finite-state-machine-fsm)
6. [Verilog Implementation Walkthrough](#6-verilog-implementation-walkthrough)
7. [Power Modes at a Glance](#7-power-modes-at-a-glance)
8. [State Transition Table](#8-state-transition-table)
9. [Timing and Clocking](#9-timing-and-clocking)
10. [External Hardware Context](#10-external-hardware-context)
11. [Tiny Tapeout Integration](#11-tiny-tapeout-integration)
12. [Testing Infrastructure](#12-testing-infrastructure)
13. [CI/CD Pipeline (GitHub Actions)](#13-cicd-pipeline-github-actions)
14. [Build Configuration](#14-build-configuration)
15. [Known Gaps / Next Steps](#15-known-gaps--next-steps)

---

## 1. What Is This Project?

The **Load Priority Controller (LPC)** is a digital hardware circuit designed and submitted to the [Tiny Tapeout](https://tinytapeout.com/) programme — an initiative that lets students and hobbyists design chips that are physically manufactured on real silicon using the open-source **Sky130A** process node (developed by SkyWater Technology and Google).

The LPC is a **power management controller**: it monitors how much electrical power is available in a system and decides which electrical loads (devices, subsystems, or circuits) should be switched ON or OFF at any given moment. The core idea is *load shedding* — when power is scarce, lower-priority consumers are turned off first so that the most critical systems stay alive.

Think of it like a triage system for electricity. A hospital during a blackout keeps the ICU running before the cafeteria. This circuit does the same thing in hardware, automatically and in real time.

---

## 2. The Problem It Solves

In embedded systems, renewable energy setups (solar, battery), or any power-constrained environment, a common failure mode is **overload** — too many devices drawing power at once, causing the supply voltage to collapse and the whole system to shut down.

Traditional solutions require a microcontroller running firmware. The LPC solves this in **pure combinational + sequential logic**: no software, no processor, no firmware update needed. It is intrinsically fast (responds on the next clock edge) and reliable because there are no software bugs to worry about.

The controller:
- Reads three hardware flags from a voltage comparator circuit (undervoltage, medium power, high power).
- Decides which of four loads to enable.
- Updates its decision every clock cycle.

---

## 3. System Architecture Overview

```
                      ┌────────────────────────────────┐
  undervoltage_flag ──►                                 ├──► load_enable[0]  (L1 — highest priority)
  medium_power_flag ──►   Load Priority Controller      ├──► load_enable[1]  (L2)
  high_power_flag   ──►       (FSM — 2-bit state)       ├──► load_enable[2]  (L3)
                    ──►                                 ├──► load_enable[3]  (L4 — lowest priority)
          clk       ──►                                 │
          rst       ──►                                 │
                      └────────────────────────────────┘
```

The design is split into the classic three-block FSM pattern:

| Block | Type | Responsibility |
|---|---|---|
| **State Register** | Sequential (flip-flop) | Holds current state, updates on clock edge |
| **Next-State Logic** | Combinational | Computes next state from flags |
| **Output Logic** | Combinational | Drives load_enable based on current state |

---

## 4. Signal Descriptions (Pin Map)

### Inputs

| Signal | Pin | Description |
|---|---|---|
| `clk` | `ui[0]` | Clock signal. All state transitions happen on the **rising edge**. |
| `reset` | `ui[1]` | Asynchronous reset. When HIGH, immediately forces the FSM to LOW_POWER_MODE regardless of clock. |
| `undervoltage_flag` | `ui[2]` | Asserted HIGH when available power is critically low (e.g., battery near empty or bus voltage collapsed). |
| `medium_power_flag` | `ui[3]` | Asserted HIGH when moderate power is available (enough for two loads). |
| `high_power_flag` | `ui[4]` | Asserted HIGH when full power is available (all loads can run). |
| `ui[5:7]` | — | Unused (tied to 0). |

### Outputs

| Signal | Pin | Description |
|---|---|---|
| `load_enable[0]` (L1) | `uo[0]` | Enable for Load 1 — the **highest priority** load. Always ON unless hard reset. |
| `load_enable[1]` (L2) | `uo[1]` | Enable for Load 2 — ON in medium and high power modes. |
| `load_enable[2]` (L3) | `uo[2]` | Enable for Load 3 — ON only in high power mode. |
| `load_enable[3]` (L4) | `uo[3]` | Enable for Load 4 — ON only in high power mode. |
| `uo[4:7]` | — | Unused (tied to 0). |

**Note:** The `uio` bidirectional bus is entirely unused in this design.

---

## 5. The Finite State Machine (FSM)

The LPC is built around a **3-state Mealy/Moore hybrid FSM** encoded in 2 bits.

### States

| State Name | Encoding | Meaning |
|---|---|---|
| `LOW_POWER_MODE` | `2'b00` | Power is critically low. Only the most essential load (L1) is kept on. |
| `MEDIUM_POWER_MODE` | `2'b01` | Moderate power available. L1 and L2 are enabled. |
| `HIGH_POWER_MODE` | `2'b10` | Full power available. All four loads are enabled. |

### Default / Reset State

On assertion of `rst` (asynchronous, active-HIGH), the FSM immediately jumps to `LOW_POWER_MODE`. This is a **safe default** — if the reset line is ever triggered mid-operation (e.g., during a power glitch), the system defaults to the most conservative behaviour, protecting the supply.

### State Transition Diagram

```
                    ┌──────────────────────────────────┐
                    │         RESET (async)            │
                    ▼                                   │
            ┌──────────────┐                           │
            │  LOW_POWER   │◄──────────────────────────┘
            │    MODE      │◄── undervoltage_flag=1
            │  (2'b00)     │◄── (no flags asserted)
            └──────┬───────┘
                   │ medium_power_flag=1
                   │ (undervoltage=0)
                   ▼
            ┌──────────────┐
            │    MEDIUM    │
            │    POWER     │
            │    MODE      │
            │  (2'b01)     │
            └──────┬───────┘
                   │ high_power_flag=1
                   │ (undervoltage=0, medium=0)
                   ▼
            ┌──────────────┐
            │     HIGH     │
            │     POWER    │
            │     MODE     │
            │  (2'b10)     │
            └──────────────┘
```

Transitions go in both directions: the FSM can escalate to a higher mode when more power becomes available, or de-escalate immediately when a flag changes (e.g., if `undervoltage_flag` fires while in HIGH_POWER_MODE, the next clock cycle drops straight to LOW_POWER_MODE).

---

## 6. Verilog Implementation Walkthrough

The main module is [src/LPC.v](src/LPC.v). Here is a block-by-block breakdown:

### Module Declaration

```verilog
module load_priority_controller(
    input wire clk,
    input wire rst,
    input wire undervoltage_flag,
    input wire medium_power_flag,
    input wire high_power_flag,
    output reg [3:0] load_enable
);
```

Five inputs, one 4-bit output register. The `output reg` declaration means `load_enable` is driven by an `always` block.

### State Encoding

```verilog
parameter LOW_POWER_MODE    = 2'b00;
parameter MEDIUM_POWER_MODE = 2'b01;
parameter HIGH_POWER_MODE   = 2'b10;
```

Using `parameter` keeps the state names human-readable and makes modifications easy.

### State Register (Sequential Block)

```verilog
always @(posedge clk or posedge rst) begin
    if (rst)
        current_state <= LOW_POWER_MODE;
    else
        current_state <= next_state;
end
```

This is a **D-type flip-flop with asynchronous reset**. It only changes `current_state` — it does not compute anything.

### Next-State Logic (Combinational Block)

```verilog
always @(*) begin
    if (undervoltage_flag)
        next_state = LOW_POWER_MODE;
    else if (medium_power_flag)
        next_state = MEDIUM_POWER_MODE;
    else if (high_power_flag)
        next_state = HIGH_POWER_MODE;
    else
        next_state = LOW_POWER_MODE;
end
```

The `always @(*)` means this block re-evaluates instantly whenever any input changes. The **priority order** in the `if-else if` chain is critical:

1. `undervoltage_flag` wins over everything — safety first.
2. `medium_power_flag` wins if undervoltage is not asserted.
3. `high_power_flag` wins only if neither of the above is asserted.
4. If nothing is asserted, default to LOW_POWER_MODE (conservative fallback).

This means you **cannot be in HIGH_POWER_MODE while undervoltage_flag is HIGH**, even if the hardware signals are contradictory. The FSM is fault-tolerant by design.

### Output Logic (Combinational Block)

```verilog
always @(*) begin
    case (current_state)
        LOW_POWER_MODE:    load_enable = 4'b0001;
        MEDIUM_POWER_MODE: load_enable = 4'b0011;
        HIGH_POWER_MODE:   load_enable = 4'b1111;
        default:           load_enable = 4'b0000;
    endcase
end
```

A `case` statement maps each state to its output pattern. The `default` arm (outputting `0000`) handles any illegal state encoding — an important safety measure in ASIC design where radiation or fabrication defects can corrupt state registers.

---

## 7. Power Modes at a Glance

| Mode | `load_enable[3:0]` | Loads ON | Loads OFF |
|---|---|---|---|
| LOW_POWER_MODE | `4'b0001` | L1 | L2, L3, L4 |
| MEDIUM_POWER_MODE | `4'b0011` | L1, L2 | L3, L4 |
| HIGH_POWER_MODE | `4'b1111` | L1, L2, L3, L4 | — |
| (illegal/reset) | `4'b0000` | — | All |

L1 is the highest-priority load and is always enabled in all valid operating states.

---

## 8. State Transition Table

| Current State | `undervoltage` | `medium` | `high` | Next State |
|---|---|---|---|---|
| Any | 1 | X | X | LOW_POWER_MODE |
| Any | 0 | 1 | X | MEDIUM_POWER_MODE |
| Any | 0 | 0 | 1 | HIGH_POWER_MODE |
| Any | 0 | 0 | 0 | LOW_POWER_MODE |

**X** = Don't care. The transition is entirely input-driven (no history dependency), which means the FSM is effectively a **combinational selector with registered output** — it converges to the correct state in a single clock cycle from any starting state.

---

## 9. Timing and Clocking

- **Clock:** External, driven via `ui[0]`. Internally treated as a standard synchronous clock.
- **Reset:** Asynchronous — takes effect immediately, not waiting for the next clock edge.
- **Target Clock Period:** 20 ns (50 MHz) as configured in [src/config.json](src/config.json).
- **Combinational depth:** Extremely shallow — just an `if-else if` chain and a `case`. The critical path is well within the 20 ns budget.
- **Metastability:** The input flags (`undervoltage_flag`, `medium_power_flag`, `high_power_flag`) are assumed to come from an external comparator circuit. In a real deployment, synchronizer flip-flops should be placed on these inputs if they can change asynchronously with respect to `clk`.

---

## 10. External Hardware Context

The LPC is designed to work alongside a **voltage comparator circuit** that generates the three power-status flags:

```
  Battery / Power Bus
         │
         ▼
  ┌─────────────────────┐
  │  Voltage Comparator │──► undervoltage_flag  (threshold: e.g., < 3.0V)
  │  (e.g., LM393 or   │──► medium_power_flag  (threshold: e.g., 3.0V–4.0V)
  │   discrete resistor │──► high_power_flag    (threshold: e.g., > 4.0V)
  │   divider network)  │
  └─────────────────────┘
```

The load_enable outputs can drive:
- **MOSFETs** or **relay drivers** to switch physical loads.
- **LEDs** for visual verification during testing.

In a practical deployment (e.g., a solar energy system):
- L1 could be a control board or communication module.
- L2 could be sensors or low-power peripherals.
- L3 and L4 could be high-power actuators or non-critical displays.

---

## 11. Tiny Tapeout Integration

[Tiny Tapeout](https://tinytapeout.com/) is an educational platform that aggregates many small chip designs onto a single silicon die and manufactures them in bulk using open-source EDA tools and the **Sky130A** PDK (Process Design Kit) from SkyWater Technology / Google.

### How It Works

1. Designers submit a project with a standardised interface (`tt_um_*` top-level wrapper).
2. All submissions are stitched into a single GDS file (GDSII — the chip layout format).
3. The chip is manufactured and returned to each designer.

### Wrapper Module: [src/project.v](src/project.v)

Tiny Tapeout requires a specific top-level wrapper with an 8-bit input bus (`ui_in`), 8-bit output bus (`uo_out`), and bidirectional bus (`uio_*`). The actual `load_priority_controller` module is instantiated inside this wrapper and wired to the appropriate pins:

```
ui_in[0]  → clk
ui_in[1]  → rst
ui_in[2]  → undervoltage_flag
ui_in[3]  → medium_power_flag
ui_in[4]  → high_power_flag

uo_out[3:0] ← load_enable[3:0]
uo_out[7:4] ← 4'b0000 (unused)
```

**Current status:** The `project.v` file in the repository still contains the Tiny Tapeout template (an adder example). The `load_priority_controller` instantiation needs to be wired in before ASIC submission.

---

## 12. Testing Infrastructure

### Testbench: [test/tb.v](test/tb.v)

A Verilog testbench that:
- Instantiates the `tt_um_example` DUT (Device Under Test).
- Dumps all signals to an FST waveform file for viewing in GTKWave or Surfer.
- Provides clock and reset stimulus via cocotb.

### Python Test Harness: [test/test.py](test/test.py)

Uses [cocotb](https://www.cocotb.org/) — a Python-based hardware verification framework:
- Drives the DUT via Python coroutines.
- Clock period: 10 µs (100 kHz) for simulation.
- Reset sequence: Hold reset for 10 clock cycles, then release.
- Assertions check output values after stimulus is applied.

### Running Tests

```bash
# RTL simulation (Icarus Verilog)
cd test && make -B

# Gate-level simulation (after GDS build)
make -B GATES=yes

# View waveforms
gtkwave tb.fst tb.gtkw
# or
surfer tb.fst
```

### Typical Test Scenario

| Step | Action | Expected `uo_out[3:0]` |
|---|---|---|
| 1 | Assert reset (`ui_in[1]=1`) | `0001` (LOW_POWER_MODE) |
| 2 | Release reset, set `undervoltage=1` | `0001` (LOW_POWER_MODE) |
| 3 | Set `medium_power=1`, clear `undervoltage` | `0011` (MEDIUM_POWER_MODE) |
| 4 | Set `high_power=1`, clear `medium` | `1111` (HIGH_POWER_MODE) |
| 5 | Re-assert `undervoltage=1` | `0001` (back to LOW_POWER_MODE) |

---

## 13. CI/CD Pipeline (GitHub Actions)

The project uses four automated workflows:

| Workflow | Trigger | What It Does |
|---|---|---|
| [test.yaml](.github/workflows/test.yaml) | Push | Runs cocotb simulation, uploads waveform artifacts |
| [gds.yaml](.github/workflows/gds.yaml) | Push | Full ASIC flow: synthesis → place & route → GDS generation → DRC/LVS precheck → GL test → layout viewer |
| [docs.yaml](.github/workflows/docs.yaml) | Push | Generates project documentation page |
| [fpga.yaml](.github/workflows/fpga.yaml) | Manual only | Synthesises bitstream for ICE40UP5K FPGA |

The GDS workflow is the most significant — it runs the complete open-source ASIC toolchain (OpenLane / LibreLane) and produces a manufacturable chip layout from the Verilog source.

---

## 14. Build Configuration

[src/config.json](src/config.json) configures the LibreLane/OpenLane ASIC build:

| Parameter | Value | Meaning |
|---|---|---|
| `CLOCK_PERIOD` | 20 ns | Target 50 MHz operation |
| `PL_TARGET_DENSITY_PCT` | 60 | 60% cell placement density within the tile |
| `CLOCK_PORT` | `clk` | The signal used for clock tree synthesis |
| `RUN_LINTER` | 1 | Enable Verilog linting during synthesis |
| PDK | Sky130A | Open-source 130nm CMOS process |
| Die margins | 1/1/6/6 | Asymmetric margins for Tiny Tapeout tile shape |

---

## 15. Known Gaps / Next Steps

1. **`project.v` wrapper not connected** — The `tt_um_example` module currently contains the template adder circuit. It needs to be updated to instantiate and wire `load_priority_controller` to the correct `ui_in`/`uo_out` pins.

2. **Test suite not LPC-specific** — `test/test.py` currently asserts `uo_out == ui_in + uio_in` (the template test). It needs to be rewritten to test all three power modes and the priority logic.

3. **No input synchronizers** — If `undervoltage_flag`, `medium_power_flag`, and `high_power_flag` come from asynchronous external comparators, double-flop synchronizers should be added at the input to prevent metastability on the fabricated chip.

4. **Only 3 of 4 state encodings used** — The 2-bit state register has a fourth possible state (`2'b11`). It is handled by the `default` arm (`load_enable = 4'b0000`), but an explicit transition back to `LOW_POWER_MODE` on the next clock cycle would make the FSM self-correcting rather than just safe-output.

---

*This document was written based on the complete project source at the time of analysis. For the latest state of the design, refer to the source files in [src/](src/) and [docs/info.md](docs/info.md).*
