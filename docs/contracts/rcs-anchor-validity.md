# RCS Anchor Validity and Fail-Closed Contract

Status: frozen for ModelConfig schema/config `8/13`.

An RCS anchor is measurement evidence, not merely four positive numbers. Each
`RcsCalibrationAnchor` must declare:

```text
calibration_id
valid
frequency_hz + frequency_tolerance_hz
temperature_c + temperature_tolerance_c
physical_range_m + physical_range_tolerance_m
equivalent_rcs_m2
digital_voltage_gain
```

The target compiler evaluates both the anchor conditions and the enclosing
`CalibrationProfile` frequency/temperature conditions against the requested
scenario before calculating any target gain.

## Absolute mode

`ReflectionScenario.require_absolute_rcs=True` fails before producing a
scatterer when any of the following is true:

- no anchor is installed;
- the anchor is explicitly marked invalid;
- frequency, temperature or physical range lies outside anchor tolerance;
- frequency or temperature lies outside the calibration profile tolerance.

It is forbidden to generate a relative waveform and label it absolute, or to
generate an anchor-scaled waveform while only clearing a later status bit.

## Explicit relative mode

`require_absolute_rcs=False` may use a valid in-condition anchor. If the anchor
or profile is invalid/out of condition, it deliberately ignores the anchor and
uses the documented relative voltage law:

```text
gain = sqrt(target_rcs_m2) * (physical_range / apparent_range)^2
```

The result is tagged `absolute_rcs_calibrated=False`. This fallback is never
permitted when absolute mode was requested.
