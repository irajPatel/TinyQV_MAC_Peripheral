/*
 * Copyright (c) 2025 Iraj Patel
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

// INT16 Multiply-Accumulate Peripheral for TinyQV
// Module name: tqvp_iraj_MAC
// Implements: 16x16 multiply, optional accumulate into 48-bit accumulator
// Controls: signed/unsigned, shift amount, rounding, saturate, clear accumulator
module tqvp_iraj_MAC (
    input         clk,          // Clock - 64MHz
    input         rst_n,        // Reset_n - low to reset

    input  [7:0]  ui_in,        // Input PMOD (avoid ui_in[7] - UART RX)
    output [7:0]  uo_out,       // Output PMOD (avoid uo_out[0] - UART TX)

    input [5:0]   address,      // 6-bit address space (64 registers)
    input [31:0]  data_in,      // 32-bit data input
    input [1:0]   data_write_n, // Write control: 11=no write, 00=8b, 01=16b, 10=32b
    input [1:0]   data_read_n,  // Read control: 11=no read, 00=8b, 01=16b, 10=32b
    
    output [31:0] data_out,     // 32-bit data output
    output        data_ready,    // Data ready signal
    output        user_interrupt // Interrupt to CPU
);

    // --- MAC registers and state ---
    // Control register (0x20)
    // bit0: START (write 1 to start)
    // bit1: MODE (0=MUL,1=MAC)  -- when 0, product is computed and available; when 1, product accumulates
    // bit2: SIGNED (1 = signed two's-complement inputs)
    // bit3: SATURATE_EN
    // bit4: ROUND_EN
    // bit[10:5]: SHIFT (6-bit right shift amount applied to product before accumulation)
    // bit11: CLEAR_ACC (write 1 to clear accumulator)
    // register addresses and bitfields
    localparam ADDR_CTRL    = 6'h20;
    localparam ADDR_A       = 6'h24;
    localparam ADDR_B       = 6'h28;
    localparam ADDR_PRODUCT = 6'h2C;
    localparam ADDR_ACC_H   = 6'h30;
    localparam ADDR_ACC_M   = 6'h34;
    localparam ADDR_ACC_L   = 6'h38;

    // control bit positions
    localparam BIT_START     = 0;
    localparam BIT_MODE      = 1;
    localparam BIT_SIGNED    = 2;
    localparam BIT_SAT       = 3;
    localparam BIT_ROUND     = 4;
    localparam BIT_SHIFT_LSB = 5; // bits [10:5]
    localparam BIT_CLEAR_ACC = 11;
    localparam BIT_CLEAR_DONE= 12; // write 1 to clear DONE

    // status bit positions (readback overlay in mac_ctrl)
    localparam BIT_STATUS_BUSY = 16;
    localparam BIT_STATUS_DONE = 17;
    localparam BIT_STATUS_SAT  = 18;

    // Status mask for read-overlay (bits [18:16])
    localparam [31:0] STATUS_MASK = (32'h1 << BIT_STATUS_BUSY) | (32'h1 << BIT_STATUS_DONE) | (32'h1 << BIT_STATUS_SAT);

    reg [31:0] mac_ctrl;      // control (writeable)
    reg [31:0] mac_a;         // operand A (lower 16 bits used)
    reg [31:0] mac_b;         // operand B (lower 16 bits used)
    reg [31:0] mac_product;   // last product (32-bit)
    reg signed [47:0] mac_acc;       // 48-bit signed accumulator
    reg mac_busy;             // MAC busy
    reg mac_done;             // MAC done (sticky until cleared)
    reg mac_sat_flag;         // saturation flag
    reg mac_start;            // internal start latch (set by write, consumed by core)

    // temporaries (module scope) - combinational intermediates
    reg signed [31:0] comb_prod_s;
    reg [31:0] comb_prod_u;
    reg signed [31:0] comb_prod_sel;      // selected product (signed view)
    reg signed [31:0] comb_prod_shifted;  // after shift/round
    reg signed [47:0] comb_acc_next_s;
    reg [5:0] comb_shift_amt;
    reg [31:0] rnd;                    // rounding constant (module scope)
    reg        comb_sat_flag;
    reg [31:0] comb_mac_product;

    // saturation limits
    localparam signed [47:0] SAT_MAX = 48'sh7FFFFFFFFFFF;
    localparam signed [47:0] SAT_MIN = -48'sh800000000000;

    // Reset / register-write handling (sequential)
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mac_ctrl <= 32'd0;
            mac_a <= 32'd0;
            mac_b <= 32'd0;
            mac_product <= 32'd0;
            mac_acc <= 48'd0;
            mac_busy <= 1'b0;
            mac_done <= 1'b0;
            mac_sat_flag <= 1'b0;
            mac_start <= 1'b0;
        end else begin
            // default: no register write unless decoded
            if (address == ADDR_CTRL && data_write_n != 2'b11) begin
                // support partial writes (8/16/32) via data_write_n
                reg [31:0] mask;
                mask = 32'h0;
                if (data_write_n == 2'b10) mask = 32'hFFFFFFFF; // 32-bit
                else if (data_write_n == 2'b01) mask = 32'h0000FFFF; // 16-bit
                else if (data_write_n == 2'b00) mask = 32'h000000FF; // 8-bit

                mac_ctrl <= (mac_ctrl & ~mask) | (data_in & mask);

                // synthesis-unfriendly prints - simulation only
                // synthesis translate_off
                //$display("[MAC] mac_ctrl <= %h at time %t", data_in, $time);
                // synthesis translate_on

                // CLEAR_ACC: clear accumulator immediately
                // CLEAR_ACC: clear accumulator immediately.
                // Note: this implementation intentionally sets the DONE sticky bit when the
                // accumulator is cleared so that software can observe completion via the
                // interrupt/status mechanism. This is a deliberate W1 (write-1) semantic for
                // CLEAR_ACC in this design; tests may rely on the resulting interrupt.
                if (data_in[BIT_CLEAR_ACC]) begin
                    mac_acc <= 48'd0;
                    mac_sat_flag <= 1'b0;
                    mac_done <= 1'b1; // indicate completion of clear (deliberate)
                end
                // CLEAR_DONE: clear done sticky
                if (data_in[BIT_CLEAR_DONE]) begin
                    mac_done <= 1'b0;
                end
                // START: set start latch (clear DONE to allow new completion)
                if (data_in[BIT_START]) begin
                    if (!mac_busy) begin
                        mac_start <= 1'b1;
                        mac_busy <= 1'b1;
                        mac_done <= 1'b0;
                    end
                end
            end

            if (address == ADDR_A && data_write_n != 2'b11) begin
                reg [31:0] mask_a;
                mask_a = (data_write_n == 2'b10) ? 32'hFFFFFFFF : (data_write_n == 2'b01) ? 32'h0000FFFF : 32'h000000FF;
                mac_a <= (mac_a & ~mask_a) | (data_in & mask_a);
                // synthesis translate_off
                //$display("[DEBUG] operand_a set to %h at time %t", data_in, $time);
                // synthesis translate_on
            end
            if (address == ADDR_B && data_write_n != 2'b11) begin
                reg [31:0] mask_b;
                mask_b = (data_write_n == 2'b10) ? 32'hFFFFFFFF : (data_write_n == 2'b01) ? 32'h0000FFFF : 32'h000000FF;
                mac_b <= (mac_b & ~mask_b) | (data_in & mask_b);
                // synthesis translate_off
                //$display("[DEBUG] operand_b set to %h at time %t", data_in, $time);
                // synthesis translate_on
            end
        end
    end

    // Combinational compute block: compute product/shift/round/accumulate
    always @* begin
        // defaults
        comb_prod_s = 32'sd0;
        comb_prod_u = 32'd0;
        comb_prod_sel = 32'sd0;
        comb_prod_shifted = 32'sd0;
        comb_acc_next_s = 48'sd0;
        comb_shift_amt = 6'd0;
        comb_mac_product = 32'd0;
        comb_sat_flag = 1'b0;

        // compute raw products from current registers
        comb_prod_s = $signed({{16{mac_a[15]}}, mac_a[15:0]}) * $signed({{16{mac_b[15]}}, mac_b[15:0]});
        comb_prod_u = mac_a[15:0] * mac_b[15:0];

        // select signed/unsigned
        if (mac_ctrl[BIT_SIGNED]) begin
            comb_prod_sel = comb_prod_s;
            comb_mac_product = comb_prod_s[31:0];
        end else begin
            comb_prod_sel = $signed(comb_prod_u);
            comb_mac_product = comb_prod_u;
        end

        comb_shift_amt = mac_ctrl[10:5];

        if (comb_shift_amt != 6'd0) begin
            if (mac_ctrl[BIT_ROUND]) begin
                rnd = (1 << (comb_shift_amt - 1));
                if (comb_prod_sel >= 0)
                    comb_prod_shifted = ($signed(comb_prod_sel + $signed({{16{1'b0}}, rnd}))) >>> comb_shift_amt;
                else
                    comb_prod_shifted = ($signed(comb_prod_sel - $signed({{16{1'b0}}, rnd}))) >>> comb_shift_amt;
            end else begin
                comb_prod_shifted = comb_prod_sel >>> comb_shift_amt;
            end
        end else begin
            comb_prod_shifted = comb_prod_sel;
        end

        comb_acc_next_s = $signed(mac_acc) + $signed({{16{comb_prod_shifted[31]}}, comb_prod_shifted});

        // saturation handling
        if (mac_ctrl[BIT_SAT]) begin
            if ($signed(comb_acc_next_s) > SAT_MAX) begin
                comb_sat_flag = 1'b1;
            end else if ($signed(comb_acc_next_s) < SAT_MIN) begin
                comb_sat_flag = 1'b1;
            end else begin
                comb_sat_flag = 1'b0;
            end
        end else begin
            comb_sat_flag = 1'b0;
        end

    end

    // Sequential commit: update outputs when START is latched
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mac_product <= 32'd0;
            mac_acc <= 48'd0;
            mac_busy <= 1'b0;
            mac_done <= 1'b0;
            mac_sat_flag <= 1'b0;
            mac_start <= 1'b0;
        end else begin
            if (mac_start) begin
                // commit product
                mac_product <= comb_mac_product;

                // commit accumulator with saturation if required
                if (mac_ctrl[BIT_SAT]) begin
                    if ($signed(comb_acc_next_s) > SAT_MAX) begin
                        mac_acc <= SAT_MAX;
                        mac_sat_flag <= 1'b1;
                    end else if ($signed(comb_acc_next_s) < SAT_MIN) begin
                        mac_acc <= SAT_MIN;
                        mac_sat_flag <= 1'b1;
                    end else begin
                        mac_acc <= comb_acc_next_s;
                        mac_sat_flag <= 1'b0;
                    end
                end else begin
                    mac_acc <= comb_acc_next_s;
                    mac_sat_flag <= 1'b0;
                end

                // done sticky, busy cleared, clear start latch
                mac_done <= 1'b1;
                mac_busy <= 1'b0;
                mac_start <= 1'b0;

                // synthesis translate_off
                $display("[MAC] operation complete at time %t product=%h acc=%h", $time, comb_mac_product, mac_acc);
                // synthesis translate_on
            end
        end
    end

    // Status outputs -> map some status bits onto uo_out for visibility
    // Do not drive uo_out[0] here; wrapper uses uio_out[0] for user_interrupt/IRQ
    assign uo_out[0] = 1'b0;
    assign uo_out[1] = mac_done;       // MAC done pulse
    assign uo_out[2] = mac_sat_flag;   // MAC saturation
    assign uo_out[3] = 1'b0;
    assign uo_out[4] = 1'b0;
    assign uo_out[5] = 1'b0;
    assign uo_out[6] = 1'b0;
    assign uo_out[7] = 1'b0;

    // Register read interface
    // Provide a read-overlay for the control register so status bits appear when reading ADDR_CTRL.
    // This overlays the BUSY/DONE/SAT status bits into the readback value while still
    // preserving the writable mac_ctrl bits.
    wire [31:0] mac_ctrl_read = (mac_ctrl & ~STATUS_MASK) | ({29'd0, mac_busy, mac_done, mac_sat_flag} << BIT_STATUS_BUSY);

    assign data_out = (address == 6'h20) ? mac_ctrl_read :
                      (address == 6'h24) ? mac_a :
                      (address == 6'h28) ? mac_b :
                      (address == 6'h2C) ? mac_product :
                      (address == 6'h30) ? {16'h0, mac_acc[47:32]} :
                      (address == 6'h34) ? {16'h0, mac_acc[31:16]} :
                      (address == 6'h38) ? {16'h0, mac_acc[15:0]} :
                      32'h0;

    assign data_ready = 1'b1;

    // Interrupt: pulse when done or on saturation
    assign user_interrupt = mac_done || mac_sat_flag;

    // prevent unused warnings for read/write strobes
    wire _unused = &{data_read_n, data_write_n, ui_in};

endmodule
