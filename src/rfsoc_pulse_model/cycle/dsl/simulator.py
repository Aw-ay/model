from __future__ import annotations

from .module import RTLModule


class CycleSimulator:
    """Execute compute, clock and one simultaneous register commit per step."""

    def __init__(self, module: RTLModule) -> None:
        self.module = module

    def step(self, inputs: dict[str, int]) -> dict[str, int]:
        self.module.set_inputs(inputs)
        self.module.compute()
        self.module.clock()
        self.module.commit()
        return self.module.outputs()

