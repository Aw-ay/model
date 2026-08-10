# Stream Status and Online PDW Contract

Status: frozen for ModelConfig schema/config `8/14`.

`GoldenReflectionStream.process_chunk()` has two independent progress fronts:

- `processed_stop_sample`: exclusive absolute RFDC sample after the last input
  accepted by the stream;
- `emitted_stop_sample`: exclusive absolute RFDC sample after the stable
  waveform prefix returned so far.

Fractional-delay look-ahead can make the emitted front lag the processed
front. `selected_ranges` describes the range state after accepted input,
whereas the returned waveform arrays cover only the newly emitted stable
interval. `emitted_stop_sample` can never exceed `processed_stop_sample`.

## PDW/event delivery

A non-final call emits every newly stable `PulseRecord` and `PulseEvent`. A
record is withheld while the current buffer end could still change pulse
closure, refinement, post-trigger IQ or range association. `final=True`
defines end-of-input and flushes all remaining records.

Delivery rules are:

1. sort by global detector-domain `(ToA, channel)` as in the one-shot result;
2. emit only a stable prefix, never a later record ahead of an earlier pending
   record;
3. emit each PDW and event exactly once;
4. concatenated per-call PDWs/events equal one-shot order and contents;
5. a pulse artificially closed by a software chunk boundary is not emitted.

Status counters are unambiguous:

```text
monitor_pulse_count       = PDWs newly emitted in this call
monitor_pulse_count_total = PDWs emitted since stream start
stream_final              = final input accepted; further chunks forbidden
```

This Golden implementation may recompute full history, but Cycle must realize
the same observable rules with bounded detector state, queues and overflow
reporting.
