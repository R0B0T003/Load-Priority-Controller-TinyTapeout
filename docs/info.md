## How it works

The Load Priority Controller is a 3-state Finite State Machine (FSM) implemented in pure digital logic. It manages power distribution across four prioritised loads based on external power-status signals — no firmware, no processor.

The system receives three flags from an external voltage comparator circuit connected to `ui_in[2:0]`:

- `ui_in[0]` — `undervoltage_flag`: power is critically low (highest priority signal)
- `ui_in[1]` — `medium_power_flag`: moderate power available
- `ui_in[2]` — `high_power_flag`: full power available

The dedicated `clk` pin drives the state register. The dedicated `rst_n` pin (active-LOW) performs an asynchronous reset to LOW_POWER_MODE.

Based on the flags, the FSM moves between three power modes:

| Mode | Condition | `uo_out[3:0]` | Loads ON |
|---|---|---|---|
| LOW_POWER_MODE | undervoltage=1 OR no flags | `0001` | L1 only |
| MEDIUM_POWER_MODE | medium_power=1, undervoltage=0 | `0011` | L1 + L2 |
| HIGH_POWER_MODE | high_power=1, others=0 | `1111` | All 4 loads |

`undervoltage_flag` has absolute priority — it overrides all other flags and forces the FSM to LOW_POWER_MODE within one clock cycle, regardless of current state.

## How to test

1. Hold `rst_n` LOW for at least 5 clock cycles, then release HIGH
2. Drive the clock continuously via the dedicated `clk` pin
3. Drive flags via `ui_in[2:0]` and verify `uo_out[3:0]` after 2 clock cycles:

| `ui_in[2:0]` | Condition | Expected `uo_out[3:0]` |
|---|---|---|
| `000` | No flags | `0001` |
| `001` | undervoltage only | `0001` |
| `010` | medium_power only | `0011` |
| `100` | high_power only | `1111` |
| `101` | undervoltage + high_power | `0001` (undervoltage wins) |
| `011` | undervoltage + medium | `0001` (undervoltage wins) |

4. Verify outputs change only on rising clock edges
5. Verify only one power mode is active at a time

## External hardware

**Voltage comparator circuit** — generates the three power-status flags:
- Connect power bus voltage through a resistive divider to an LM393/LM339 comparator
- Set three reference thresholds (e.g., 3.0V, 3.5V, 4.0V for a 5V system)
- Comparator outputs wire directly to `ui_in[0]`, `ui_in[1]`, `ui_in[2]`

**Load switching circuit** — switches physical loads using the enable outputs:
- `uo_out[0]` → gate driver → N-MOSFET → L1 (highest priority load)
- `uo_out[1]` → gate driver → N-MOSFET → L2
- `uo_out[2]` → gate driver → N-MOSFET → L3
- `uo_out[3]` → gate driver → N-MOSFET → L4 (lowest priority load)

**LED indicators** — connect LEDs with series resistors (330Ω) from each `uo_out[3:0]` pin to ground for visual verification during testing.
