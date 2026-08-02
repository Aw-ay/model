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

from rfsoc_pulse_model import ModelConfig
from rfsoc_pulse_model.golden import GoldenPulseDetector

iq = np.zeros(128, dtype=np.complex128)
iq[32:48] = 4000 * np.exp(2j * np.pi * 0.125 * np.arange(16))

config = ModelConfig.load_default()
golden = GoldenPulseDetector(config.detector)
records = golden.detect(iq)
print(records[0].toa_samples, records[0].pw_samples)
print(records[0].sample_domain, records[0].sample_rate_hz)
print(records[0].toa_seconds, records[0].pw_seconds)
print(records[0].frequency_turns_per_sample)
```

The receive reference also models the Dual RF-ADC word contract, ideal Q17
FIR, 2:1 decimation, gain paths and ADC clipping. The transmit reference uses
the same 32-bit phase increment law intended for the Cycle DDS while computing
the mathematical sine with NumPy.

### PulseRecord sampling contract

Every `PulseRecord` explicitly carries `sample_domain` and `sample_rate_hz`.
Records emitted by `GoldenPulseDetector` use:

```text
sample_domain  = detector
sample_rate_hz = 250_000_000
sample period  = 4 ns
```

Therefore `toa_samples`, `pw_samples`, the IQ window and signed-Q31
`freq_word` all refer to the detector sample domain. RFDC source time is
recovered with:

```text
source_sample_index = 7 + 2 * detector_sample_index
```

`toa_seconds` and `pw_seconds` provide explicit unit conversion. Event
association rejects records from different sample domains or rates.

### ADC clipping and FWHM

`apply_range_gain()` returns `AdcSampleBatch`, containing IQ and a per-sample
clipping sideband. The FIR OR-reduces that sideband over every contributing
15-sample window and the detector propagates it into `PulseRecord.saturated`.
An explicit sideband is authoritative. For an unannotated raw array, only the
signed-16 rail codes `+32767` and `-32768` are conservatively treated as
saturated; `-32767` is not a rail.

FWHM is the contiguous region at or above `max(half_peak, threshold)` that
contains the main peak. Refinement walks left and right from the first global
maximum and stops at the first sample below the refinement threshold. It never
bridges a sub-half-peak valley to another lobe.

### Unified configuration and rates

`ModelConfig.load_default()` reads the installed package resource and validates
these equations before any pipeline is created:

```text
rfdc_complex_rate = adc_rate / RFDC_decimation
rfdc_complex_rate = rx_fabric_clock * RFDC_complex_samples_per_clock
detector_rate     = rfdc_complex_rate / PL_decimation
detector_period   = 1 / detector_rate
DAC_baseband_rate = dac_rate / RFDC_interpolation
DAC_baseband_rate = DAC_fabric_clock * TX_samples_per_clock
```

For the default configuration these resolve to 4 GSPS -> 500 MSPS complex ->
250 MSPS detector, and 4 GSPS / 8 = 500 MSPS real TX baseband carried as two
samples per 250 MHz clock. Inconsistent rates, FIR group delay, channel/range
count or TX data type are rejected.

The authoritative installed resource is
`rfsoc_pulse_model/config/default.json`. The root `config/default.json` is a
human-visible source-tree mirror and must remain byte-identical.

### Rounding rule

The whole model uses `ties_away_from_zero`: round to nearest, and move an exact
half step away from zero. `common/fixed.py` is the only rounding implementation
for scalar and NumPy operations. ADC gain quantization, IQ payload conversion,
power fields, frequency words, fixed formats and DAC LFM samples all use it.
Future Cycle and generated RTL must implement the same rule explicitly.

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

All layers consume `ModelConfig`, `common/types.py`, `common/fixed.py`, and
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
    config/default.json          # installed package data
    common/{config.py,types.py,fixed.py,events.py,tables.py}
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
