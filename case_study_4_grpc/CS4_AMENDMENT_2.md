# Case Study 4, amendment 2: Java warm-up call and timing upper bound

Dated amendment, written 2026-10-12, after the Java development run of
scenario S (`results/dev_20261012_java/`, commit `c7aab89`) and before any
scored run. No scored run of any scenario has been made. The plan
(`CS4_PLAN.md`, `ca4ccaa`) and amendment 1 (`ae942d8`) are not edited.
Decided by the operator on 2026-10-12.

## Trigger

Two observations in allowed development data (scenario S only; no X5, X1,
X2 or T data exists for any subject configuration):

1. **Slow first Java call.** Client-side elapsed time of the 20 `java` S
   calls: call 0 608.4 ms, call 1 59.0 ms, calls 2-19 19.8 to 32.3 ms. The
   `go184` S calls took 10.5 to 14.4 ms, including call 0. The first Java
   call carries JVM class loading and Netty start-up. The plan classes an X2
   call as *immediate* only below 500 ms, and requires all 20 calls of a
   scenario to give one tuple. Java's call 0 in X2HI and X2NEG would
   therefore probably class as *other* and make the verdict
   NONDETERMINISTIC for a reason unrelated to grpc's retry decision.
2. **Late Java retries.** Server-side gap between attempt 1 and attempt 2
   (pushback 10 ms): `java` 16.3 to 40.2 ms (median 27.4 ms); `go184` and
   the planted Go copies 10.1 to 11.3 ms. The Java overshoot, about 16 to
   30 ms, is consistent with timer granularity on Windows (about 15.6 ms)
   but its cause was not established. Applied to the timing track (200 ms
   base), an overshoot of up to 30 ms adds up to 0.15 to *r*. The A6 class
   requires at least 95 per cent of *r* at most 1.30, and A6 jitter reaches
   1.20, leaving a margin of 0.10.

## Changes

1. **Java warm-up call.** Before its measured calls, after building the
   channel, the Java client makes one call to `/cs4.Probe/Warmup`, a method
   the server does not register. It must end with `UNIMPLEMENTED`; any other
   status stops the client (exit 2). The grpc-go server, which sets no
   unknown-service handler, answers an unknown method of a known service
   with `UNIMPLEMENTED` without invoking the CS4 handler (`server.go`
   1592-1614 at v1.84.0), so the warm-up reaches neither the server's
   attempt log nor the client log. It uses the same channel,
   service config, retry path and transport as the measured calls; with no
   pushback and a non-retryable status it is not retried. The Go client is
   unchanged: its first call already took 14.4 ms, and rebuilding it would
   void the recorded binaries and development runs.
2. **Timing upper bound.** In the A6 class, "at least 95 per cent of *r* at
   most 1.30" becomes "at least 95 per cent of *r* at most 1.40", for every
   configuration. The lower bound (no *r* below 0.80), the old-range rule
   (at least 70 per cent of *r* below 0.80), the sample sizes and every
   prediction are unchanged. Positive overshoot cannot move a delay below
   0.80, so the comparison that separates the A6 range from the old range
   is not affected.

The checker constant (`internal/oracle`, `RHigh`), its boundary tests, and
the report field and column naming the bound change accordingly. The
server, the Go clients and their binaries are unchanged; only `checker`
is rebuilt.

## What this does not change

The decision-track scenarios, deadlines, *immediate* and *waited*
thresholds, replay rule, controls, gates and stop rule are as in the plan
and amendment 1. The warm-up is the only change to what a client sends.

## Check

A second Java development run of scenario S, with the warm-up, is made
after this amendment is committed and before any scored run. Its first
call's elapsed time is recorded in `DEV_LOG.md`. If call 0 is still at or
above 500 ms, the X2 Java rows are reported with that fact and a further
amendment is considered before they run.
