"""Numerical tables shared by Golden references and future Cycle hardware."""

FIR_DECIMATOR_Q17 = (
    828,
    442,
    -2793,
    -5924,
    -1242,
    15283,
    35864,
    46156,
    35864,
    15283,
    -1242,
    -5924,
    -2793,
    442,
    828,
)

FIR_DECIMATOR_FLOAT = tuple(value / float(1 << 17) for value in FIR_DECIMATOR_Q17)

