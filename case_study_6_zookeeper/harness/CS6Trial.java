/*
 * CS6 single-trial harness (ZooKeeper 3.9.6).
 *
 * One trial of the H1 sequence or the T0 control. Prints one JSON line of the
 * G1-G7 witnesses plus a per-trial classification. A PowerShell driver loops
 * this and resets state between trials.
 *
 * Witnesses use the main client jar only:
 *   - lastZxid (G2/G6): ClientCnxn.getLastZxid() via reflection on ZooKeeper.cnxn
 *   - connected server (G7): parsed from ClientCnxn.toString() "remoteserver:"
 *   - event zxid/type/path (G1): WatchedEvent accessors
 *   - session (G5): ZooKeeper.getSessionId(), KeeperState.Expired watch
 *
 * Compile (on the operator's box, against the real jars):
 *   javac -cp "C:\zk\apache-zookeeper-3.9.6-bin\lib\*" CS6Trial.java
 * Run one trial:
 *   java -cp ".;C:\zk\apache-zookeeper-3.9.6-bin\lib\*" CS6Trial `
 *     --mode T1 --trial 1 --path /x `
 *     --client 127.0.0.1:12181 --node2 127.0.0.1:2182 --leader 127.0.0.1:2183 `
 *     --ctlA 13001 --ctlB 13002
 *
 * Roles (fixed): S1 = node 1 reached via Proxy B (client listen 12181 -> 2181);
 * S2 = node 2 reached directly on 2182, held behind the leader via Proxy A on
 * its learner channel. Leader = node 3 (2183).
 */
import java.io.IOException;
import java.io.OutputStream;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.apache.zookeeper.CreateMode;
import org.apache.zookeeper.KeeperException;
import org.apache.zookeeper.Watcher;
import org.apache.zookeeper.WatchedEvent;
import org.apache.zookeeper.ZooDefs;
import org.apache.zookeeper.ZooKeeper;
import org.apache.zookeeper.data.Stat;

public class CS6Trial {

    // ---- args ----
    static String mode = "T1", path = "/x", client, node2, leader;
    static int ctlA, ctlB, trial;

    // ---- client-side observations ----
    static final CountDownLatch connectLatch = new CountDownLatch(1);
    static final CountDownLatch watchLatch = new CountDownLatch(1);
    static final AtomicBoolean sawExpired = new AtomicBoolean(false);
    static final AtomicReference<String> evType = new AtomicReference<>("(none)");
    static final AtomicReference<String> evPath = new AtomicReference<>("(none)");
    static final AtomicLong evZxid = new AtomicLong(-1);
    static final AtomicLong lastZxidAtNotify = new AtomicLong(-1);
    static ZooKeeper C;   // referenced by the watcher to read lastZxid at notify time

    public static void main(String[] args) throws Exception {
        parse(args);
        // Start clean: both proxies PASS. (Driver also pre-checks convergence.)
        ctl(ctlA, "pass"); ctl(ctlB, "pass");
        Thread.sleep(500);

        // Writer connects to the leader directly.
        ZooKeeper W = new ZooKeeper(leader, 30000, e -> {});
        awaitConnected(W, 10000);
        ensureNode(W, path, "seed".getBytes(StandardCharsets.UTF_8));

        long A, Z = -1, lastAfterRead = -1;
        String valueA, valueRead = "(none)", remoteSetup, remoteRead = "(none)";
        long sidInit, sidFinal;
        long tHold, tNotify = -1, tRead;
        boolean refused = false;
        String error = "";

        // Client C connects to S1 (node 1) via Proxy B.
        Watcher w = CS6Trial::onEvent;
        C = new ZooKeeper(client, 30000, w);
        if (!connectLatch.await(10, TimeUnit.SECONDS)) throw new IllegalStateException("C did not connect");
        sidInit = C.getSessionId();

        // Setup read: establishes the watch (T1) and baseline lastZxid = A.
        Stat sA = new Stat();
        byte[] bA = C.getData(path, (mode.equals("T1") ? w : null), sA);
        valueA = new String(bA, StandardCharsets.UTF_8);
        A = lastZxid(C);
        remoteSetup = remote(C);

        // Partition node 2 from the leader BEFORE writing Z (fixed order).
        // NOTE: node 2 is added to C's server list only later (just before the cut).
        // Adding it here makes the client rebalance off node 1 before the watch fires.
        ctl(ctlA, "hold");
        tHold = System.currentTimeMillis();

        // Writer commits Z. Majority = leader + node 1; node 2 is held and will not see it.
        Stat sZ = C_write(W, path, ("v" + trial + "-" + System.nanoTime()).getBytes(StandardCharsets.UTF_8));
        Z = sZ.getMzxid();

        if (mode.equals("T1")) {
            // T1: C learns Z only via the watch notification; lastZxid must NOT advance.
            if (!watchLatch.await(4, TimeUnit.SECONDS)) { error = "watch did not fire"; }
            tNotify = System.currentTimeMillis();
        } else {
            // T0 control: C learns Z via an ordinary reply on node 1, advancing lastZxid to >= Z.
            Stat s0 = new Stat();
            C.getData(path, false, s0);
        }
        long lastBeforeFailover = lastZxid(C);

        // Only now add node 2 as a failover target (adding it earlier rebalances the client
        // off node 1 before the watch can fire), then cut node 1 so C fails over to node 2.
        C.updateServerList(client + "," + node2);
        ctl(ctlB, "cut");

        // The failover read, retried while the client fails over to node 2.
        // ConnectionLoss is expected transiently during failover; a genuine refusal
        // (T0: node 2 rejects the ahead-zxid session; or node 2 cannot revalidate its
        // global session while partitioned) never succeeds and exhausts the retries.
        refused = true;
        for (int attempt = 0; attempt < 20; attempt++) {
            try {
                Stat sR = new Stat();
                byte[] bR = C.getData(path, false, sR);
                valueRead = new String(bR, StandardCharsets.UTF_8);
                lastAfterRead = lastZxid(C);
                remoteRead = remote(C);
                refused = false;
                error = "";
                break;
            } catch (KeeperException ke) {
                error = "failover read (attempt " + attempt + "): "
                        + ke.getClass().getSimpleName() + " " + ke.getMessage();
                Thread.sleep(250);
            }
        }
        tRead = System.currentTimeMillis();
        sidFinal = C.getSessionId();

        // Heal.
        ctl(ctlA, "pass"); ctl(ctlB, "pass");

        // Classify (T1): stale read reproduced iff served by node 2, value is pre-Z,
        // and the serving server's reply-header zxid (now C's lastZxid) is below Z.
        boolean servedByNode2 = remoteRead.contains(portOf(node2));
        boolean valuePreZ = valueRead.equals(valueA);
        boolean zxidBelowZ = !refused && lastAfterRead >= 0 && lastAfterRead < Z;
        boolean notifyHeldA = (mode.equals("T1")) && (lastZxidAtNotify.get() == A);
        String outcome;
        if (mode.equals("T0")) {
            outcome = refused ? "T0_REFUSED_as_predicted" : "T0_UNEXPECTED_served";
        } else if (error.startsWith("watch")) {
            outcome = "T1_INCONCLUSIVE_no_watch";
        } else if (refused) {
            outcome = "T1_FAILOVER_BLOCKED";
        } else if (servedByNode2 && valuePreZ && zxidBelowZ) {
            outcome = "T1_STALE_reproduced";
        } else if (servedByNode2 && !valuePreZ) {
            outcome = "T1_FRESH_node2_served_current";
        } else {
            outcome = "T1_INCONCLUSIVE";
        }

        long elapsed = tRead - tHold;
        boolean windowOk = elapsed < 8000;

        StringBuilder j = new StringBuilder();
        j.append("{");
        kv(j, "trial", trial); kv(j, "mode", q(mode)); kv(j, "outcome", q(outcome));
        kv(j, "A", hex(A)); kv(j, "Z", hex(Z));
        kv(j, "lastBeforeFailover", hex(lastBeforeFailover));
        kv(j, "lastZxidAtNotify", hex(lastZxidAtNotify.get()));
        kv(j, "lastAfterRead", hex(lastAfterRead));
        kv(j, "valueA", q(valueA)); kv(j, "valueRead", q(valueRead));
        kv(j, "eventType", q(evType.get())); kv(j, "eventPath", q(evPath.get())); kv(j, "eventZxid", hex(evZxid.get()));
        kv(j, "remoteSetup", q(remoteSetup)); kv(j, "remoteRead", q(remoteRead));
        kv(j, "servedByNode2", servedByNode2); kv(j, "valuePreZ", valuePreZ);
        kv(j, "zxidBelowZ", zxidBelowZ); kv(j, "notifyHeldA", notifyHeldA);
        kv(j, "refused", refused);
        kv(j, "sessionStable", (sidInit == sidFinal) && !sawExpired.get());
        kv(j, "sidInit", hex(sidInit)); kv(j, "elapsedMs", elapsed); kv(j, "windowOk", windowOk);
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
            // The crux: record the client's tracked zxid at the instant of the node event.
            lastZxidAtNotify.set(lastZxid(C));
            watchLatch.countDown();
        }
    }

    // ---- reflection helpers ----
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
    static Stat C_write(ZooKeeper zk, String p, byte[] v) throws KeeperException, InterruptedException {
        return zk.setData(p, v, -1);
    }

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
                case "--client": client = a[i+1]; break;
                case "--node2": node2 = a[i+1]; break;
                case "--leader": leader = a[i+1]; break;
                case "--ctlA": ctlA = Integer.parseInt(a[i+1]); break;
                case "--ctlB": ctlB = Integer.parseInt(a[i+1]); break;
            }
        }
    }
}
