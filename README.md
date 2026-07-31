# RFSoC pulse three-layer model

This directory is the independent modeling project for the ZU27DR pulse
system. Development has one direction only:

```text
Golden mathematics -> Cycle hardware architecture -> generated Verilog
```

The current milestone implements `common/` and the complete clock-free
`golden/` layer. `cycle/` is an explicit package boundary for the next
milestone; `build/` does not become authoritative source code.

## Golden model

Golden consumes whole NumPy arrays and answers mathematical questions: whether
a pulse is detected, its refined ToA and FWHM width, its peak/mean power and
frequency, whether a range clipped, and which hit-only IQ samples belong to the
record. It contains no clock, register, RAM, FIFO, AXI, `valid`, or `ready`.

```python
import numpy as np

from rfsoc_pulse_model.golden import DetectorConfig, GoldenPulseDetector

iq = np.zeros(128, dtype=np.complex128)
iq[32:48] = 4000 * np.exp(2j * np.pi * 0.125 * np.arange(16))

golden = GoldenPulseDetector(
    DetectorConfig(
        noise_boot_samples=16,
        threshold_scale=6.0,
        moving_average=2,
        vote_window=3,
        vote_required=2,
    )
)
records = golden.detect(iq)
print(records[0].toa_samples, records[0].pw_samples)
print(records[0].frequency_turns_per_sample)
```

The receive reference also models the Dual RF-ADC word contract, ideal Q17
FIR, 2:1 decimation, gain paths and ADC clipping. The transmit reference uses
the same 32-bit phase increment law intended for the Cycle DDS while computing
the mathematical sine with NumPy.

## Establishing correspondence between the three layers

Correspondence is defined by a shared contract, not by giving identically
named functions unrelated implementations.

| Algorithm contract | Golden source | Future Cycle source | Generated RTL |
| --- | --- | --- | --- |
| RX I/Q lane order | `golden/receive.py::unpack_dual_iq_words` | `cycle/hardware/dual_iq_packer.py` | `rfdc_dual_iq_packer.v` |
| 15-tap 2:1 complex FIR | `golden/receive.py::GoldenReceivePipeline` | `cycle/hardware/fir_decimator.py` | `complex_fir_decimator2.v` |
| I/Q power | NumPy magnitude squared in `golden/detector.py` | `cycle/hardware/iq_power.py` | `iq_power.v` |
| Adaptive threshold | `GoldenPulseDetector` | `cycle/hardware/noise_threshold.py` | `noise_threshold.v` |
| Moving average and N/M vote | `GoldenPulseDetector` | `cycle/hardware/coarse_detector.py` | `coarse_detector.v` |
| Half-peak refinement | `GoldenPulseDetector` | initially `cycle/software/pulse_refiner.py` | none until a hardware Cycle module exists |
| Range association | `common/events.py` | `cycle/software/event_packetizer.py` or a later hardware associator | none until registered as hardware |
| Real LFM phase law | `golden/transmit.py` | `cycle/hardware/tx_lfm.py` | `tx_lfm_axis.v` |

All layers consume `config/default.json`, `common/types.py`, and
`common/tables.py`. Their equivalence gates differ intentionally:

1. **Golden -> Cycle:** compare normalized semantics. Detection count/order,
   refined ToA/PW, range choice, IQ-window boundaries and frequency meaning
   must match after applying declared quantization and pipeline-latency
   normalization.
2. **Cycle -> Verilog:** drive identical vectors and compare every declared
   observable signal on every clock, bit for bit. The Cycle model is the only
   structural source for emitted RTL.
3. **Manifest:** every future RTL artifact must name its Cycle source class,
   ports, latency, configuration hash and file hash. A software-only Cycle
   module cannot be emitted.

This means Golden may remain vectorized and ideal while Cycle introduces
fixed widths, registers, RAM/FIFO and handshakes. Any numerical change starts
in Golden; any architecture/latency change starts in Cycle; Verilog is always
regenerated and never hand-edited.

## Layout

```text
model/
  config/default.json
  src/rfsoc_pulse_model/
    common/{types.py,fixed.py,events.py,tables.py}
    golden/{detector.py,receive.py,transmit.py}
    cycle/{dsl,hardware,software}/
  tests/{golden,cycle,equivalence,verilog}/
  build/                         # generated locally, ignored
```

## Run

```powershell
cd D:\AWAY\RFSOC\model
py -m pip install -e .
py -m unittest discover -s tests\golden -v
```

The default `py` installation on a development machine must have a working
NumPy installation. Model tests do not validate Vivado Block Design, CDC,
timing closure, bitstream generation, or board operation.

