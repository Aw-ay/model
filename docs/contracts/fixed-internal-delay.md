# Fixed Internal Delay Contract

Status: executable two-axis contract for ModelConfig schema/config `11/17`.

## Public quantity

`CalibrationProfile.fixed_internal_delay` is a `FixedInternalDelay` value with
the following immutable meaning:

```text
reference boundary : mathematical RFDC ADC complex input
                  -> mathematical DAC baseband output
sample domain      : RFDC_COMPLEX_INPUT
sample rate        : 500,000,000 samples/s
unit               : complex-input samples (fractional values allowed)
includes           : common deployed Cycle pipeline, RAM and filter latency
excludes           : target-programmed apparent-range delay
excludes           : Golden symmetric fractional-kernel center
```

The value must be measured again whenever the generated Cycle structure,
RFDC configuration, clocking or implementation latency changes. A profile
whose delay sample rate differs from `ModelConfig.reflection_sample_rate_hz`
fails before target compilation.

## Two sample-time references

Golden `EightChannelDacFrame.samples` is a latency-normalized algorithm
reference. Its `start_sample` and array offsets use
`SampleTimeReference.LATENCY_NORMALIZED`; the array is not shifted by the
measured common hardware latency.

The corresponding physical Cycle/DAC-equivalent coordinate, still expressed
in `RFDC_COMPLEX_INPUT` samples at 500 MSPS, is:

```text
physical_sample_index
  = normalized_sample_index + fixed_internal_delay.samples

normalized_sample_index
  = physical_sample_index - fixed_internal_delay.samples
```

`FixedInternalDelay.normalized_to_physical_sample()` and
`physical_to_normalized_sample()` implement these equations.
`EightChannelDacFrame.sample_index(offset, reference)` exposes both views while
keeping one waveform array. For example, with the test placeholder delay of
64 samples, Golden offset 60 is normalized sample 60 and physical sample 124.

Cycle-to-Golden equivalence must subtract the measured fixed delay from the
physical Cycle output index before comparing samples. This is not the raw
4-GSPS RF-DAC converter sample number. Distance/board acceptance uses the
500-MSPS-equivalent physical index and must not compare directly against the
Golden array offset.

## The 31-sample rule

The configured fractional-delay filter has 63 taps, hence an internal
symmetric-kernel center of `(63 - 1) / 2 = 31` samples.

That 31 is an implementation coordinate, not a public delay:

- `apply_causal_delay()` subtracts 31 before convolution, so its observable
  delay remains exactly the compiled integer plus fractional target delay;
- `apply_relative_delay()` crops away the same center, so ADC/DAC relative
  channel alignment does not move the public sample axis;
- Cycle may require real common buffering or pipeline latency to implement the
  same operation. That measured Cycle latency belongs in
  `FixedInternalDelay.samples` once, and must not be increased by another 31.

Consequently `31` must not be written into a calibration profile merely
because the Golden kernel has 63 taps. The numeric fixed delay remains absent
from the generated manifest until it is measured for the deployed build. The
manifest records only the 31-sample kernel-center convention and that the
fixed-delay value comes from the calibration profile.

## Target-delay equation

All terms below are expressed at the 500 MSPS RFDC complex-input rate:

```text
device_equivalent_delay_samples
  = 2 * (apparent_range_m - physical_range_m) / c * 500e6

programmable_target_delay_samples
  = device_equivalent_delay_samples - fixed_internal_delay.samples
```

The compiled programmable value must be at least 31 samples only because the
current causal Golden FIR needs that much support. The public result still has
the compiled delay, not compiled delay plus 31.

## Verification boundary

Golden verifies the equation, both time-axis mappings and the absence of a
hidden 31-sample shift. Cycle must later declare its actual common latency and
prove normalized sample-index equivalence. Board calibration must measure the
end-to-end boundary above; the placeholder `64.0` used by tests is not a
measured board value.
