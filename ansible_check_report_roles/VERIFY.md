# Verification Contract

The wrapper is the verification boundary.

## Success

The run is successful only when the wrapper prints exactly:

```text
OK
```

## Failure

Any other output must be treated as failure.

Expected failure format:

```text
FAIL reason=<reason> log_dir=<path>
```

## Reporting

Reply with the wrapper output only.

