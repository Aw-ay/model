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

The Golden system entry also models the continuous dual-polarization active
reflection path. It reconstructs H/V from eight ADC paths, applies causal
delay, calibrated RCS, explicit carrier range phase, a 2x2 scattering matrix
and Doppler, then routes the predistorted H/V envelopes to the configured eight
DAC paths. Pulse detection remains a monitor branch and cannot control the
reflection timing.

```python
import numpy as np

from rfsoc_pulse_model import (
    CalibrationProfile,
    EightChannelAdcFrame,
    GoldenReflectionSource,
    ModelConfig,
    ReflectionScenario,
    SampleDomain,
    TargetRequest,
)

config = ModelConfig.load_default()
calibration = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
samples = np.zeros((8, 512), dtype=np.complex128)
samples[0, 80:160] = 1000.0   # H high: +20 dB nominal voltage gain
samples[1, 80:160] = 100.0    # H mid:    0 dB
samples[2, 80:160] = 10.0     # H low:  -20 dB
samples[4, 80:160] = 5000.0j  # V high: +20 dB
samples[5, 80:160] = 500.0j   # V mid:    0 dB
samples[6, 80:160] = 50.0j    # V low:  -20 dB
adc_frame = EightChannelAdcFrame(
    samples=samples,
    clipped=np.zeros((8, 512), dtype=np.bool_),
    sample_domain=SampleDomain.RFDC_COMPLEX_INPUT,
    sample_rate_hz=500_000_000,
)
scenario = ReflectionScenario(
    physical_range_m=100.0,
    carrier_frequency_hz=2.8e9,
    targets=(TargetRequest(150.0, 0.0, 1.0, np.eye(2)),),
    temperature_c=25.0,
    start_sample=0,
    length=512,
    require_absolute_rcs=False,
)

result = GoldenReflectionSource(config, calibration).run(adc_frame, scenario)
print(result.dac_frame.samples.shape)
```

For a continuous acquisition split into software chunks, use
`GoldenReflectionStream.process_chunk()`. Chunks must have contiguous absolute
`start_sample` values; the final chunk sets `final=True`. The stream buffers the
Golden history and withholds any suffix that still depends on future samples,
so concatenating its returned arrays is equivalent to one `run()` over the
whole acquisition. This buffer-backed implementation defines the mathematical
oracle only; Cycle must replace it with bounded delay RAM, FIR state, detector
state and explicit 2SPC pipelines.

`result.dac_frame` is an eight-channel complex-baseband mathematical
reference. The RFDC DAC AXI boundary is separately frozen as two signed-16
real samples per 32-bit word; this does not imply that the mathematical complex
frame can be connected directly to the DAC. The first Cycle checkpoint now
implements only the 8-channel RFDC 2SPC ingress; the rest of the reflection,
detection and TX data paths, Vivado Block Design, CDC and board RF performance
remain unvalidated.

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

### PulseRecord physical contract

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

Every record also carries the complete numeric interpretation of its payload
and power statistics. The default contract is:

| Field | Default representation | Meaning |
| --- | --- | --- |
| `iq` | signed 16-bit, 0 fractional bits | raw I/Q ADC codes |
| `peak_power` | unsigned 32-bit, 0 fractional bits | maximum `I²+Q²`, in ADC-code² |
| `mean_power` | unsigned 32-bit, 0 fractional bits | rounded mean `I²+Q²`, in ADC-code² |

The corresponding record fields are `iq_width_bits`, `iq_fraction_bits`,
`iq_signed`, `iq_unit`, `power_width_bits`, `power_fraction_bits` and
`power_unit`. `power_definition` is fixed to `I^2+Q^2`. The stored value is
therefore not watts, dBm, dBFS or a calibrated receiver-input power. Converting
it to dBFS requires the declared code format; converting it to dBm additionally
requires a board-specific calibration for RF gain/loss, ADC full scale and
impedance. Event association rejects records with different physical formats.

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
rfdc_complex_rate = rx_fabric_clock * rfdc_complex_samples_per_cycle
detector_rate     = rfdc_complex_rate / PL_decimation
detector_period   = 1 / detector_rate
DAC_baseband_rate = dac_rate / RFDC_interpolation
DAC_baseband_rate = DAC_fabric_clock * TX_samples_per_clock
```

For the default configuration these resolve to 4 GSPS -> 500 MSPS complex ->
250 MSPS detector, and 4 GSPS / 8 = 500 MSPS real TX baseband carried as two
samples per 250 MHz clock. Inconsistent rates, FIR group delay, channel/range
count, IQ/power format or TX data type are rejected. `ModelConfig` is the
single source for these fields and passes them into `DetectorConfig`, which in
turn stamps every emitted `PulseRecord`.

The RFDC parallelism field is deliberately named
`rfdc_complex_samples_per_cycle=2`: it counts complete complex samples, not
AXI words or separate I/Q words. The removed
`rfdc_iq_stream_words_per_cycle` spelling is rejected to prevent a different
Cycle interface interpretation.

`ModelConfig` validates in `__post_init__`, so direct construction,
`from_mapping()` and `dataclasses.replace()` cannot create different validity
rules. The current package schema/config version is `9/16`.

The XCZU27DR v2.1 RFDC tile/slice, package-bank, board-net and carrier-endpoint
mapping is frozen in `ModelConfig` and documented in
`docs/contracts/zu27dr-v2.1-physical-channel-map.md`. External H/V and
+20/0/-20 dB wiring still requires the documented board continuity and
low-power tone acceptance before normal RF operation.

The RFDC AXI word contract is frozen in `ModelConfig.rfdc_axis` and documented
in `docs/contracts/rfdc-axis-word-format.md`. Each physical dual ADC uses an
even I stream and its adjacent odd Q stream, each 32-bit at 250 MHz with two
signed-16 component samples. The paired detector ingress word is exactly
`{Q1,I1,Q0,I0}`. Every DAC uses a 32-bit real stream `{sample1,sample0}`.
Vivado readback shows the existing BD is still a partial 125 MHz/64-bit ADC
configuration, so it is deliberately rejected as the target integration.

`AUTO_HOLD` uses the absolute RFDC input-sample timeline. H and V each retain
their current range and last absolute switch sample across contiguous frames;
a gap is rejected until `reset_auto_hold()` explicitly begins a new
acquisition. Range decisions use delay-aligned raw ADC codes and the matching
aligned clipping sideband, while the selected output uses the calibrated value
at that same aligned sample. Thus channel delay calibration cannot make the
range decision and returned sample refer to different physical instants.

Absolute RCS is fail-closed. An `RcsCalibrationAnchor` must carry a nonempty
calibration ID, an explicit validity flag, frequency/temperature/physical-range
conditions and their tolerances. Absolute mode rejects a missing, invalid,
out-of-anchor-condition or out-of-profile-condition calibration before target
gain is emitted. Only explicitly non-absolute mode may fall back to relative
gain, and then `absolute_rcs_calibrated` remains false.

The streaming API emits closed, stable PDWs and associated events online; it
does not wait unconditionally for `final=True`. It withholds a record that is
closed only by the current array boundary and emits records/events as a stable
global `(ToA, channel)` prefix, so concatenating per-call outputs exactly
matches one-shot ordering without duplicates. Stream status distinguishes the
exclusive end of accepted input (`processed_stop_sample`) from the exclusive
end of stable waveform output (`emitted_stop_sample`). `monitor_pulse_count`
is new PDWs in this call, `monitor_pulse_count_total` is cumulative, and
`stream_final` states whether future input is forbidden.

The authoritative installed resource is
`rfsoc_pulse_model/config/default.json`. The root `config/default.json` is a
human-visible source-tree mirror and must remain byte-identical.

### Reflection gain, delay, and phase contracts

For each ADC path, `nominal_gain_db` is the ideal physical voltage gain and
`ComplexChannelCalibration.response_gain` is only the measured residual
complex response. Reconstruction uses:

```text
incident = adc_code / (10^(nominal_gain_db/20) * response_gain)
```

ADC and DAC channel alignment removes only relative path delay. The symmetric
63-tap Golden interpolation kernel has an internal center of 31 samples, but
that center is removed from the public time axis in both the causal target
delay and the Golden-only relative alignment helpers. It is never added to
`fixed_internal_delay`.

`FixedInternalDelay` is measured from the mathematical RFDC ADC complex input
to the mathematical DAC baseband output. Its `samples` value is expressed in
`RFDC_COMPLEX_INPUT` at 500 MSPS. It includes common Cycle pipeline, RAM and
filter latency measured for the deployed build, and excludes target-programmed
delay. A calibration profile whose delay rate differs from
`reflection_sample_rate_hz` is rejected before target compilation. See
[`docs/contracts/fixed-internal-delay.md`](docs/contracts/fixed-internal-delay.md).

Because delaying a complex envelope between coherent DDC and DUC stages does
not by itself reproduce RF carrier propagation phase, each compiled target
also carries:

```text
range_carrier_phase = wrap(-2*pi*fc*2*(apparent_range-physical_range)/c)
```

The reflection kernel applies this phase independently of Doppler and target
`initial_phase_rad`. Future Cycle logic must quantize the explicit phase field;
it must not rely on an implicit RFDC NCO phase assumption.

The DAC policy is explicitly `external_analog_path`: HIGH/MID/LOW ports receive
the same digital complex envelope, while their external analogue paths apply
the configured `+20/0/-20 dB` nominal voltage gains. `digital_scale` remains an
explicit digital multiplier and `response_gain` is residual complex
calibration. The router therefore does not divide by DAC `nominal_gain_db`.

Every monitor `PulseRecord` carries `ChannelIdentity` with polarization, gain
range, role and physical channel. Polarimetric association groups three ranges
only within H or within V; the legacy four-channel association API remains
available for the original interface.

### Rounding rule

The whole model uses `ties_away_from_zero`: round to nearest, and move an exact
half step away from zero. `common/fixed.py` is the only rounding implementation
for scalar and NumPy operations. ADC gain quantization, IQ payload conversion,
power fields, frequency words, fixed formats and DAC LFM samples all use it.
Future Cycle and generated RTL must implement the same rule explicitly.

### Fixed-point width authority

`ModelConfig.numeric_formats` is the required width authority for every Cycle
data-path boundary and intermediate. It covers RFDC ADC input, the 2:1 FIR,
power/noise/threshold/vote, PDW fields, the 500 MSPS dual-polarization
reflection path, fractional delay, calibration and target matrices,
multi-target accumulation, phase/NCO, TX scaling and DAC output.

Lossless intermediate nodes use overflow policy `error`; Cycle simulation must
raise rather than hide an undersized value. Only named external/requantization
boundaries may `saturate`, and phase/event rollover is explicitly `wrap`.
Every discarded fractional bit uses project-wide `ties_away_from_zero`.
The complete table and width derivations are frozen in
[`docs/contracts/fixed-point-widths.md`](docs/contracts/fixed-point-widths.md).

## Establishing correspondence between the three layers

Correspondence is defined by a shared contract, not by giving identically
named functions unrelated implementations.

| Algorithm contract | Golden source | Cycle source | Generated RTL |
| --- | --- | --- | --- |
| 8-channel RFDC 2SPC ingress | `common/rfdc_axis.py` | `cycle/hardware/rx_group_ingress.py` | `rx_group_ingress_2spc.v` |
| 15-tap 2:1 complex FIR | `golden/receive.py::GoldenReceivePipeline` | `cycle/hardware/fir_decimator.py` | `complex_fir_decimator2.v` |
| I/Q power | NumPy magnitude squared in `golden/detector.py` | `cycle/hardware/iq_power.py` | `iq_power.v` |
| Adaptive threshold | `GoldenPulseDetector` | `cycle/hardware/noise_threshold.py` | `noise_threshold.v` |
| Moving average and N/M vote | `GoldenPulseDetector` | `cycle/hardware/coarse_detector.py` | `coarse_detector.v` |
| Half-peak refinement | `GoldenPulseDetector` | initially `cycle/software/pulse_refiner.py` | none until a hardware Cycle module exists |
| Range association | `common/events.py` | `cycle/software/event_packetizer.py` or a later hardware associator | none until registered as hardware |
| Real LFM phase law | `golden/transmit.py` | `cycle/hardware/tx_lfm.py` | `tx_lfm_axis.v` |

All layers consume `ModelConfig`, `common/types.py`, `common/fixed.py`, and
`common/tables.py`. `cycle/registry.py` is the hardware emission allow-list;
unregistered `.v` files make generation fail rather than being preserved.
Their equivalence gates differ intentionally:

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

The implemented ingress consumes eight flattened 32-bit I words and eight
32-bit Q words per 250 MHz clock, publishes lane0/lane1 for all eight channels
after one cycle, and increments an absolute 500 MSPS sample base by two. It has
no ready/backpressure input. Startup patterns are ignored until
`acquisition_enable_i`; after arming, an all-idle beat sets sticky
`gap_error_o` and a partially valid 16-stream group sets sticky
`format_error_o`. Either fault invalidates cross-channel time alignment and
fails closed until reset.

The single `clk_i` is only an integration candidate: the default configuration
records `common_pl_clock_mts` with proof status `unverified`, so generated
metadata reports that Block Design integration is not ready until Vivado proves
the common clock/reset/MTS topology. See
[`docs/contracts/cycle-2spc-ingress.md`](docs/contracts/cycle-2spc-ingress.md).

## Layout

```text
model/
  config/default.json
  src/rfsoc_pulse_model/
    config/default.json          # installed package data
    common/{config.py,types.py,fixed.py,numeric_formats.py,events.py,tables.py}
    golden/{detector.py,receive.py,transmit.py}
    cycle/{dsl,hardware,software}/
  tests/{golden,cycle,equivalence,verilog}/
  build/                         # generated locally, ignored
```

Generate the registered Cycle hardware with:

```text
python -m rfsoc_pulse_model.generate --output build/cycle_2spc
```

This writes Cycle-derived RTL, numeric metadata and `manifest.json`; the build
directory is disposable and must be regenerated rather than hand-edited.

## Run

```powershell
cd D:\AWAY\RFSOC\model
py -m pip install -e .
py -m unittest discover -s tests\golden -v
```

The default `py` installation on a development machine must have a working
NumPy installation. Model tests do not validate Vivado Block Design, CDC,
timing closure, bitstream generation, or board operation.
