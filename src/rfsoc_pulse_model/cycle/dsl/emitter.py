from __future__ import annotations

from .module import RTLModule, Signal


def _range(signal: Signal) -> str:
    return "" if signal.width == 1 else f" [{signal.width - 1}:0]"


class VerilogEmitter:
    """One-to-one Verilog-2001 emitter for the restricted Cycle structure."""

    def emit(self, module: RTLModule) -> str:
        module.elaborate()
        lines = ["`timescale 1ns/1ps", "", f"module {module.module_name} ("]
        declarations = []
        for port in module.ports:
            if port.direction == "input":
                kind = "input wire"
            elif port.registered or port in module.comb_assignments:
                kind = "output reg"
            else:
                kind = "output wire"
            declarations.append(f"    {kind}{_range(port)} {port.name}")
        lines.append(",\n".join(declarations))
        lines.append(");")
        lines.append("")

        for signal in module.internal_signals:
            kind = "reg" if signal.registered or signal in module.comb_assignments else "wire"
            lines.append(f"{kind}{_range(signal)} {signal.name};")
        if module.internal_signals:
            lines.append("")

        lines.append("always @(*) begin")
        for target, expression in module.comb_assignments.items():
            lines.append(f"    {target.name} = {expression.verilog()};")
        lines.append("end")
        lines.append("")

        if module.reset_signal is None:
            raise ValueError("emitted modules require an explicit reset signal")
        clock = next((port for port in module.ports if port.name == "clk_i"), None)
        if clock is None:
            raise ValueError("emitted modules require clk_i")
        lines.append(f"always @(posedge {clock.name}) begin")
        lines.append(f"    if ({module.reset_signal.name}) begin")
        for target, (_, reset) in module.clock_assignments.items():
            lines.append(f"        {target.name} <= {target.width}'d{reset};")
        lines.append("    end else begin")
        for target, (expression, _) in module.clock_assignments.items():
            lines.append(f"        {target.name} <= {expression.verilog()};")
        lines.append("    end")
        lines.append("end")
        lines.append("")
        lines.append("endmodule")
        lines.append("")
        return "\n".join(lines)
