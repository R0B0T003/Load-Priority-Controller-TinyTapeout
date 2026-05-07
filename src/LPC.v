/*
 * Load Priority Controller — Smart Edition
 * Authors: Abiola Enoch, Omotosho Enoch, Esabu Blessing
 * Platform: Tiny Tapeout (Sky130A 130 nm CMOS)
 * SPDX-License-Identifier: Apache-2.0
 *
 * Features merged from feature_update.v:
 *   1. 2-stage input synchronizer    — metastability protection on async comparator flags
 *   2. Stability detection           — anti-hunting filter, 20-cycle hold before escalation
 *   3. 6-state FSM with WAIT states  — staged/soft load activation (WAIT_L2, WAIT_L3)
 *   4. Delay timer                   — 50-cycle inrush-current guard per WAIT state
 *   5. Stepped de-escalation         — L3→L2→L1 on power drop, not instant full drop
 *
 * Reset: active-LOW (rst_n), asynchronous → lands in L1_STATE (L1 always safe)
 *
 * Pin map (TinyTapeout interface):
 *   ui_in[0] = undervoltage_flag   ui_in[1] = medium_power_flag   ui_in[2] = high_power_flag
 *   uo_out[0] = L1                 uo_out[1] = L2                 uo_out[2] = L3
 */

module tt_um_load_priority_controller (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n — active-LOW asynchronous reset
);

    //==========================================================================
    // Flag extraction
    //==========================================================================

    wire undervoltage_flag = ui_in[0];
    wire medium_power_flag = ui_in[1];
    wire high_power_flag   = ui_in[2];

    //==========================================================================
    // Internal 2-bit power level encoding
    //
    //   undervoltage OR no flags → 2'b01  (critical low — keep L1 only)
    //   medium_power             → 2'b10
    //   high_power               → 2'b11
    //
    // undervoltage_flag has absolute priority — it overrides all other flags.
    //==========================================================================

    wire [1:0] power_level;

    assign power_level = undervoltage_flag ? 2'b01 :
                         high_power_flag   ? 2'b11 :
                         medium_power_flag ? 2'b10 :
                                            2'b01;

    //==========================================================================
    // Section 1 — 2-stage input synchronizer
    //
    // Comparator outputs are asynchronous relative to clk. Sampling them directly
    // risks metastability in the FSM flip-flops. Two chained FFs give the signal
    // two clock cycles to resolve before power_sync reaches any logic.
    //==========================================================================

    reg [1:0] p_s1, p_s2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            p_s1 <= 2'b01;
            p_s2 <= 2'b01;
        end else begin
            p_s1 <= power_level;
            p_s2 <= p_s1;
        end
    end

    wire [1:0] power_sync = p_s2;

    //==========================================================================
    // Section 2 — Stability detection (anti-hunting filter)
    //
    // power_sync must hold the same value for STABLE_THRESHOLD consecutive cycles
    // before the FSM is permitted to escalate (add loads). This prevents rapid
    // ON/OFF toggling caused by rail noise or comparator chatter.
    //
    // De-escalation (shedding loads) is NOT gated by stability — it is immediate,
    // because protecting the supply on a power drop is time-critical.
    //
    // Counter saturates at 0xFF to avoid wrap-around glitches.
    //==========================================================================

    reg [1:0] prev_power;
    reg [7:0] stable_count;

    localparam STABLE_THRESHOLD = 8'd20;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            prev_power   <= 2'b01;
            stable_count <= 8'd0;
        end else begin
            if (power_sync == prev_power)
                stable_count <= (stable_count == 8'hFF) ? 8'hFF : stable_count + 8'd1;
            else begin
                stable_count <= 8'd0;
                prev_power   <= power_sync;
            end
        end
    end

    wire stable = (stable_count >= STABLE_THRESHOLD);

    //==========================================================================
    // Section 3 — FSM state definitions (6 states, 3-bit encoding)
    //
    //   IDLE     — all loads OFF  (transient; normally skipped after rst_n)
    //   L1_STATE — L1 ON only     (lowest safe operating point)
    //   WAIT_L2  — L1 ON, timer running before enabling L2
    //   L2_STATE — L1 + L2 ON
    //   WAIT_L3  — L1 + L2 ON, timer running before enabling L3
    //   L3_STATE — all loads ON
    //==========================================================================

    localparam IDLE     = 3'd0;
    localparam L1_STATE = 3'd1;
    localparam WAIT_L2  = 3'd2;
    localparam L2_STATE = 3'd3;
    localparam WAIT_L3  = 3'd4;
    localparam L3_STATE = 3'd5;

    reg [2:0] state, next_state;

    //==========================================================================
    // Section 4 — Delay timer (inrush-current guard)
    //
    // Counts only while in a WAIT state. When delay_count reaches DELAY_THRESHOLD
    // the next load is enabled and the counter resets (because the FSM leaves the
    // WAIT state and the counter reset arm fires on the next cycle).
    //
    // At 50 MHz: DELAY_THRESHOLD = 50 → 1 µs stagger per load pair.
    //==========================================================================

    reg [7:0] delay_count;

    localparam DELAY_THRESHOLD = 8'd50;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            delay_count <= 8'd0;
        else if ((state == WAIT_L2) || (state == WAIT_L3))
            delay_count <= delay_count + 8'd1;
        else
            delay_count <= 8'd0;
    end

    wire delay_done = (delay_count >= DELAY_THRESHOLD);

    //==========================================================================
    // Section 5 — State register
    //
    // Resets to L1_STATE (not IDLE) so that the highest-priority load is
    // immediately active after power-on or reset, matching the original design
    // intent that L1 is never shed unless power vanishes entirely.
    //==========================================================================

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state <= L1_STATE;
        else
            state <= next_state;
    end

    //==========================================================================
    // Section 6 — Next-state logic
    //
    // Escalation (adding loads) requires stable power and passes through WAIT.
    // De-escalation (shedding loads) is immediate and stepped:
    //     L3_STATE → L2_STATE → L1_STATE → IDLE
    //==========================================================================

    always @(*) begin
        next_state = state;

        case (state)

            IDLE: begin
                // Leave IDLE as soon as power is stable (should be near-instant
                // after reset since power_sync = 2'b01 = prev_power from reset).
                if (stable)
                    next_state = L1_STATE;
            end

            L1_STATE: begin
                if (power_sync == 2'b00)
                    next_state = IDLE;
                else if ((power_sync >= 2'b10) && stable)
                    next_state = WAIT_L2;
            end

            WAIT_L2: begin
                // Abort if power dropped while waiting
                if (power_sync < 2'b10)
                    next_state = L1_STATE;
                else if (delay_done)
                    next_state = L2_STATE;
            end

            L2_STATE: begin
                if (power_sync < 2'b10)
                    next_state = L1_STATE;
                else if ((power_sync == 2'b11) && stable)
                    next_state = WAIT_L3;
            end

            WAIT_L3: begin
                // Abort if power dropped while waiting
                if (power_sync < 2'b11)
                    next_state = L2_STATE;
                else if (delay_done)
                    next_state = L3_STATE;
            end

            L3_STATE: begin
                // Stepped de-escalation: drop to L2 first, not straight to L1
                if (power_sync < 2'b11)
                    next_state = L2_STATE;
            end

            default: next_state = IDLE;

        endcase
    end

    //==========================================================================
    // Section 7 — Output logic
    //
    // WAIT states hold the same outputs as the preceding load state — loads
    // already ON stay ON during the wait; the new load is only enabled when
    // the delay completes and the FSM advances to the next load state.
    //==========================================================================

    reg L1, L2, L3;

    always @(*) begin
        L1 = 1'b0;
        L2 = 1'b0;
        L3 = 1'b0;

        case (state)
            IDLE:     begin L1 = 1'b0; L2 = 1'b0; L3 = 1'b0; end
            L1_STATE: begin L1 = 1'b1; L2 = 1'b0; L3 = 1'b0; end
            WAIT_L2:  begin L1 = 1'b1; L2 = 1'b0; L3 = 1'b0; end
            L2_STATE: begin L1 = 1'b1; L2 = 1'b1; L3 = 1'b0; end
            WAIT_L3:  begin L1 = 1'b1; L2 = 1'b1; L3 = 1'b0; end
            L3_STATE: begin L1 = 1'b1; L2 = 1'b1; L3 = 1'b1; end
            default:  begin L1 = 1'b0; L2 = 1'b0; L3 = 1'b0; end
        endcase
    end

    //==========================================================================
    // Output pin assignments
    //==========================================================================

    assign uo_out[0] = L1;
    assign uo_out[1] = L2;
    assign uo_out[2] = L3;
    assign uo_out[7:3] = 5'b0;

    assign uio_out = 8'b0;
    assign uio_oe  = 8'b0;

    // Silence unused-input warnings required by OpenLane linter
    wire _unused = &{ena, uio_in, ui_in[7:3], 1'b0};

endmodule
