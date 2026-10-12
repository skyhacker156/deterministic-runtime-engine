package cs4;

import io.grpc.CallOptions;
import io.grpc.ClientCall;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import io.grpc.Status;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.PrintWriter;
import java.io.UncheckedIOException;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * CS4 Java client (grpc-java 1.84.2, CS4_AMENDMENT_1.md). Same request body,
 * retry policy and log format as the Go client (harness/go). Labels:
 * {@code java} (default environment) and {@code javaNoJitter}
 * ({@code GRPC_EXPERIMENTAL_XDS_RLS_LB=false} set before JVM start).
 *
 * <p>It refuses to run unless the label matches what it can check at
 * runtime: grpc version, transport builder, the environment variable and
 * system property, and the jitter flag as RetriableStream resolved it.
 */
public final class Client {
  static final String FULL_METHOD = "cs4.Probe/Run";
  static final String SERVICE = "cs4.Probe";
  static final String FLAG = "GRPC_EXPERIMENTAL_XDS_RLS_LB";
  static final String VERSION = "1.84.2";

  /** Scenario: {deadline ms, timing policy 0/1}. Mirrors harness/go/internal/cs4/cs4.go. */
  static final Map<String, long[]> SCENARIOS = Map.of(
      "S", new long[] {10000, 0},
      "X5", new long[] {10000, 0},
      "X1", new long[] {10000, 0},
      "X2HI", new long[] {2000, 0},
      "X2MAX", new long[] {2000, 0},
      "X2NEG", new long[] {2000, 0},
      "X4P", new long[] {10000, 0},
      "X4Z", new long[] {10000, 0},
      "T", new long[] {10000, 1});

  static final MethodDescriptor.Marshaller<byte[]> RAW = new MethodDescriptor.Marshaller<>() {
    @Override
    public InputStream stream(byte[] value) {
      return new ByteArrayInputStream(value);
    }

    @Override
    public byte[] parse(InputStream stream) {
      try {
        return stream.readAllBytes();
      } catch (IOException e) {
        throw new UncheckedIOException(e);
      }
    }
  };

  static final MethodDescriptor<byte[], byte[]> METHOD =
      MethodDescriptor.<byte[], byte[]>newBuilder()
          .setType(MethodDescriptor.MethodType.SERVER_STREAMING)
          .setFullMethodName(FULL_METHOD)
          .setRequestMarshaller(RAW)
          .setResponseMarshaller(RAW)
          .build();

  /**
   * CS4_AMENDMENT_2.md: a method the server does not register. One call to it
   * warms the JVM, channel and retry path before the measured calls; the
   * grpc-go server answers UNIMPLEMENTED without reaching the CS4 handler.
   */
  static final MethodDescriptor<byte[], byte[]> WARMUP =
      METHOD.toBuilder().setFullMethodName("cs4.Probe/Warmup").build();

  /** Retry policy as in harness/go/internal/cs4 ServiceConfig: no throttling, no hedging. */
  static Map<String, Object> serviceConfig(boolean timing) {
    Map<String, Object> retry = new TreeMap<>();
    retry.put("maxAttempts", timing ? 5.0 : 3.0);
    retry.put("initialBackoff", "0.2s");
    retry.put("maxBackoff", "0.2s");
    retry.put("backoffMultiplier", 1.0);
    retry.put("retryableStatusCodes", List.of("UNAVAILABLE"));
    Map<String, Object> mc = new HashMap<>();
    mc.put("name", List.of(Map.of("service", SERVICE)));
    mc.put("retryPolicy", retry);
    return Map.of("methodConfig", List.of(mc));
  }

  static void fail(String msg) {
    System.err.println("FATAL: " + msg);
    System.exit(2);
  }

  static String json(String s) {
    StringBuilder b = new StringBuilder("\"");
    for (char c : s.toCharArray()) {
      switch (c) {
        case '"': b.append("\\\""); break;
        case '\\': b.append("\\\\"); break;
        case '\n': b.append("\\n"); break;
        case '\r': b.append("\\r"); break;
        case '\t': b.append("\\t"); break;
        default:
          if (c < 0x20 || c > 0x7e) {
            b.append(String.format("\\u%04x", (int) c));
          } else {
            b.append(c);
          }
      }
    }
    return b.append('"').toString();
  }

  static String sha256(Path p) throws Exception {
    return HexFormat.of().withUpperCase().formatHex(
        MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p)));
  }

  /** Checks the label against the runtime; returns a description line. */
  static String checkLabel(String label, ManagedChannelBuilder<?> builder) throws Exception {
    if (!label.equals("java") && !label.equals("javaNoJitter")) {
      fail("unknown -client " + label + " (java or javaNoJitter)");
    }
    Object v = Class.forName("io.grpc.internal.GrpcUtil").getField("IMPLEMENTATION_VERSION").get(null);
    if (!VERSION.equals(v)) {
      fail("grpc-java version " + v + ", need " + VERSION);
    }
    String b = builder.getClass().getName();
    if (!b.equals("io.grpc.netty.NettyChannelBuilder")) {
      fail("channel builder " + b + ", need io.grpc.netty.NettyChannelBuilder");
    }
    String env = System.getenv(FLAG);
    String prop = System.getProperty(FLAG);
    if (prop != null) {
      fail("system property " + FLAG + " must not be set");
    }
    if (label.equals("java") && env != null) {
      fail("-client java needs " + FLAG + " unset, found \"" + env + "\"");
    }
    if (label.equals("javaNoJitter") && !"false".equals(env)) {
      fail("-client javaNoJitter needs " + FLAG + "=false, found " + (env == null ? "unset" : "\"" + env + "\""));
    }
    Class<?> rs = Class.forName("io.grpc.internal.RetriableStream");
    Field f = rs.getDeclaredField("isExperimentalRetryJitterEnabled");
    f.setAccessible(true);
    boolean jitter = f.getBoolean(null);
    if (jitter != label.equals("java")) {
      fail("RetriableStream jitter flag is " + jitter + " for -client " + label);
    }
    Path jar = Paths.get(rs.getProtectionDomain().getCodeSource().getLocation().toURI());
    return String.format("grpc %s builder=%s %s=%s jitterFlag=%s RetriableStream from %s sha256=%s",
        v, b, FLAG, env == null ? "unset" : env, jitter, jar.getFileName(), sha256(jar));
  }

  public static void main(String[] args) throws Exception {
    Map<String, String> a = new HashMap<>();
    boolean checkOnly = false;
    for (int i = 0; i < args.length; i++) {
      if (args[i].equals("-check")) {
        checkOnly = true;
      } else if (args[i].startsWith("-") && i + 1 < args.length) {
        a.put(args[i].substring(1), args[++i]);
      } else {
        fail("bad argument " + args[i]);
      }
    }
    String label = a.getOrDefault("client", "");
    String addr = a.getOrDefault("addr", "127.0.0.1:50051");
    int colon = addr.lastIndexOf(':');
    if (colon < 0) {
      fail("-addr must be host:port");
    }
    ManagedChannelBuilder<?> builder = ManagedChannelBuilder.forAddress(
        addr.substring(0, colon), Integer.parseInt(addr.substring(colon + 1)));
    String info = checkLabel(label, builder);
    if (checkOnly) {
      System.out.println("CHECK " + label + " " + info);
      return;
    }

    String scen = a.getOrDefault("scenario", "");
    String run = a.getOrDefault("run", "");
    String out = a.getOrDefault("out", "");
    int n = Integer.parseInt(a.getOrDefault("n", "0"));
    long[] sc = SCENARIOS.get(scen);
    if (sc == null || n <= 0 || run.isEmpty() || out.isEmpty()) {
      fail("usage: -client L -scenario S -n N -run TAG -out FILE [-addr A] | -client L -check");
    }
    System.out.println("CLIENT " + label + " " + info + " scenario=" + scen + " n=" + n);

    ManagedChannel ch = builder
        .usePlaintext()
        .enableRetry()
        .defaultServiceConfig(serviceConfig(sc[1] == 1))
        .build();
    Map<String, Integer> tally = new TreeMap<>();
    String[] wu = call(ch, WARMUP, new byte[0], 10000);
    if (!wu[0].equals("UNIMPLEMENTED")) {
      ch.shutdownNow();
      fail("warm-up call ended with " + wu[0] + " (" + wu[2] + "), need UNIMPLEMENTED");
    }
    System.out.printf("WARMUP cs4.Probe/Warmup %s in %.1f ms (not logged)%n", wu[0], Long.parseLong(wu[1]) / 1e6);
    try (PrintWriter w = new PrintWriter(Files.newBufferedWriter(Paths.get(out), StandardCharsets.UTF_8,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE))) {
      for (int i = 0; i < n; i++) {
        String id = String.format("%s.%s.%s.%03d", run, label, scen, i);
        String body = "{\"call_id\":" + json(id) + ",\"scenario\":" + json(scen)
            + ",\"client\":" + json(label) + "}";
        String[] r = call(ch, METHOD, body.getBytes(StandardCharsets.UTF_8), sc[0]);
        tally.merge(r[0], 1, Integer::sum);
        w.println("{\"client\":" + json(label) + ",\"scenario\":" + json(scen) + ",\"call_id\":" + json(id)
            + ",\"final_code\":" + json(r[0]) + ",\"elapsed_ns\":" + r[1] + ",\"message\":" + json(r[2]) + "}");
        w.flush();
        if (w.checkError()) {
          fail("client log write failed");
        }
      }
    } finally {
      ch.shutdownNow();
      ch.awaitTermination(5, TimeUnit.SECONDS);
    }
    System.out.println("CLIENT done: " + n + " calls, final codes " + tally + ", log " + out);
  }

  /** One server-streaming call. Returns {final code name, elapsed ns, message}. */
  static String[] call(ManagedChannel ch, MethodDescriptor<byte[], byte[]> method, byte[] body,
      long deadlineMs) throws Exception {
    CompletableFuture<Status> done = new CompletableFuture<>();
    AtomicInteger msgs = new AtomicInteger();
    long t0 = System.nanoTime();
    ClientCall<byte[], byte[]> c =
        ch.newCall(method, CallOptions.DEFAULT.withDeadlineAfter(deadlineMs, TimeUnit.MILLISECONDS));
    c.start(new ClientCall.Listener<byte[]>() {
      @Override
      public void onMessage(byte[] message) {
        msgs.incrementAndGet();
      }

      @Override
      public void onClose(Status status, Metadata trailers) {
        done.complete(status);
      }
    }, new Metadata());
    c.request(Integer.MAX_VALUE);
    c.sendMessage(body);
    c.halfClose();
    Status s = done.get(deadlineMs + 30_000, TimeUnit.MILLISECONDS);
    long elapsed = System.nanoTime() - t0;
    String msg = s.getDescription() == null ? "" : s.getDescription();
    if (msgs.get() > 0) {
      msg = (msg + " (received " + msgs.get() + " unexpected messages)").trim();
    }
    return new String[] {s.getCode().name(), Long.toString(elapsed), msg};
  }
}
