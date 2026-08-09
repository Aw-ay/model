# Polarimetric Reflection Source Golden Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the clock-free 8-ADC to H/V to causal delay/RCS/polarization/Doppler to 8-DAC Golden reference while retaining pulse detection as a non-controlling monitor branch.

**Architecture:** Add shared physical contracts and three configuration layers, then implement small NumPy Golden units for causal delay, RCS, target compilation, reflection, ADC reconstruction, calibration and DAC routing. `GoldenReflectionSource` composes those units; the existing 500-to-250 MSPS FIR/detector is invoked only after the reflection result is determined and cannot affect the main path.

**Tech Stack:** Python 3.12, NumPy 2.3.5, frozen dataclasses, `enum`, standard-library `unittest`, editable `src/` package layout.

## Global Constraints

- Authoritative source is `D:\AWAY\RFSOC\model`; do not duplicate implementations under legacy `src/rfsoc_pulse`.
- Golden operates on complete NumPy arrays and contains no clocks, registers, RAM, FIFO, AXI, `valid` or `ready`.
- Reflection path uses `SampleDomain.RFDC_COMPLEX_INPUT` at exactly `500_000_000` complex samples/s by default.
- Monitor path remains `SampleDomain.DETECTOR` at exactly `250_000_000` samples/s by default.
- Internal reflection and DAC mathematical outputs use `complex128`; they are not RFDC AXI word definitions.
- Existing `PulseRecord` IQ width, ADC-code unit, ADC-code-squared power, clipping, contiguous-main-peak FWHM and ties-away-from-zero behavior must remain unchanged.
- ADC default map is H high/mid/low/reference on ADC0/1/2/3 and V high/mid/low/reference on ADC4/5/6/7.
- DAC map is V high on DAC0, H high on DAC1, V mid on DAC2, H mid on DAC3, V low on DAC4, H low on DAC5, V calibration/cancellation on DAC6 and H calibration/cancellation on DAC7.
- Nominal gain ranges are `HIGH=+20 dB`, `MID=0 dB`, `LOW=-20 dB`; actual complex corrections come from calibration.
- `RangeId` remains a legacy PDW type. New code uses independent polarization, range and role fields.
- Negative programmable delay, delay beyond `1_048_576` samples, singular calibration and invalid absolute-RCS requests must fail explicitly.
- `FUSED` range selection exists only as a rejected enum value in this milestone.
- Root `config/default.json` and installed `src/rfsoc_pulse_model/config/default.json` remain byte-identical.
- Do not modify Cycle, generated RTL, Vivado Tcl or Block Design in this plan.

## Test Environment

The registered Anaconda Python currently has a broken NumPy DLL and the registered Python 3.14 lacks NumPy. Use the bundled verified interpreter for every command:

```powershell
$modelPython = 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'D:\AWAY\RFSOC\model\src'
```

Baseline before implementation:

```powershell
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: `Ran 34 tests` and `OK`.

## File Map

| File | Responsibility |
| --- | --- |
| `src/rfsoc_pulse_model/common/types.py` | Keep legacy pulse types; add only shared scalar enums used by old and new layers |
| `src/rfsoc_pulse_model/common/reflection_types.py` | H/V waveforms, eight-channel frames, target/scatterer/scenario/status and channel-map contracts |
| `src/rfsoc_pulse_model/common/calibration_types.py` | Per-channel complex response, RCS anchor and immutable calibration profile |
| `src/rfsoc_pulse_model/common/config.py` | Parse and validate static reflection capability and channel maps |
| `src/rfsoc_pulse_model/golden/delay.py` | Causal integer plus 63-tap windowed-sinc fractional delay |
| `src/rfsoc_pulse_model/golden/rcs.py` | Calibrated or explicitly relative RCS-to-voltage conversion |
| `src/rfsoc_pulse_model/golden/reflection.py` | Target compiler and 2x2 multi-target reflection kernel |
| `src/rfsoc_pulse_model/golden/adc_frontend.py` | Eight ADC corrections and H/V fixed or auto-hold selection |
| `src/rfsoc_pulse_model/golden/calibration.py` | TX matrix forward model and inverse predistortion |
| `src/rfsoc_pulse_model/golden/dac_router.py` | Actual eight-channel DAC mapping and auxiliary modes |
| `src/rfsoc_pulse_model/golden/system.py` | End-to-end composition and independent legacy monitor branch |
| `tests/golden/test_reflection_types.py` | Common contract and mapping tests |
| `tests/golden/test_delay.py` | Causality, integer delay and fractional-delay tests |
| `tests/golden/test_rcs.py` | RCS scaling and calibration-anchor tests |
| `tests/golden/test_reflection.py` | Polarization, Doppler, compiler and multi-target tests |
| `tests/golden/test_adc_frontend.py` | ADC calibration, clipping and selection-mode tests |
| `tests/golden/test_calibration.py` | Matrix conditioning and predistortion tests |
| `tests/golden/test_dac_router.py` | Eight-DAC routing and auxiliary-output tests |
| `tests/golden/test_reflection_system.py` | End-to-end result and monitor independence tests |

---

### Task 1: Add physical contracts, static configuration and channel maps

**Files:**
- Modify: `src/rfsoc_pulse_model/common/types.py`
- Create: `src/rfsoc_pulse_model/common/reflection_types.py`
- Create: `src/rfsoc_pulse_model/common/calibration_types.py`
- Modify: `src/rfsoc_pulse_model/common/config.py`
- Modify: `src/rfsoc_pulse_model/common/__init__.py`
- Modify: `src/rfsoc_pulse_model/__init__.py`
- Modify: `config/default.json`
- Modify: `src/rfsoc_pulse_model/config/default.json`
- Create: `tests/golden/test_reflection_types.py`
- Modify: `tests/golden/test_config.py`

**Interfaces:**
- Consumes: existing `SampleDomain`, `RangeId`, `ModelConfig`, `DetectorConfig`.
- Produces: `Polarization`, `GainRange`, `ChannelRole`, `RangeSelectionMode`, `AuxOutputMode`, `PhysicalChannelMapEntry`, `PolarimetricWaveform`, `EightChannelAdcFrame`, `EightChannelDacFrame`, `TargetRequest`, `CompiledScatterer`, `ReflectionScenario`, `DacAuxRequest`, `ReflectionStatus`, `ComplexChannelCalibration`, `RcsCalibrationAnchor`, `CalibrationProfile`, plus new `ModelConfig` fields.

- [ ] **Step 1: Write failing common-contract tests**

Create `tests/golden/test_reflection_types.py` with concrete shape, domain and mapping checks:

```python
import unittest
import numpy as np

from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    GainRange,
    Polarization,
    PolarimetricWaveform,
)
from rfsoc_pulse_model.common.types import SampleDomain


class ReflectionContractTest(unittest.TestCase):
    def test_polarimetric_waveform_uses_h_then_v(self) -> None:
        samples = np.array([[1 + 2j, 3 + 4j], [5 + 6j, 7 + 8j]])
        waveform = PolarimetricWaveform(
            samples=samples,
            sample_domain=SampleDomain.RFDC_COMPLEX_INPUT,
            sample_rate_hz=500_000_000,
        )
        np.testing.assert_array_equal(waveform.samples[0], samples[0])
        np.testing.assert_array_equal(waveform.samples[1], samples[1])

    def test_polarimetric_waveform_rejects_wrong_shape(self) -> None:
        with self.assertRaisesRegex(ValueError, "shape.*2"):
            PolarimetricWaveform(
                samples=np.zeros((8, 4), dtype=np.complex128),
                sample_domain=SampleDomain.RFDC_COMPLEX_INPUT,
                sample_rate_hz=500_000_000,
            )

    def test_default_physical_channel_maps_match_the_board_contract(self) -> None:
        config = ModelConfig.load_default()
        self.assertEqual(
            [(entry.index, entry.polarization, entry.gain_range) for entry in config.adc_channel_map],
            [
                (0, Polarization.H, GainRange.HIGH),
                (1, Polarization.H, GainRange.MID),
                (2, Polarization.H, GainRange.LOW),
                (3, Polarization.H, GainRange.REFERENCE),
                (4, Polarization.V, GainRange.HIGH),
                (5, Polarization.V, GainRange.MID),
                (6, Polarization.V, GainRange.LOW),
                (7, Polarization.V, GainRange.REFERENCE),
            ],
        )
        self.assertEqual(
            [(entry.index, entry.polarization, entry.gain_range) for entry in config.dac_channel_map],
            [
                (0, Polarization.V, GainRange.HIGH),
                (1, Polarization.H, GainRange.HIGH),
                (2, Polarization.V, GainRange.MID),
                (3, Polarization.H, GainRange.MID),
                (4, Polarization.V, GainRange.LOW),
                (5, Polarization.H, GainRange.LOW),
                (6, Polarization.V, GainRange.REFERENCE),
                (7, Polarization.H, GainRange.REFERENCE),
            ],
        )


if __name__ == "__main__":
    unittest.main()
```

Extend `tests/golden/test_config.py`:

```python
    def test_reflection_rate_and_capacity_are_static_contracts(self) -> None:
        config = ModelConfig.load_default()
        self.assertEqual(config.adc_channels, 8)
        self.assertEqual(config.dac_channels, 8)
        self.assertEqual(config.polarizations, 2)
        self.assertEqual(config.reflection_sample_rate_hz, 500_000_000)
        self.assertEqual(config.maximum_targets, 8)
        self.assertEqual(config.maximum_delay_samples, 1_048_576)
        self.assertEqual(config.fractional_delay_taps, 63)

    def test_duplicate_adc_index_is_rejected(self) -> None:
        payload = self.root_payload()
        payload["adc_channel_map"][1]["index"] = 0
        with self.assertRaisesRegex(ValueError, "adc_channel_map.*index"):
            ModelConfig.from_mapping(payload)

    def test_default_json_mirror_is_byte_identical(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        self.assertEqual(
            (project_root / "config/default.json").read_bytes(),
            (project_root / "src/rfsoc_pulse_model/config/default.json").read_bytes(),
        )
```

- [ ] **Step 2: Run the new tests and confirm missing imports/fields**

Run:

```powershell
& $modelPython -m unittest tests.golden.test_reflection_types tests.golden.test_config -v
```

Expected: FAIL because `reflection_types` and the new `ModelConfig` fields do not exist.

- [ ] **Step 3: Implement enums and immutable contracts**

Add the scalar enums to `common/types.py`:

```python
class Polarization(str, Enum):
    H = "H"
    V = "V"


class GainRange(str, Enum):
    HIGH = "high"
    MID = "mid"
    LOW = "low"
    REFERENCE = "reference"


class ChannelRole(str, Enum):
    ECHO = "echo"
    CALIBRATION = "calibration"
    CANCELLATION = "cancellation"


class RangeSelectionMode(str, Enum):
    FIXED = "fixed"
    AUTO_HOLD = "auto_hold"
    FUSED = "fused"


class AuxOutputMode(str, Enum):
    OFF = "off"
    CALIBRATION = "calibration"
    CANCELLATION = "cancellation"
```

Implement `common/reflection_types.py` with frozen dataclasses. Each NumPy field is converted with `np.asarray`; validate exact shapes, finite values, positive rates and nonnegative indices. Define `PhysicalChannelMapEntry` as:

```python
@dataclass(frozen=True)
class PhysicalChannelMapEntry:
    index: int
    polarization: Polarization
    gain_range: GainRange
    allowed_roles: tuple[ChannelRole, ...]
    nominal_gain_db: float
    digital_scale: float = 1.0
    enabled: bool = True
```

Define `TargetRequest.normalized_scattering_matrix` as `(2, 2) complex128`; define `CompiledScatterer` with integer delay, fractional delay, Doppler and complex matrix; define `ReflectionScenario` with:

```python
physical_range_m: float
carrier_frequency_hz: float
targets: tuple[TargetRequest, ...]
temperature_c: float
start_sample: int
length: int
require_absolute_rcs: bool = True
```

Define `DacAuxRequest(mode, waveform)` so `OFF` requires `waveform is None`, while calibration/cancellation requires one H/V waveform. Define `ReflectionStatus` with these exact fields:

```python
@dataclass(frozen=True)
class ReflectionStatus:
    adc_clipped: tuple[bool, bool]
    selected_ranges: tuple[GainRange, GainRange]
    absolute_rcs_calibrated: bool
    calibration_out_of_range: bool
    calibration_outputs_enabled: bool
    cancellation_outputs_enabled: bool
    monitor_pulse_count: int
```

Implement `common/calibration_types.py`:

```python
class CalibrationConditionError(ValueError):
    pass


@dataclass(frozen=True)
class ComplexChannelCalibration:
    response_gain: complex = 1.0 + 0.0j
    response_delay_samples: float = 0.0


@dataclass(frozen=True)
class RcsCalibrationAnchor:
    frequency_hz: float
    physical_range_m: float
    equivalent_rcs_m2: float
    digital_voltage_gain: float


@dataclass(frozen=True)
class CalibrationProfile:
    frequency_hz: float
    temperature_c: float
    frequency_tolerance_hz: float
    temperature_tolerance_c: float
    fixed_internal_delay_samples: float
    adc_channels: tuple[ComplexChannelCalibration, ...]
    dac_channels: tuple[ComplexChannelCalibration, ...]
    rx_polarization_matrix: np.ndarray
    tx_polarization_matrix: np.ndarray
    rcs_anchor: RcsCalibrationAnchor | None
    maximum_condition_number: float = 1.0e6
```

Reject zero/non-finite response gains, negative response delays, channel tuples not length 8, non-`(2,2)` matrices and nonpositive tolerances/condition limit. Compute the condition number of both polarization matrices and raise `CalibrationConditionError` when it is non-finite or exceeds `maximum_condition_number`.

Add this exact convenience constructor, returning eight identity channels and identity matrices:

```python
@classmethod
def identity(
    cls,
    frequency_hz: float,
    temperature_c: float,
    fixed_internal_delay_samples: float,
    rcs_anchor: RcsCalibrationAnchor | None,
) -> "CalibrationProfile":
    channels = tuple(ComplexChannelCalibration() for _ in range(8))
    return cls(
        frequency_hz=frequency_hz,
        temperature_c=temperature_c,
        frequency_tolerance_hz=1_000_000.0,
        temperature_tolerance_c=5.0,
        fixed_internal_delay_samples=fixed_internal_delay_samples,
        adc_channels=channels,
        dac_channels=channels,
        rx_polarization_matrix=np.eye(2, dtype=np.complex128),
        tx_polarization_matrix=np.eye(2, dtype=np.complex128),
        rcs_anchor=rcs_anchor,
        maximum_condition_number=1.0e6,
    )
```

The constructor uses `frequency_tolerance_hz=1_000_000.0`, `temperature_tolerance_c=5.0` and `maximum_condition_number=1.0e6`.

- [ ] **Step 4: Extend `ModelConfig` and both JSON files**

Parse the new fields and convert each map entry through `PhysicalChannelMapEntry.from_mapping()`. Add these values to both JSON files and increment `model_schema_version` to `4` and `config_version` to `7`:

```json
"adc_channels": 8,
"dac_channels": 8,
"polarizations": 2,
"reflection_sample_rate_hz": 500000000,
"maximum_targets": 8,
"maximum_delay_samples": 1048576,
"fractional_delay_taps": 63,
"processing_representation": "complex_baseband",
"dac_output_mode": "complex_baseband_reference",
"auto_range_high_water_fraction": 0.9,
"auto_range_low_water_fraction": 0.25,
"auto_range_hold_samples": 64
```

Encode ADC and DAC maps exactly as stated in Global Constraints. Echo channels allow `echo`; ADC references allow `calibration`; DAC6/7 allow both `calibration` and `cancellation`. Preserve legacy `channels=4`, `ranges_db` and `loopback_channel` for existing PDW tests.

Validate map indices are exactly `0..7`, entries are unique, each polarization has one HIGH/MID/LOW ADC, and reference DACs are DAC6 V and DAC7 H. Validate `reflection_sample_rate_hz == rfdc_complex_sample_rate_hz`, odd `fractional_delay_taps`, `0 < low_water < high_water < 1`, and positive hold count.

- [ ] **Step 5: Run contract tests and the full Golden baseline**

Run:

```powershell
& $modelPython -m unittest tests.golden.test_reflection_types tests.golden.test_config -v
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: all new tests pass; existing 34 tests remain green.

- [ ] **Step 6: Commit the common contract gate**

```powershell
git add src/rfsoc_pulse_model/common src/rfsoc_pulse_model/__init__.py config/default.json src/rfsoc_pulse_model/config/default.json tests/golden/test_reflection_types.py tests/golden/test_config.py
git commit -m "feat: add polarimetric reflection contracts"
```

---

### Task 2: Implement causal integer and fractional delay

**Files:**
- Create: `src/rfsoc_pulse_model/golden/delay.py`
- Create: `tests/golden/test_delay.py`

**Interfaces:**
- Consumes: `PolarimetricWaveform`, `ModelConfig.fractional_delay_taps`, `maximum_delay_samples`.
- Produces: `CausalityError`, `compile_target_delay -> tuple[int, float]`, `fractional_delay_kernel -> np.ndarray`, `apply_causal_delay -> np.ndarray`.

- [ ] **Step 1: Write failing delay tests**

```python
import unittest
import numpy as np

from rfsoc_pulse_model.golden.delay import (
    CausalityError,
    apply_causal_delay,
    compile_target_delay,
)


class GoldenDelayTest(unittest.TestCase):
    def test_integer_delay_is_zero_filled_without_wraparound(self) -> None:
        source = np.zeros((2, 96), dtype=np.complex128)
        source[0, 10] = 1.0
        delayed = apply_causal_delay(source, 40, 0.0, taps=63)
        self.assertAlmostEqual(delayed[0, 50], 1.0, places=12)
        self.assertEqual(delayed[0, 0], 0.0)
        self.assertEqual(delayed[0, -1], 0.0)

    def test_noncausal_apparent_range_is_rejected(self) -> None:
        with self.assertRaises(CausalityError):
            compile_target_delay(
                apparent_range_m=100.0,
                physical_range_m=100.0,
                fixed_internal_delay_samples=64.0,
                sample_rate_hz=500_000_000,
                maximum_delay_samples=1_048_576,
                taps=63,
            )

    def test_fractional_delay_has_expected_tone_phase(self) -> None:
        n = np.arange(512)
        tone = np.exp(2j * np.pi * 0.05 * n)
        source = np.vstack((tone, np.zeros_like(tone)))
        delayed = apply_causal_delay(source, 48, 0.25, taps=63)
        valid = slice(128, 400)
        expected = tone[valid] * np.exp(-2j * np.pi * 0.05 * 48.25)
        np.testing.assert_allclose(delayed[0, valid], expected, atol=2e-3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and confirm the module is absent**

```powershell
& $modelPython -m unittest tests.golden.test_delay -v
```

Expected: FAIL importing `rfsoc_pulse_model.golden.delay`.

- [ ] **Step 3: Implement the exact causal operator**

Use `SPEED_OF_LIGHT_MPS = 299_792_458.0`. `compile_target_delay` computes:

```python
programmable_samples = (
    2.0 * (apparent_range_m - physical_range_m)
    / SPEED_OF_LIGHT_MPS
    * sample_rate_hz
    - fixed_internal_delay_samples
)
```

Reject non-finite inputs, nonpositive ranges/rate, `programmable_samples < (taps - 1) // 2`, and delay above the configured maximum. Split with `integer = math.floor(programmable_samples)` and `fractional = programmable_samples - integer`.

Build a normalized Blackman-windowed sinc:

```python
center = (taps - 1) // 2
k = np.arange(taps, dtype=np.float64)
h = np.sinc(k - center - fractional_delay) * np.blackman(taps)
h /= np.sum(h)
```

For a declared delay `integer + fractional`, first prepend the coarse delay `integer - center`, then convolve each polarization with `h` in `full` mode and crop `[:N]`. This makes the external observable delay equal the declared value and never reads future samples. Reject `integer < center`; do not use `np.roll`.

- [ ] **Step 4: Run focused and full tests**

```powershell
& $modelPython -m unittest tests.golden.test_delay -v
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: delay tests and all previous tests pass.

- [ ] **Step 5: Commit the delay reference**

```powershell
git add src/rfsoc_pulse_model/golden/delay.py tests/golden/test_delay.py
git commit -m "feat: add causal golden target delay"
```

---

### Task 3: Implement calibrated RCS-to-voltage conversion

**Files:**
- Create: `src/rfsoc_pulse_model/golden/rcs.py`
- Create: `tests/golden/test_rcs.py`

**Interfaces:**
- Consumes: `RcsCalibrationAnchor`.
- Produces: `RcsCalibrationError`, `digital_gain_for_target -> tuple[float, bool]` where the boolean states whether absolute calibration was used.

- [ ] **Step 1: Write failing RCS tests**

```python
import unittest

from rfsoc_pulse_model.common.calibration_types import RcsCalibrationAnchor
from rfsoc_pulse_model.golden.rcs import RcsCalibrationError, digital_gain_for_target


class GoldenRcsTest(unittest.TestCase):
    def test_doubling_apparent_range_divides_voltage_gain_by_four(self) -> None:
        anchor = RcsCalibrationAnchor(
            frequency_hz=2.8e9,
            physical_range_m=100.0,
            equivalent_rcs_m2=1.0,
            digital_voltage_gain=0.5,
        )
        near, calibrated = digital_gain_for_target(1.0, 100.0, 1000.0, anchor, True)
        far, _ = digital_gain_for_target(1.0, 100.0, 2000.0, anchor, True)
        self.assertTrue(calibrated)
        self.assertAlmostEqual(far / near, 0.25)

    def test_absolute_mode_requires_an_anchor(self) -> None:
        with self.assertRaises(RcsCalibrationError):
            digital_gain_for_target(1.0, 100.0, 1000.0, None, True)

    def test_relative_mode_is_explicitly_uncalibrated(self) -> None:
        gain, calibrated = digital_gain_for_target(4.0, 100.0, 1000.0, None, False)
        self.assertAlmostEqual(gain, 0.02)
        self.assertFalse(calibrated)
```

- [ ] **Step 2: Run and confirm failure**

```powershell
& $modelPython -m unittest tests.golden.test_rcs -v
```

Expected: FAIL importing `golden.rcs`.

- [ ] **Step 3: Implement calibrated and relative formulas**

Compute:

```python
equivalent_rcs = target_rcs_m2 * (physical_range_m / apparent_range_m) ** 4
```

With an anchor:

```python
gain = anchor.digital_voltage_gain * np.sqrt(
    equivalent_rcs / anchor.equivalent_rcs_m2
)
return float(gain), True
```

Without an anchor and with `require_absolute=False`, return `sqrt(target_rcs_m2) * (physical_range_m / apparent_range_m) ** 2, False`. Reject nonpositive/non-finite RCS and ranges.

- [ ] **Step 4: Run focused and full tests**

```powershell
& $modelPython -m unittest tests.golden.test_rcs -v
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: all pass.

- [ ] **Step 5: Commit the RCS gate**

```powershell
git add src/rfsoc_pulse_model/golden/rcs.py tests/golden/test_rcs.py
git commit -m "feat: add calibrated golden RCS model"
```

---

### Task 4: Compile targets and implement the polarimetric reflection kernel

**Files:**
- Create: `src/rfsoc_pulse_model/golden/reflection.py`
- Create: `tests/golden/test_reflection.py`

**Interfaces:**
- Consumes: `ModelConfig`, `CalibrationProfile`, `ReflectionScenario`, `TargetRequest`, `CompiledScatterer`, `compile_target_delay`, `digital_gain_for_target`, `apply_causal_delay`.
- Produces: `TargetCompiler.compile(scenario) -> tuple[CompiledScatterer, ...]` and `GoldenPolarimetricReflectionKernel.process(incident, scatterers) -> PolarimetricWaveform`.

- [ ] **Step 1: Write failing compiler and kernel tests**

Include these exact cases in `tests/golden/test_reflection.py`:

```python
import unittest
import numpy as np

from rfsoc_pulse_model.common.calibration_types import CalibrationProfile
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    CompiledScatterer,
    PolarimetricWaveform,
    ReflectionScenario,
    TargetRequest,
)
from rfsoc_pulse_model.common.types import SampleDomain
from rfsoc_pulse_model.golden.reflection import (
    GoldenPolarimetricReflectionKernel,
    TargetCompiler,
)


class GoldenReflectionTest(unittest.TestCase):
    def test_h_input_produces_hh_and_vh_outputs(self) -> None:
        samples = np.zeros((2, 128), dtype=np.complex128)
        samples[0, 4] = 1.0
        incident = PolarimetricWaveform(
            samples, SampleDomain.RFDC_COMPLEX_INPUT, 500_000_000
        )
        scatterer = CompiledScatterer(
            integer_delay_samples=40,
            fractional_delay=0.0,
            doppler_hz=0.0,
            complex_scattering_matrix=np.array([[2, 0], [3j, 0]], dtype=np.complex128),
        )
        result = GoldenPolarimetricReflectionKernel(taps=63).process(
            incident, (scatterer,)
        )
        self.assertEqual(result.samples[0, 44], 2.0)
        self.assertEqual(result.samples[1, 44], 3.0j)

    def test_doppler_uses_absolute_sample_index(self) -> None:
        samples = np.ones((2, 256), dtype=np.complex128)
        samples[1] = 0.0
        incident = PolarimetricWaveform(
            samples, SampleDomain.RFDC_COMPLEX_INPUT, 500_000_000, start_sample=1000
        )
        scatterer = CompiledScatterer(
            40, 0.0, 5_000_000.0, np.eye(2, dtype=np.complex128)
        )
        output = GoldenPolarimetricReflectionKernel(63).process(incident, (scatterer,))
        phase_step = np.angle(output.samples[0, 101] * np.conj(output.samples[0, 100]))
        self.assertAlmostEqual(phase_step, 2 * np.pi * 5_000_000 / 500_000_000)

    def test_compiler_uses_receding_negative_doppler_convention(self) -> None:
        config = ModelConfig.load_default()
        calibration = CalibrationProfile.identity(
            frequency_hz=2.8e9,
            temperature_c=25.0,
            fixed_internal_delay_samples=64.0,
            rcs_anchor=None,
        )
        scenario = ReflectionScenario(
            physical_range_m=100.0,
            carrier_frequency_hz=2.8e9,
            targets=(TargetRequest(1000.0, 10.0, 1.0, np.eye(2)),),
            temperature_c=25.0,
            start_sample=0,
            length=256,
            require_absolute_rcs=False,
        )
        result = TargetCompiler(config, calibration).compile(scenario)
        self.assertAlmostEqual(
            result[0].doppler_hz,
            -2.0 * 10.0 * 2.8e9 / 299_792_458.0,
        )
```

Add this fourth test to the same class:

```python
    def test_multiple_targets_add_linearly(self) -> None:
        incident = PolarimetricWaveform(
            np.vstack((np.ones(192), np.full(192, 2.0))).astype(np.complex128),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        first = CompiledScatterer(40, 0.0, 0.0, np.eye(2, dtype=np.complex128))
        second = CompiledScatterer(
            48,
            0.0,
            0.0,
            np.array([[0.5, 0.25], [0.0, -1.0]], dtype=np.complex128),
        )
        kernel = GoldenPolarimetricReflectionKernel(taps=63)
        first_only = kernel.process(incident, (first,)).samples
        second_only = kernel.process(incident, (second,)).samples
        combined = kernel.process(incident, (first, second)).samples
        np.testing.assert_allclose(combined, first_only + second_only, atol=1e-12)
```

- [ ] **Step 2: Run and confirm missing kernel/compiler**

```powershell
& $modelPython -m unittest tests.golden.test_reflection -v
```

Expected: FAIL importing `golden.reflection`.

- [ ] **Step 3: Implement `TargetCompiler`**

Reject target counts over `config.maximum_targets`. For each target:

1. Call `compile_target_delay` with scenario physical range, calibration fixed delay and reflection rate.
2. Compute `doppler_hz = -2 * velocity * carrier / SPEED_OF_LIGHT_MPS`.
3. Map `HH/HV/VH/VV` to indices `(0,0)/(0,1)/(1,0)/(1,1)`.
4. Reject a zero reference element.
5. Call `digital_gain_for_target`.
6. Build:

```python
matrix = (
    target.normalized_scattering_matrix
    / abs(target.normalized_scattering_matrix[reference_index])
    * gain
    * np.exp(1j * target.initial_phase_rad)
)
```

Return immutable `CompiledScatterer` objects in input order. Store whether all targets used absolute calibration as compiler property `last_absolute_rcs_calibrated` for the system status.

- [ ] **Step 4: Implement the kernel**

Allocate `(2, N)` complex zeros. For every scatterer, call `apply_causal_delay`, multiply with `scatterer.complex_scattering_matrix @ delayed`, then multiply both rows by:

```python
n = incident.start_sample + np.arange(N, dtype=np.float64)
rotation = np.exp(2j * np.pi * scatterer.doppler_hz * n / incident.sample_rate_hz)
```

Accumulate in input order and return a new `PolarimetricWaveform` preserving domain, rate and start sample.

- [ ] **Step 5: Run focused and full tests**

```powershell
& $modelPython -m unittest tests.golden.test_reflection -v
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: all pass.

- [ ] **Step 6: Commit compiler and kernel**

```powershell
git add src/rfsoc_pulse_model/golden/reflection.py tests/golden/test_reflection.py
git commit -m "feat: add polarimetric golden reflection kernel"
```

---

### Task 5: Reconstruct H/V from eight calibrated ADC channels

**Files:**
- Create: `src/rfsoc_pulse_model/golden/adc_frontend.py`
- Create: `tests/golden/test_adc_frontend.py`

**Interfaces:**
- Consumes: `ModelConfig`, `CalibrationProfile.adc_channels`, `EightChannelAdcFrame`, `RangeSelectionMode`, `GainRange`, `Polarization`.
- Produces: `AdcFrontendResult(measured_incident, incident, selected_ranges, corrected_channels, corrected_clipped)` and `GoldenEightChannelAdcFrontend.reconstruct`.

- [ ] **Step 1: Write failing fixed-range and clipping tests**

```python
import dataclasses
import unittest
import numpy as np

from rfsoc_pulse_model.common.calibration_types import CalibrationProfile
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import EightChannelAdcFrame
from rfsoc_pulse_model.common.types import GainRange, Polarization, RangeSelectionMode, SampleDomain
from rfsoc_pulse_model.golden.adc_frontend import GoldenEightChannelAdcFrontend


class GoldenAdcFrontendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        self.calibration = CalibrationProfile.identity(
            frequency_hz=2.8e9,
            temperature_c=25.0,
            fixed_internal_delay_samples=64.0,
            rcs_anchor=None,
        )

    def test_fixed_ranges_select_h_and_v_independently(self) -> None:
        samples = np.vstack([np.full(32, index + 1.0) for index in range(8)]).astype(np.complex128)
        frame = EightChannelAdcFrame(
            samples, np.zeros((8, 32), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT, 500_000_000,
        )
        result = GoldenEightChannelAdcFrontend(self.config, self.calibration).reconstruct(
            frame,
            mode=RangeSelectionMode.FIXED,
            fixed_ranges={Polarization.H: GainRange.MID, Polarization.V: GainRange.LOW},
        )
        np.testing.assert_array_equal(result.incident.samples[0], samples[1])
        np.testing.assert_array_equal(result.incident.samples[1], samples[6])

    def test_rx_polarization_matrix_is_inverted_after_range_selection(self) -> None:
        true_hv = np.vstack((np.full(32, 2.0), np.full(32, 3.0))).astype(np.complex128)
        response = np.array([[1.0, 0.25], [0.1j, 0.8]], dtype=np.complex128)
        measured = response @ true_hv
        samples = np.zeros((8, 32), dtype=np.complex128)
        for index in (0, 1, 2):
            samples[index] = measured[0]
        for index in (4, 5, 6):
            samples[index] = measured[1]
        profile = dataclasses.replace(
            self.calibration,
            rx_polarization_matrix=response,
        )
        frame = EightChannelAdcFrame(
            samples,
            np.zeros((8, 32), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        result = GoldenEightChannelAdcFrontend(self.config, profile).reconstruct(
            frame,
            mode=RangeSelectionMode.FIXED,
            fixed_ranges={Polarization.H: GainRange.HIGH, Polarization.V: GainRange.HIGH},
        )
        np.testing.assert_allclose(result.incident.samples, true_hv, atol=1e-12)

    def test_clipped_high_range_falls_to_mid_and_holds(self) -> None:
        samples = np.zeros((8, 96), dtype=np.complex128)
        samples[0] = 1000.0
        samples[1] = 100.0
        samples[2] = 10.0
        samples[4] = 200.0
        clipped = np.zeros((8, 96), dtype=np.bool_)
        clipped[0, 10] = True
        frame = EightChannelAdcFrame(
            samples, clipped, SampleDomain.RFDC_COMPLEX_INPUT, 500_000_000
        )
        result = GoldenEightChannelAdcFrontend(self.config, self.calibration).reconstruct(
            frame, mode=RangeSelectionMode.AUTO_HOLD
        )
        self.assertEqual(result.selected_ranges[0, 10], GainRange.MID)
        self.assertTrue(all(value == GainRange.MID for value in result.selected_ranges[0, 10:74]))

    def test_fused_mode_is_rejected(self) -> None:
        frame = EightChannelAdcFrame(
            np.zeros((8, 8), dtype=np.complex128),
            np.zeros((8, 8), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        with self.assertRaisesRegex(ValueError, "FUSED"):
            GoldenEightChannelAdcFrontend(self.config, self.calibration).reconstruct(
                frame, mode=RangeSelectionMode.FUSED
            )
```

- [ ] **Step 2: Run and confirm missing frontend**

```powershell
& $modelPython -m unittest tests.golden.test_adc_frontend -v
```

Expected: FAIL importing `golden.adc_frontend`.

- [ ] **Step 3: Implement per-channel correction**

For each channel, divide by `response_gain`. To correct relative delay causally, compute the largest declared ADC response delay, then add `max_delay - channel_delay` to each channel. Use the same windowed-sinc helper with a shared causal support delay when the difference is fractional. OR the input clipping flags across every contributing FIR support window so `corrected_clipped` remains authoritative.

When all response delays are zero, bypass the fractional-delay filter so an identity calibration returns the input arrays exactly and does not add hidden latency.

- [ ] **Step 4: Implement fixed and auto-hold selection**

Build `(polarization, range) -> channel index` from `config.adc_channel_map`; never hard-code channel indices in selection logic.

For `FIXED`, require explicit H and V selections from HIGH/MID/LOW and copy the corrected sample plus clipping flag.

For `AUTO_HOLD`, initialize each polarization at HIGH. At each sample:

1. If the current path is clipped or either component exceeds `high_water_fraction * 32767`, step down HIGH→MID→LOW immediately.
2. Do not step up before `auto_range_hold_samples` have elapsed since the last switch.
3. After hold expires, step up one range only when the candidate higher path is not clipped and both components are below `low_water_fraction * 32767`.
4. H and V keep independent state.

Return `selected_ranges` as `(2,N)` object array of `GainRange`. Assemble the selected H/V rows as `measured_incident`, then apply `np.linalg.inv(calibration.rx_polarization_matrix)` to obtain the corrected `incident` waveform. Preserve frame domain/rate/start sample in both waveforms. This pair lets the system expose `C_TX * S * C_RX * x` diagnostics without contaminating the compensated main path.

- [ ] **Step 5: Run focused and full tests**

```powershell
& $modelPython -m unittest tests.golden.test_adc_frontend -v
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: all pass.

- [ ] **Step 6: Commit the ADC frontend**

```powershell
git add src/rfsoc_pulse_model/golden/adc_frontend.py tests/golden/test_adc_frontend.py
git commit -m "feat: add calibrated eight-channel ADC frontend"
```

---

### Task 6: Implement TX matrix forward model and predistortion

**Files:**
- Create: `src/rfsoc_pulse_model/golden/calibration.py`
- Create: `tests/golden/test_calibration.py`

**Interfaces:**
- Consumes: `CalibrationProfile.tx_polarization_matrix`, `maximum_condition_number`, `PolarimetricWaveform`.
- Produces: `GoldenTxPredistorter.forward`, `predistort`, `forward_predistorted`; `CalibrationConditionError` is the common contract created in Task 1.

- [ ] **Step 1: Write failing calibration tests**

```python
import unittest
import numpy as np

from rfsoc_pulse_model.common.calibration_types import (
    CalibrationConditionError,
    CalibrationProfile,
)
from rfsoc_pulse_model.common.reflection_types import PolarimetricWaveform
from rfsoc_pulse_model.common.types import SampleDomain
from rfsoc_pulse_model.golden.calibration import GoldenTxPredistorter


class GoldenCalibrationTest(unittest.TestCase):
    def test_predistortion_recovers_desired_hv_after_forward_matrix(self) -> None:
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        profile = CalibrationProfile(
            **{**profile.__dict__, "tx_polarization_matrix": np.array([[1.0, 0.1j], [0.2, 0.8]])}
        )
        desired = PolarimetricWaveform(
            np.array([[1 + 2j, 3 + 4j], [5 - 1j, 2 + 0j]]),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )
        model = GoldenTxPredistorter(profile)
        drive = model.predistort(desired)
        np.testing.assert_allclose(model.forward(drive).samples, desired.samples, atol=1e-12)

    def test_singular_tx_matrix_is_rejected(self) -> None:
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        singular = np.array([[1.0, 2.0], [2.0, 4.0]], dtype=np.complex128)
        with self.assertRaises(CalibrationConditionError):
            CalibrationProfile(**{**profile.__dict__, "tx_polarization_matrix": singular})
```

- [ ] **Step 2: Run and confirm missing calibration module**

```powershell
& $modelPython -m unittest tests.golden.test_calibration -v
```

Expected: FAIL importing `golden.calibration`.

- [ ] **Step 3: Implement forward and inverse matrix operations**

The common `CalibrationProfile` has already rejected ill-conditioned matrices. At construction store `np.linalg.inv(matrix)`. Both methods preserve waveform metadata:

```python
def forward(self, drive: PolarimetricWaveform) -> PolarimetricWaveform:
    return replace(drive, samples=self.matrix @ drive.samples)

def predistort(self, desired: PolarimetricWaveform) -> PolarimetricWaveform:
    return replace(desired, samples=self.inverse @ desired.samples)
```

`forward_predistorted(desired)` calls `forward(predistort(desired))` for diagnostics/tests; it does not replace the drive waveform returned to the router.

- [ ] **Step 4: Run focused and full tests**

```powershell
& $modelPython -m unittest tests.golden.test_calibration -v
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: all pass.

- [ ] **Step 5: Commit TX calibration**

```powershell
git add src/rfsoc_pulse_model/golden/calibration.py tests/golden/test_calibration.py
git commit -m "feat: add TX complex predistortion model"
```

---

### Task 7: Route H/V envelopes to the actual eight DAC channels

**Files:**
- Create: `src/rfsoc_pulse_model/golden/dac_router.py`
- Create: `tests/golden/test_dac_router.py`

**Interfaces:**
- Consumes: `ModelConfig.dac_channel_map`, `CalibrationProfile.dac_channels`, `PolarimetricWaveform`, `DacAuxRequest`.
- Produces: `GoldenEightChannelDacRouter.route(reflected, auxiliary) -> EightChannelDacFrame`.

- [ ] **Step 1: Write failing board-routing tests**

```python
import unittest
import numpy as np

from rfsoc_pulse_model.common.calibration_types import CalibrationProfile
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import DacAuxRequest, PolarimetricWaveform
from rfsoc_pulse_model.common.types import AuxOutputMode, SampleDomain
from rfsoc_pulse_model.golden.dac_router import GoldenEightChannelDacRouter


class GoldenDacRouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ModelConfig.load_default()
        self.profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        self.waveform = PolarimetricWaveform(
            np.array([[1 + 2j, 3 + 4j], [5 + 6j, 7 + 8j]]),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

    def test_echo_routes_v_to_even_and_h_to_odd_range_channels(self) -> None:
        frame = GoldenEightChannelDacRouter(self.config, self.profile).route(
            self.waveform, DacAuxRequest(AuxOutputMode.OFF, None)
        )
        for index in (0, 2, 4):
            np.testing.assert_array_equal(frame.samples[index], self.waveform.samples[1])
        for index in (1, 3, 5):
            np.testing.assert_array_equal(frame.samples[index], self.waveform.samples[0])
        np.testing.assert_array_equal(frame.samples[6:], 0.0)

    def test_calibration_mode_routes_v_to_dac6_and_h_to_dac7(self) -> None:
        auxiliary = DacAuxRequest(AuxOutputMode.CALIBRATION, self.waveform)
        frame = GoldenEightChannelDacRouter(self.config, self.profile).route(
            self.waveform, auxiliary
        )
        np.testing.assert_array_equal(frame.samples[6], self.waveform.samples[1])
        np.testing.assert_array_equal(frame.samples[7], self.waveform.samples[0])
```

- [ ] **Step 2: Run and confirm missing router**

```powershell
& $modelPython -m unittest tests.golden.test_dac_router -v
```

Expected: FAIL importing `golden.dac_router`.

- [ ] **Step 3: Implement configuration-driven routing and channel correction**

Allocate `(8,N)` complex zeros. For enabled ECHO entries, select H row 0 or V row 1, multiply by `entry.digital_scale / channel.response_gain`, and apply causal relative-delay alignment using the same maximum-response-delay rule as the ADC frontend. Identity calibration must bypass filtering and reproduce the input exactly.

For reference entries:

- `OFF`: leave DAC6/7 at zero;
- `CALIBRATION`: require `ChannelRole.CALIBRATION` in `allowed_roles` and route auxiliary V to DAC6, H to DAC7;
- `CANCELLATION`: require `ChannelRole.CANCELLATION` and use the same V/H order.

Reject waveform domain/rate/length mismatches. Return representation exactly `complex_baseband_reference`.

- [ ] **Step 4: Run focused and full tests**

```powershell
& $modelPython -m unittest tests.golden.test_dac_router -v
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: all pass.

- [ ] **Step 5: Commit the physical DAC router**

```powershell
git add src/rfsoc_pulse_model/golden/dac_router.py tests/golden/test_dac_router.py
git commit -m "feat: add configured eight-channel DAC router"
```

---

### Task 8: Compose the end-to-end Golden system and independent monitor branch

**Files:**
- Create: `src/rfsoc_pulse_model/golden/system.py`
- Create: `tests/golden/test_reflection_system.py`
- Modify: `src/rfsoc_pulse_model/golden/__init__.py`
- Modify: `src/rfsoc_pulse_model/__init__.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: every Golden unit from Tasks 2-7, existing `GoldenReceivePipeline`, `AdcSampleBatch`, `RangeId`.
- Produces: `ReflectionSourceResult` and `GoldenReflectionSource.run(adc_frame, scenario, auxiliary=None) -> ReflectionSourceResult`.

- [ ] **Step 1: Write failing end-to-end and monitor-independence tests**

```python
import dataclasses
import unittest
import numpy as np

from rfsoc_pulse_model.common.calibration_types import CalibrationProfile
from rfsoc_pulse_model.common.config import ModelConfig
from rfsoc_pulse_model.common.reflection_types import (
    EightChannelAdcFrame,
    ReflectionScenario,
    TargetRequest,
)
from rfsoc_pulse_model.common.types import SampleDomain
from rfsoc_pulse_model.common.types import RangeId, SampleDomain
from rfsoc_pulse_model.golden.system import GoldenReflectionSource


class GoldenReflectionSystemTest(unittest.TestCase):
    def make_input(self) -> EightChannelAdcFrame:
        samples = np.zeros((8, 512), dtype=np.complex128)
        samples[0:3, 80:160] = 1000.0
        samples[4:7, 80:160] = 500.0j
        return EightChannelAdcFrame(
            samples,
            np.zeros((8, 512), dtype=np.bool_),
            SampleDomain.RFDC_COMPLEX_INPUT,
            500_000_000,
        )

    def make_scenario(self) -> ReflectionScenario:
        return ReflectionScenario(
            physical_range_m=100.0,
            carrier_frequency_hz=2.8e9,
            targets=(TargetRequest(150.0, 0.0, 1.0, np.eye(2)),),
            temperature_c=25.0,
            start_sample=0,
            length=512,
            require_absolute_rcs=False,
        )

    def test_one_call_returns_hv_reflection_dac_frame_and_monitor_records(self) -> None:
        config = ModelConfig.load_default()
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        result = GoldenReflectionSource(config, profile).run(
            self.make_input(), self.make_scenario()
        )
        self.assertEqual(result.incident.samples.shape, (2, 512))
        self.assertEqual(result.desired_reflection.samples.shape, (2, 512))
        self.assertEqual(result.predistorted_reflection.samples.shape, (2, 512))
        self.assertEqual(result.dac_frame.samples.shape, (8, 512))
        self.assertEqual(len(result.compiled_targets), 1)

    def test_detector_threshold_cannot_move_or_change_dac_output(self) -> None:
        config = ModelConfig.load_default()
        quiet_detector = dataclasses.replace(config.detector, threshold_scale=1.0e12)
        quiet_config = dataclasses.replace(config, detector=quiet_detector)
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        normal = GoldenReflectionSource(config, profile).run(self.make_input(), self.make_scenario())
        quiet = GoldenReflectionSource(quiet_config, profile).run(self.make_input(), self.make_scenario())
        np.testing.assert_array_equal(normal.dac_frame.samples, quiet.dac_frame.samples)

    def test_monitor_uses_six_echo_channels_and_excludes_references(self) -> None:
        config = ModelConfig.load_default()
        fast_detector = dataclasses.replace(
            config.detector,
            noise_boot_samples=16,
            threshold_scale=2.0,
            moving_average=1,
            vote_window=1,
            vote_required=1,
        )
        config = dataclasses.replace(config, detector=fast_detector)
        profile = CalibrationProfile.identity(2.8e9, 25.0, 64.0, None)
        result = GoldenReflectionSource(config, profile).run(
            self.make_input(), self.make_scenario()
        )
        self.assertTrue(result.pulse_records)
        self.assertTrue({record.channel for record in result.pulse_records} <= {0, 1, 2, 4, 5, 6})
        self.assertFalse({3, 7} & {record.channel for record in result.pulse_records})
        self.assertTrue(
            {record.range_id for record in result.pulse_records}
            <= {RangeId.PLUS_20_DB, RangeId.ZERO_DB, RangeId.MINUS_20_DB}
        )
```

- [ ] **Step 2: Run and confirm missing system top**

```powershell
& $modelPython -m unittest tests.golden.test_reflection_system -v
```

Expected: FAIL importing `golden.system`.

- [ ] **Step 3: Implement `ReflectionSourceResult` and the main composition**

Define:

```python
@dataclass(frozen=True)
class ReflectionSourceResult:
    incident: PolarimetricWaveform
    desired_reflection: PolarimetricWaveform
    actual_uncompensated: PolarimetricWaveform
    predistorted_reflection: PolarimetricWaveform
    dac_frame: EightChannelDacFrame
    pulse_records: tuple[PulseRecord, ...]
    compiled_targets: tuple[CompiledScatterer, ...]
    status: ReflectionStatus
```

Constructor dependencies are created once from `config` and `calibration`. The constructor accepts `range_selection_mode`, defaulting to `FIXED`, and fixed H/V ranges, defaulting to HIGH for both polarizations. `run` validates frame/scenario length, rate, start sample, frequency/temperature tolerances and target count. Execute the main path in this exact order:

```python
frontend = self.adc_frontend.reconstruct(
    adc_frame,
    mode=self.range_selection_mode,
    fixed_ranges=self.fixed_ranges,
)
scatterers = self.target_compiler.compile(scenario)
desired = self.kernel.process(frontend.incident, scatterers)
uncompensated_reflection = self.kernel.process(
    frontend.measured_incident,
    scatterers,
)
actual_uncompensated = self.predistorter.forward(uncompensated_reflection)
predistorted = self.predistorter.predistort(desired)
auxiliary_request = (
    auxiliary
    if auxiliary is not None
    else DacAuxRequest(AuxOutputMode.OFF, None)
)
dac_frame = self.dac_router.route(predistorted, auxiliary_request)
```

- [ ] **Step 4: Add the monitor without data/control feedback**

After `dac_frame` has been computed, iterate configured ADC ECHO channels only. For each channel build `AdcSampleBatch(frame.samples[index], frame.clipped[index])`, map gain range to legacy `RangeId`, and call `GoldenReceivePipeline(config).detect(batch, channel=index, range_id=legacy_range)`.

Do not pass monitor records or detector thresholds to the compiler, kernel, predistorter or router. Sort records by `(toa_samples, channel)` only for deterministic reporting.

Build `ReflectionStatus` from frontend clipping/selected ranges, compiler absolute-RCS flag, frequency/temperature bounds, auxiliary mode and monitor record count.

- [ ] **Step 5: Export public APIs and update README**

Export the new common types and `GoldenReflectionSource` from package `__init__.py` files. Add one runnable README example that loads `ModelConfig`, builds identity calibration, creates an `(8,N)` frame and calls `GoldenReflectionSource.run`. State explicitly that the returned DAC frame is a complex-baseband mathematical reference and that Cycle/RTL/BD are not implemented by this milestone.

- [ ] **Step 6: Run focused, full and mirror checks**

```powershell
& $modelPython -m unittest tests.golden.test_reflection_system -v
& $modelPython -m unittest discover -s tests\golden -v
& $modelPython -c "from pathlib import Path; root=Path(r'D:\AWAY\RFSOC\model'); assert (root/'config/default.json').read_bytes() == (root/'src/rfsoc_pulse_model/config/default.json').read_bytes()"
```

Expected: all Golden tests pass and JSON assertion exits zero.

- [ ] **Step 7: Commit the Golden system top**

```powershell
git add src/rfsoc_pulse_model/golden/system.py src/rfsoc_pulse_model/golden/__init__.py src/rfsoc_pulse_model/__init__.py tests/golden/test_reflection_system.py README.md
git commit -m "feat: add end-to-end golden reflection source"
```

---

### Task 9: Run final Golden acceptance and record the layer boundary

**Files:**
- Modify: `README.md` only if verification reveals a documented count or command mismatch
- Create: `docs/verification/polarimetric-golden-acceptance.md`

**Interfaces:**
- Consumes: completed Golden public API and all tests.
- Produces: reproducible verification record; no new behavior.

- [ ] **Step 1: Run the complete Golden suite from a clean process**

```powershell
$modelPython = 'C:\Users\40836\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:PYTHONPATH = 'D:\AWAY\RFSOC\model\src'
& $modelPython -m unittest discover -s tests\golden -v
```

Expected: `Ran 61 tests` and `OK`. If the implementation adds a necessary boundary regression, update the expected count and the acceptance record to the larger observed value in the same commit.

- [ ] **Step 2: Run deterministic high-value acceptance tests separately**

```powershell
& $modelPython -m unittest \
  tests.golden.test_delay \
  tests.golden.test_rcs \
  tests.golden.test_reflection \
  tests.golden.test_adc_frontend \
  tests.golden.test_calibration \
  tests.golden.test_dac_router \
  tests.golden.test_reflection_system -v
```

Expected: all pass, including causality, `1/4` range voltage scaling, HH/VH matrix behavior, auto-hold, singular-matrix rejection, actual DAC map and monitor independence.

- [ ] **Step 3: Verify source/config hygiene**

```powershell
git diff --check
git status --short
& $modelPython -c "from rfsoc_pulse_model import ModelConfig; c=ModelConfig.load_default(); assert c.reflection_sample_rate_hz == 500_000_000"
```

Expected: no whitespace errors; status contains only the intended acceptance document before its commit; import assertion exits zero.

- [ ] **Step 4: Write the verification record**

Create `docs/verification/polarimetric-golden-acceptance.md` containing:

```markdown
# Polarimetric Golden Acceptance

- Interpreter: bundled Python 3.12
- NumPy: 2.3.5
- Golden test command: `python -m unittest discover -s tests\golden -v` with the bundled interpreter and `model\src` on `PYTHONPATH`
- Golden result: 61 tests passed
- Config mirrors: byte-identical
- Main reflection domain: RFDC_COMPLEX_INPUT at 500 MSPS
- Monitor domain: DETECTOR at 250 MSPS
- Explicitly not verified: Cycle timing, generated RTL, Vivado BD, CDC, timing closure, RFDC configuration and board RF performance
```

If Step 1 reports more than 61 tests because an additional boundary regression was required, write that exact larger count instead.

- [ ] **Step 5: Commit the acceptance evidence**

```powershell
git add docs/verification/polarimetric-golden-acceptance.md README.md
git commit -m "test: record polarimetric golden acceptance"
```
