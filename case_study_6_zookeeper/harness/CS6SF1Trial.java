/*
 * CS6-SF1 single-trial harness (ZooKeeper 3.9.6). ADDITIVE: CS6Trial.java is
 * unchanged. Pre-registration: CS6_SF1_PLAN.md (frozen, hash 2580427C).
 *
 * Difference from CS6: instead of HOLD (blackhole) on node 2's learner channel,
 * this applies DELAY(ms) via Proxy A, so node 2 stays CONNECTED and following but
 * lags on Z. We then force the session-preserving reconnect onto node 2 and read,
 * while collecting node 2's zabstate as an OBSERVED precondition (not inferred
 * from the configured delay). Classification is predeclared (CS6_SF1_PLAN.md s7).
 *
 * Modes:
 *   T0   - no-delay control: Proxy A left PASS; node 2 keeps up; failover read to
 *          node 2 should return Z (fresh). Demonstrates the rig does not
 *          manufacture staleness. RUN THIS FIRST.
 *   SF1  - delay condition: Proxy A set DELAY(--delayms); node 2 held in [A,Z).
 *   SYNC - safety control: SF1 plus a sync(path) before the read (expect catch-up).
 *
 * Witnesses are collected; interpretation is deferred (do not conclude from one run).
 *
 * Compile (operator box, real jars):
 *   javac -cp "C:\zk\apache-zookeeper-3.9.6-bin\lib\*" CS6SF1Trial.java
 * Run one trial:
 *   java -cp ".;C:\zk\apache-zookeeper-3.9.6-bin\lib\*" CS6SF1Trial `
 *     --mode SF1 --trial 1 --path /x --delayms 4000 `
 *     --client 127.0.0.1:12181 --node2 127.0.0.1:2182 --leader 127.0.0.1:2183 `
 *     --node2admin 8082 --leaderadmin 8083 --ctlA 13001 --ctlB 13002
 *
 * Roles (fixed, as CS6): S1 = node 1 via Proxy B (client 12181 -> 2181);
 * S2 = node 2 reached DIRECTLY on 2182, lagged via DELAY on Proxy A (learner
 * channel 12883 -> 2883). Leader = node 3 (2183). Admin: 8081/8082/8083.
 */
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Field;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.zookeeper.AsyncCallback;
import org.apache.zookeeper.CreateMode;
import org.apache.zookeeper.KeeperException;
import org.apache.zookeeper.Watcher;
import org.apache.zookeeper.WatchedEvent;
import org.apache.zookeeper.ZooDefs;
import org.apache.zookeeper.ZooKeeper;
import org.apache.zookeeper.data.Stat;

public class CS6SF1Trial {

    // ---- args ----
    static String mode = "SF1", path = "/x", client, node2, leader;
    static int ctlA, ctlB, trial, delayms = 4000, node2admin = 8082, leaderadmin = 8083;

    // ---- client-side observations ----
    static final CountDownLatch connectLatch = new CountDownLatch(1);
    static final CountDownLatch watchLatch = new CountDownLatch(1);
    static final AtomicBoolean sawExpired = new AtomicBoolean(false);
    static final AtomicReference<String> evType = new AtomicReference<>("(none)");
    static final AtomicReference<String> evPath = new AtomicReference<>("(none)");
    static final AtomicLong evZxid = new AtomicLong(-1);
    static final AtomicLong lastZxidAtNotify = new AtomicLong(-1);
    static ZooKeeper C;

    public static void main(String[] args) throws Exception {
        parse(args);
        boolean delayMode = !mode.equals("T0");
        // Start clean.
        ctl(ctlA, "pass"); ctl(ctlB, "pass");
        Thread.sleep(500);

        ZooKeeper W = new ZooKeeper(leader, 30000, e -> {});
        awaitConnected(W, 10000);
        ensureNode(W, path, "seed".getBytes(StandardCharsets.UTF_8));

        long A, Z = -1, lastAfterRead = -1;
        String valueA, valueRead = "(none)", remoteSetup, remoteRead = "(none)";
        long sidInit, sidFinal;
        long tFault, tNotify = -1, tReconnect = -1, tRead;
        boolean refused = false;
        String error = "";

        // Watcher + client C -> node 1 via Proxy B.
        Watcher w = CS6SF1Trial::onEvent;
        C = new ZooKeeper(client, 30000, w);
        if (!connectLatch.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("C did not connect");
        sidInit = C.getSessionId();

        // Setup read: establish watch and baseline lastZxid = A.
        Stat sA = new Stat();
        byte[] bA = C.getData(path, w, sA);
        valueA = new String(bA, StandardCharsets.UTF_8);
        A = lastZxid(C);
        remoteSetup = remote(C);

        // Fault BEFORE Z: DELAY node 2's learner channel (SF1/SYNC) so it lags but stays
        // connected. T0 leaves Proxy A at PASS (no lag). node 2 is added to C's server
        // list only later (adding earlier rebalances C off node 1 before the watch fires).
        if (delayMode) ctl(ctlA, "delay " + delayms);
        tFault = System.currentTimeMillis();

        // Writer commits Z (majority = leader + node 1; node 2 lags under DELAY).
        Stat sZ = C.setData(path, ("v" + trial + "-" + System.nanoTime()).getBytes(StandardCharsets.UTF_8), -1);
        Z = sZ.getMzxid();

        // C must learn Z only via the watch; lastZxid must NOT advance (notifyHeldA).
        if (!watchLatch.await(4, TimeUnit.SECONDS)) error = "watch did not fire";
        tNotify = System.currentTimeMillis();
        long lastBeforeFailover = lastZxid(C);

        // Force the session-preserving reconnect onto node 2.
        C.updateServerList(client + "," + node2);
        ctl(ctlB, "cut");
        tReconnect = System.currentTimeMillis();

        // OBSERVED preconditions at the start of the failover window (Gate 2).
        Zab n2AtReconnect = fetchZab(node2admin);
        Zab leadAtReconnect = fetchZab(leaderadmin);

        // Optional safety control: force catch-up before the read.
        if (mode.equals("SYNC")) { try { syncBlocking(C, path); } catch (Exception ex) { /* recorded via outcome */ } }

        // Failover read, retried while C fails over to node 2. ConnectionLoss is
        // expected transiently; a genuine barrier exhausts the retries (refused).
        refused = true;
        for (int attempt = 0; attempt < 20; attempt++) {
            try {
                Stat sR = new Stat();
                byte[] bR = C.getData(path, false, sR);
                valueRead = new String(bR, StandardCharsets.UTF_8);
                lastAfterRead = lastZxid(C);
                remoteRead = remote(C);
                refused = false;
                error = error.startsWith("watch") ? error : "";
                break;
            } catch (KeeperException ke) {
                error = "failover read (attempt " + attempt + "): "
                        + ke.getClass().getSimpleName() + " " + ke.getMessage();
                Thread.sleep(250);
            }
        }
        tRead = System.currentTimeMillis();
        Zab n2AtRead = fetchZab(node2admin);
        sidFinal = C.getSessionId();

        // Heal.
        ctl(ctlA, "pass"); ctl(ctlB, "pass");

        // ---- derived witnesses ----
        boolean notifyHeldA   = (lastZxidAtNotify.get() == A);
        boolean servedByNode2 = remoteRead.contains(portOf(node2));
        boolean valuePreZ     = valueRead.equals(valueA);
        boolean zxidBelowZ    = !refused && lastAfterRead >= 0 && lastAfterRead < Z;
        boolean gFollowing    = n2AtReconnect.ok && n2AtReconnect.state.equalsIgnoreCase("broadcast") && !n2AtReconnect.isLeader;
        boolean gQuorum       = leadAtReconnect.ok && leadAtReconnect.state.equalsIgnoreCase("broadcast") && leadAtReconnect.isLeader;
        boolean reachedBehindZ = n2AtReconnect.ok && n2AtReconnect.zxid >= A && n2AtReconnect.zxid < Z;
        boolean servedBehindZ  = n2AtRead.ok && n2AtRead.zxid >= 0 && n2AtRead.zxid < Z;

        // ---- predeclared classification (CS6_SF1_PLAN.md s7; do NOT interpret here) ----
        String outcome;
        if (mode.equals("T0")) {
            if (refused) outcome = "T0_FAILOVER_BLOCKED_unexpected";
            else if (servedByNode2 && !valuePreZ) outcome = "T0_FRESH_as_predicted";
            else if (servedByNode2 && valuePreZ) outcome = "T0_STALE_unexpected";   // control contaminated
            else outcome = "T0_INCONCLUSIVE";
        } else if (error.startsWith("watch")) {
            outcome = "SF1_INCONCLUSIVE_no_watch";
        } else if (!notifyHeldA) {
            outcome = "SF1_INCONCLUSIVE_notify_not_held";
        } else if (!gQuorum) {
            outcome = "SF1_INCONCLUSIVE_quorum_unhealthy";
        } else if (!gFollowing) {
            outcome = "SF1_INCONCLUSIVE_node2_not_following";   // left quorum / not a healthy follower
        } else if (refused) {
            outcome = "SF1_BARRIER_BLOCKED";                    // reconnect/session establishment blocked
        } else if (!servedByNode2) {
            outcome = "SF1_INCONCLUSIVE_not_s2";                // failover did not land on node 2
        } else if (!reachedBehindZ) {
            outcome = "SF1_INCONCLUSIVE_window_missed";         // node 2 already >= Z at failover start
        } else if (valuePreZ && zxidBelowZ && servedBehindZ) {
            outcome = "SF1_STALE_OBSERVED";                     // CANDIDATE - reproduce + source-analyze (later)
        } else if (!valuePreZ && servedBehindZ) {
            outcome = "SF1_SAFE_forced_forward";                // node 2 behind-Z yet read returned Z
        } else if (!valuePreZ && !servedBehindZ) {
            outcome = "SF1_INCONCLUSIVE_caughtup_before_read";  // window closed naturally before the read
        } else {
            outcome = "SF1_INCONCLUSIVE";
        }

        long windowMs = tRead - tFault;

        StringBuilder j = new StringBuilder();
        j.append("{");
        kv(j, "trial", trial); kv(j, "mode", q(mode)); kv(j, "delayMs", delayms); kv(j, "outcome", q(outcome));
        kv(j, "A", hex(A)); kv(j, "Z", hex(Z));
        kv(j, "lastBeforeFailover", hex(lastBeforeFailover));
        kv(j, "lastZxidAtNotify", hex(lastZxidAtNotify.get()));
        kv(j, "lastAfterRead", hex(lastAfterRead));
        kv(j, "valueA", q(valueA)); kv(j, "valueRead", q(valueRead));
        kv(j, "eventType", q(evType.get())); kv(j, "eventPath", q(evPath.get())); kv(j, "eventZxid", hex(evZxid.get()));
        kv(j, "remoteSetup", q(remoteSetup)); kv(j, "remoteRead", q(remoteRead));
        // observed zabstate witnesses (Gate 2)
        kv(j, "n2ZabReconnect", q(n2AtReconnect.state)); kv(j, "n2IsLeaderReconnect", n2AtReconnect.isLeader);
        kv(j, "n2ZxidReconnect", hex(n2AtReconnect.zxid)); kv(j, "n2ZabOkReconnect", n2AtReconnect.ok);
        kv(j, "n2ZxidAtRead", hex(n2AtRead.zxid)); kv(j, "n2ZabOkAtRead", n2AtRead.ok);
        kv(j, "leaderZab", q(leadAtReconnect.state)); kv(j, "leaderIsLeader", leadAtReconnect.isLeader);
        // gates / derived
        kv(j, "notifyHeldA", notifyHeldA); kv(j, "gFollowing", gFollowing); kv(j, "gQuorum", gQuorum);
        kv(j, "reachedBehindZ", reachedBehindZ); kv(j, "servedBehindZ", servedBehindZ);
        kv(j, "servedByNode2", servedByNode2); kv(j, "valuePreZ", valuePreZ); kv(j, "zxidBelowZ", zxidBelowZ);
        kv(j, "refused", refused);
        kv(j, "sessionStable", (sidInit == sidFinal) && !sawExpired.get());
        kv(j, "sidInit", hex(sidInit));
        kv(j, "tFault", tFault); kv(j, "tNotify", tNotify); kv(j, "tReconnect", tReconnect); kv(j, "tRead", tRead);
        kv(j, "windowMs", windowMs);
        kv(j, "error", q(error), true);
        j.append("}");
        System.out.println(j.toString());

        C.close(); W.close();
    }

    // ---- watcher ----
    static void onEvent(WatchedEvent e) {
        if (e.getType() == Watcher.Event.EventType.None) {
            if (e.getState() == Watcher.Event.KeeperState.SyncConnected) connectLatch.countDown();
            if (e.getState() == Watcher.Event.KeeperState.Expired) sawExpired.set(true);
        } else {
            evType.set(String.valueOf(e.getType()));
            evPath.set(String.valueOf(e.getPath()));
            evZxid.set(e.getZxid());
            lastZxidAtNotify.set(lastZxid(C));
            watchLatch.countDown();
        }
    }

    // ---- zabstate over AdminServer (observed precondition) ----
    static class Zab { String state = "(none)"; boolean isLeader = false; long zxid = -1; boolean ok = false; }
    static final Pattern P_ZXID  = Pattern.compile("\"last_zxid\"\\s*:\\s*\"?(0x[0-9a-fA-F]+)\"?");
    static final Pattern P_STATE = Pattern.compile("\"zabstate\"\\s*:\\s*\"([A-Za-z_]+)\"");
    static final Pattern P_LEAD  = Pattern.compile("\"is_leader\"\\s*:\\s*(true|false)");

    static Zab fetchZab(int adminPort) {
        Zab r = new Zab();
        HttpURLConnection con = null;
        try {
            URL u = new URL("http://127.0.0.1:" + adminPort + "/commands/zabstate");
            con = (HttpURLConnection) u.openConnection();
            con.setConnectTimeout(1500); con.setReadTimeout(1500); con.setRequestMethod("GET");
            InputStream is = con.getInputStream();
            ByteArrayOutputStream bo = new ByteArrayOutputStream();
            byte[] buf = new byte[4096]; int n;
            while ((n = is.read(buf)) > 0) bo.write(buf, 0, n);
            String body = new String(bo.toByteArray(), StandardCharsets.UTF_8);
            Matcher ms = P_STATE.matcher(body); if (ms.find()) r.state = ms.group(1);
            Matcher ml = P_LEAD.matcher(body);  if (ml.find()) r.isLeader = Boolean.parseBoolean(ml.group(1));
            Matcher mz = P_ZXID.matcher(body);  if (mz.find()) r.zxid = Long.parseLong(mz.group(1).substring(2), 16);
            r.ok = true;
        } catch (Exception ex) {
            r.ok = false;
        } finally {
            if (con != null) con.disconnect();
        }
        return r;
    }

    static void syncBlocking(ZooKeeper zk, String p) throws InterruptedException {
        final CountDownLatch l = new CountDownLatch(1);
        zk.sync(p, (AsyncCallback.VoidCallback) (rc, pth, ctx) -> l.countDown(), null);
        l.await(4, TimeUnit.SECONDS);
    }

    // ---- reflection helpers (unchanged from CS6) ----
    static long lastZxid(ZooKeeper zk) {
        try {
            Field f = ZooKeeper.class.getDeclaredField("cnxn");
            f.setAccessible(true);
            Object cnxn = f.get(zk);
            return (long) cnxn.getClass().getMethod("getLastZxid").invoke(cnxn);
        } catch (Exception ex) { return -1; }
    }

    static String remote(ZooKeeper zk) {
        try {
            Field f = ZooKeeper.class.getDeclaredField("cnxn");
            f.setAccessible(true);
            Object cnxn = f.get(zk);
            String s = cnxn.toString();
            int i = s.indexOf("remoteserver:");
            if (i < 0) return "(unknown)";
            String rest = s.substring(i + "remoteserver:".length()).trim();
            int sp = rest.indexOf(' ');
            return sp < 0 ? rest : rest.substring(0, sp);
        } catch (Exception ex) { return "(unknown)"; }
    }

    // ---- small helpers ----
    static void ensureNode(ZooKeeper zk, String p, byte[] seed) throws KeeperException, InterruptedException {
        if (zk.exists(p, false) == null) {
            zk.create(p, seed, ZooDefs.Ids.OPEN_ACL_UNSAFE, CreateMode.PERSISTENT);
        }
    }

    static void awaitConnected(ZooKeeper zk, long ms) throws InterruptedException {
        long end = System.currentTimeMillis() + ms;
        while (zk.getState() != null && !zk.getState().isConnected() && System.currentTimeMillis() < end) {
            Thread.sleep(50);
        }
    }

    static void ctl(int port, String cmd) {
        try (Socket s = new Socket()) {
            s.connect(new InetSocketAddress("127.0.0.1", port), 3000);
            OutputStream o = s.getOutputStream();
            o.write(cmd.getBytes(StandardCharsets.US_ASCII));
            o.flush();
            s.getInputStream().read(new byte[64]);
        } catch (IOException ex) {
            System.err.println("ctl " + port + " " + cmd + " failed: " + ex.getMessage());
        }
    }

    static String portOf(String hostPort) {
        int i = hostPort.lastIndexOf(':');
        return i < 0 ? hostPort : hostPort.substring(i + 1);
    }

    static String q(String s) { return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""; }
    static String hex(long z) { return "\"0x" + Long.toHexString(z) + "\""; }
    static void kv(StringBuilder j, String k, Object v) { kv(j, k, v, false); }
    static void kv(StringBuilder j, String k, Object v, boolean last) {
        j.append("\"").append(k).append("\":").append(v);
        if (!last) j.append(",");
    }

    static void parse(String[] a) {
        for (int i = 0; i < a.length - 1; i += 2) {
            switch (a[i]) {
                case "--mode": mode = a[i+1]; break;
                case "--trial": trial = Integer.parseInt(a[i+1]); break;
                case "--path": path = a[i+1]; break;
                case "--delayms": delayms = Integer.parseInt(a[i+1]); break;
                case "--client": client = a[i+1]; break;
                case "--node2": node2 = a[i+1]; break;
                case "--leader": leader = a[i+1]; break;
                case "--node2admin": node2admin = Integer.parseInt(a[i+1]); break;
                case "--leaderadmin": leaderadmin = Integer.parseInt(a[i+1]); break;
                case "--ctlA": ctlA = Integer.parseInt(a[i+1]); break;
                case "--ctlB": ctlB = Integer.parseInt(a[i+1]); break;
            }
        }
    }
}
