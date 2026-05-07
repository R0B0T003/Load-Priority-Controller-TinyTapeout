/*
 * Copyright (c) 2024 Your Name
 * SPDX-License-Identifier: Apache-2.0
 */




module tt_um_load_priority_controller (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset


    // External power status 


    // Direct load outputs (no request layer)
    
  );
    wire undervoltage_flag;
    wire medium_power_flag;
    wire high_power_flag;
    reg [3:0] load_enable;
    
    assign undervoltage_flag = ui_in[0];
    assign medium_power_flag = ui_in[1];
    assign high_power_flag = ui_in[2];
    assign uo_out[0] = load_enable[0];
    assign uo_out[1] = load_enable[1];
    assign uo_out[2] = load_enable[2];
    assign uo_out[3] = load_enable[3];

    assign uio_out = 0;
    assign uio_oe  = 0;
    assign uo_out[7:4] = 0;

  // List all unused inputs to prevent warnings
    wire _unused = &{ena, uio_in, ui_in[7:3], 1'b0};
  //-------------------------------------------------
  // FSM States (power modes)
  //-------------------------------------------------
  localparam LOW_POWER_MODE    = 2'b00;
  localparam MEDIUM_POWER_MODE = 2'b01;
  localparam HIGH_POWER_MODE   = 2'b10;

  reg [1:0] current_state, next_state;

  //-------------------------------------------------
  // State register
  //-------------------------------------------------
    always @(posedge clk or negedge rst_n)
  begin
      if (!rst_n)
      current_state <= LOW_POWER_MODE;
    else
      current_state <= next_state;
  end

  //-------------------------------------------------
  // Next state logic
  //-------------------------------------------------
  always @(*)
  begin

    if (undervoltage_flag)
      next_state = LOW_POWER_MODE;

    else if (medium_power_flag)
      next_state = MEDIUM_POWER_MODE;

    else if (high_power_flag)
      next_state = HIGH_POWER_MODE;

    else
      next_state = LOW_POWER_MODE;

  end

  //-------------------------------------------------
  // Output logic (priority-based load enabling)
  //-------------------------------------------------
  always @(*)
  begin

    case (current_state)

      LOW_POWER_MODE:
      begin
        // Only highest priority load ON
        load_enable = 4'b0001;
      end

      MEDIUM_POWER_MODE:
      begin
        // L1 + L2 ON
        load_enable = 4'b0011;
      end

      HIGH_POWER_MODE:
      begin
        // All loads ON
        load_enable = 4'b1111;
      end

      default:
      begin
        load_enable = 4'b0000;
      end

    endcase

  end

endmodule
