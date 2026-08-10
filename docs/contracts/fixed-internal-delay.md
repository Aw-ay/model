# Fixed Internal Delay Contract

Status: frozen for ModelConfig schema/config `9/16`.

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

Golden verifies the equation and the absence of a hidden 31-sample shift.
Cycle must later declare its actual common latency and prove sample-index
equivalence. Board calibration must measure the end-to-end boundary above;
the placeholder `64.0` used by tests is not a measured board value.
