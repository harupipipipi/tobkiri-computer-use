# Foreground pointer probe

`ForegroundPointerProbe` is a read-only sampler for fixture trials. It writes
JSON lines containing uptime, the current frontmost process ID, and the
hardware pointer position. It does not activate an application, post input, or
establish that a target received an event.

The sole argument is a **bare duration in seconds**, from `0` through `120`.
For example, use the separately compiled validated binary for a 20-second
sample window:

```sh
artifacts/foreground-pointer-probe-validated 20 > artifacts/foreground-probe.jsonl
```

Do not use `--seconds 20`; option-style arguments, missing arguments, multiple
arguments, non-numeric values, and durations outside the range are rejected
with usage text. A duration of `0` produces one immediate sample, which is
useful only for checking invocation and is not an overlap measurement.

Compile a new trial binary without replacing an existing probe:

```sh
swiftc tests/fixtures/ForegroundPointerProbe.swift \
  -o artifacts/foreground-pointer-probe-validated
```
