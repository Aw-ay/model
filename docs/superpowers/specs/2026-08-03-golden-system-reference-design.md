# Golden System Reference Design

## 1. Goal and boundary

Extend the existing clock-free Golden layer from two independent mathematical
references into one minimal system-level reference:

```text
RFDC complex input
  -> +20/0/-20 dB receive paths and independent loopback path
  -> pulse records
  -> range association
  -> injectable decision policy
  -> DAC-domain commands
  -> conflict-aware scheduling
  -> four routed real DAC baseband arrays
```

The ADC/RFDC complex baseband array is the receive boundary. RF propagation,
antenna effects, targets, Doppler, multipath and analogue calibration are not
part of this milestone. RX-triggered transmission is not hard-coded system
behavior: `GoldenPulseSystem` requires a decision-policy object, and a
no-transmit policy remains a valid configuration.

## 2. Alternatives considered

### A. Minimal system-level reference (selected)

Add multi-range receive, association, a replaceable RX-to-TX policy, scheduler
and four-DAC routing. This closes the functional Golden chain needed to define
later Cycle semantics without introducing RF simulation.

### B. Receive-only completion

Add only multi-range receive and association. This is lower risk, but it still
cannot verify command timing, busy behavior or output routing and therefore
does not satisfy the system-level Layer-1 goal.

### C. Full radar/channel simulation

Add targets, propagation delay, Doppler, path loss and multipath. This is useful
for a radar-system simulator but is outside the current FPGA contract and would
delay Cycle-model work.

## 3. Shared time and numeric contracts

- `SignalScenario` is sampled in `SampleDomain.RFDC_COMPLEX_INPUT` at
  `rfdc_complex_sample_rate_hz` (default 500 MSPS complex).
- `PulseRecord` ToA/PW and `freq_word` remain in `SampleDomain.DETECTOR` at
  `detector_sample_rate_hz` (default 250 MSPS).
- `TxCommand.trigger_sample` and all scheduled output arrays are in
  `SampleDomain.DAC_BASEBAND` at
  `dac_sample_rate_hz / rfdc_interpolation` (default 500 MSPS real).
- Detector-to-DAC time conversion must be exact integer rational arithmetic.
  A configuration whose event time cannot map exactly is rejected rather than
  rounded silently.
- IQ and power formats continue to come only from `ModelConfig` and are stamped
  into every `PulseRecord`.
- All scalar and array quantization uses project ties-away-from-zero rounding.

## 4. Receive architecture

Add `golden/multirange.py` with:

```python
@dataclass(frozen=True)
class GoldenChannelReceiveResult:
    channel: int
    range_id: RangeId
    gain_db: int
    adc: AdcSampleBatch
    decimated: GoldenReceiveResult
    records: tuple[PulseRecord, ...]

@dataclass(frozen=True)
class GoldenMultiRangeReceiveResult:
    channels: tuple[GoldenChannelReceiveResult, ...]
    records: tuple[PulseRecord, ...]
    events: tuple[PulseEvent, ...]

class GoldenMultiRangeReceiver:
    def process(
        self,
        antenna_iq: np.ndarray,
        loopback_iq: np.ndarray | None = None,
    ) -> GoldenMultiRangeReceiveResult:
        ...
```

Channels 0/1/2 consume the same antenna input with configured gains
`+20/0/-20 dB`. The configured loopback channel consumes only `loopback_iq`
with its configured gain. If loopback input is absent, that channel receives a
zero array of matching length.

Each channel owns a separate `GoldenReceivePipeline`. All non-loopback records
are passed through `associate_range_records()`. Loopback records remain
one-record events and are never joined to external range events.

The existing greedy ToA/PW association remains the milestone algorithm. Dense
pulse global matching is deferred and must not be implied by the API.

## 5. Frequency-estimation correction

`GoldenPulseDetector` currently removes zero-amplitude samples before phase
differencing, which incorrectly joins samples separated by a zero/deep-fade
gap. The corrected estimator retains original indices and includes only pairs
whose indices differ by exactly one. If no adjacent valid pair exists, it
returns zero turns/sample.

This correction is isolated and covered by a regression test before the
system-level features are added.

## 6. Decision-policy contract

Add the shared immutable command type:

```python
@dataclass(frozen=True)
class TxCommand:
    event_id: int
    trigger_sample: int
    path: RangeId
    loopback_enable: bool
    phase_inc_0: int
    phase_inc_step: int
    pulse_samples: int
    amplitude_q15: int
    settle_samples: int = 0
```

`TxCommand` uses DAC-baseband sample indices. It validates nonnegative timing,
positive width, unsigned 32-bit modulo phase words and Q15 amplitude. A
negative chirp step is represented by its 32-bit two's-complement word, matching
the existing accumulator contract.

Add `golden/policy.py`:

```python
class GoldenDecisionPolicy(Protocol):
    def decide(
        self,
        events: Sequence[PulseEvent],
        config: ModelConfig,
    ) -> tuple[TxCommand, ...]:
        ...
```

Two concrete policies are required:

- `NoTransmitPolicy`: always returns no commands.
- `EventLfmPolicy`: maps each eligible non-loopback event to a command using
  explicit waveform parameters and response delay. Its path selection uses
  `event.selected_range`; eligibility of all-saturated events is an explicit
  policy option, never an implicit fallback.

The policy is pure: it does not schedule, mutate state or generate samples.

## 7. Scheduler and four-DAC routing

Add `golden/scheduler.py`:

```python
@dataclass(frozen=True)
class GoldenTransmitResult:
    sample_domain: SampleDomain
    sample_rate_hz: int
    dac: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
    active_mask: np.ndarray
    accepted_commands: tuple[TxCommand, ...]
    dropped_commands: tuple[TxCommand, ...]

class GoldenTxScheduler:
    def schedule(
        self,
        commands: Sequence[TxCommand],
        total_samples: int,
    ) -> GoldenTransmitResult:
        ...
```

Commands are ordered by `(trigger_sample, event_id)`. A command occupies
`settle_samples + pulse_samples` beginning at `trigger_sample`; settle samples
are zeros but keep the transmitter busy. If a command overlaps an accepted
command, the later command is rejected and returned in `dropped_commands`.
This matches the current busy-reject control direction and avoids hidden delay.

The LFM phase starts from zero for every accepted command. Its waveform starts
after settle time and is routed only to the selected path. When
`loopback_enable` is true, the same waveform is also routed to the configured
loopback DAC. A command whose selected path is loopback routes only there.
`active_mask` is used instead of a single active-path value because a selected
range and loopback can be active simultaneously.

No AXI `valid/ready`, clock cycles or RFDC interpolation images exist in this
Golden scheduler.

## 8. System top

Add `golden/system.py`:

```python
@dataclass(frozen=True)
class GoldenSystemResult:
    input_iq: np.ndarray
    receive: GoldenMultiRangeReceiveResult
    tx_commands: tuple[TxCommand, ...]
    transmit: GoldenTransmitResult

class GoldenPulseSystem:
    def run(
        self,
        scenario: SignalScenario,
        *,
        loopback_iq: np.ndarray | None = None,
        total_tx_samples: int | None = None,
    ) -> GoldenSystemResult:
        ...
```

`run()` generates the RFDC-domain scenario, executes multi-range reception,
passes events to the injected policy and schedules the result. If
`total_tx_samples` is omitted, the RFDC scenario duration is converted exactly
to the DAC-baseband duration. Commands extending past the result boundary are
rejected rather than truncated silently.

The system does not feed generated DAC3 samples back into the receiver in the
same call. Such feedback needs an explicit channel/delay model and belongs to a
later optional milestone.

## 9. Errors and deterministic behavior

- Wrong-dimensional antenna or loopback arrays are rejected.
- Antenna and loopback arrays must have equal length when both are supplied.
- Invalid rate relationships are rejected by `ModelConfig`.
- Commands outside the output window, overlapping accepted commands or ending
  beyond the output window are returned as dropped commands.
- Equal-time commands have deterministic `event_id` ordering.
- All arrays have fixed explicit dtypes and idle DAC samples are exactly zero.

## 10. TDD acceptance scenarios

1. Frequency estimation ignores nonadjacent nonzero sample pairs across a gap.
2. A moderate pulse produces three associated range records and selects +20 dB.
3. A pulse clipping +20 dB but not 0 dB selects the 0 dB record.
4. Noise-only input produces no event, no command and four zero DAC arrays.
5. A policy-generated command routes only to its selected DAC; optional
   loopback duplicates it only to DAC3.
6. Loopback receive records never associate with the three external ranges.
7. Overlapping commands accept the earlier command and explicitly drop the
   later command.
8. The system top preserves all three sample-domain/rate declarations.

Golden tests prove mathematical and functional semantics only. They do not
prove Cycle timing, RTL equivalence, Block Design interfaces, CDC, timing
closure or board behavior.
