module load_priority_controller(
    input wire clk,
    input wire rst,

    // External power status 
    input wire undervoltage_flag,
    input wire medium_power_flag,
    input wire high_power_flag,

    // Direct load outputs (no request layer)
    output reg [3:0] load_enable
  );

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
  always @(posedge clk or posedge rst)
  begin
    if (rst)
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
