/*
 * CS7 (C1) client. Java + Apache Curator 5.9.0. Pre-registration: CS7_C1_PREREGISTRATION.md (cs7-c1).
 *
 * Models a realistic application that FOLLOWS Curator's documented connection-state
 * guidance: it registers a ConnectionStateListener that sets a volatile `lockLost`
 * flag on SUSPENDED/LOST, and checks `!lockLost` before writing to the external
 * resource. The fencing token is the ephemeral lock node's sequence number
 * (monotonic across acquisitions), extracted via reflection (holder's lockPath),
 * with a getParticipantNodes() fallback.
 *
 * Roles:
 *   A  acquire -> print A_ACQUIRED (with OS pid, for PsSuspend) -> poll for the
 *      --gofile barrier (driver suspends A here so its session expires; driver
 *      creates --gofile only AFTER resuming A) -> on gofile: sample lockLost,
 *      then (if !lockLost) write to the resource IMMEDIATELY. This is the race the
 *      experiment turns on: a local resource write vs. the ZK client learning of
 *      session expiry on reconnect.
 *   B  acquire -> write to the resource (registers B's newer token BEFORE A's
 *      stale write, per the Arm F ordering requirement) -> hold until --holdfile
 *      appears, then release.
 *
 * Compile (operator box, with Curator + ZK + Guava + slf4j jars on the classpath):
 *   javac -cp "C:\cs7lib\*" C1Client.java
 * Run (examples):
 *   java -cp ".;C:\cs7lib\*" C1Client --role A --id A --zk 127.0.0.1:2181 `
 *     --lockpath /cs7/lock --resource 127.0.0.1:14000 --session 5000 `
 *     --value vA --gofile C:\tmp\A_GO
 *   java -cp ".;C:\cs7lib\*" C1Client --role B --id B --zk 127.0.0.1:2181 `
 *     --lockpath /cs7/lock --resource 127.0.0.1:14000 --session 5000 `
 *     --value vB --holdfile C:\tmp\B_HOLD
 */
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.curator.framework.CuratorFramework;
import org.apache.curator.framework.CuratorFrameworkFactory;
import org.apache.curator.framework.recipes.locks.InterProcessMutex;
import org.apache.curator.framework.state.ConnectionState;
import org.apache.curator.framework.state.ConnectionStateListener;
import org.apache.curator.retry.ExponentialBackoffRetry;

public class C1Client {

    static volatile boolean lockLost = false;
    static volatile long tListenerLost = -1;

    static String role, id, zk, lockpath, resource, value, gofile = "", holdfile = "";
    static int session = 5000;

    public static void main(String[] args) throws Exception {
        parse(args);
        final String pid = ManagementFactory.getRuntimeMXBean().getName().split("@")[0];

        CuratorFramework client = CuratorFrameworkFactory.builder()
                .connectString(zk)
                .sessionTimeoutMs(session)
                .connectionTimeoutMs(3000)
                .retryPolicy(new ExponentialBackoffRetry(1000, 3))
                .build();

        // Documented mitigation: treat SUSPENDED/LOST as lock-loss.
        client.getConnectionStateListenable().addListener(new ConnectionStateListener() {
            public void stateChanged(CuratorFramework c, ConnectionState newState) {
                if (newState == ConnectionState.SUSPENDED || newState == ConnectionState.LOST) {
                    lockLost = true;
                    if (tListenerLost < 0) tListenerLost = now();
                    out("LISTENER state=" + newState + " t=" + now());
                }
            }
        });
        client.start();
        client.blockUntilConnected();

        InterProcessMutex lock = new InterProcessMutex(client, lockpath);
        lock.acquire();
        long token = extractToken(lock);

        if (role.equals("A")) {
            out("A_ACQUIRED pid=" + pid + " token=" + token + " t=" + now());
            // Barrier: spin until the driver creates --gofile (it does so only AFTER
            // resuming A, i.e. after A's session has already expired and B acquired).
            if (!gofile.isEmpty()) {
                while (!Files.exists(Paths.get(gofile))) {
                    Thread.sleep(15);
                }
            }
            boolean lost = lockLost;                 // sample the documented flag
            long tw = now();
            out("A_PREWRITE lockLost=" + lost + " token=" + token + " t=" + tw);
            if (!lost) {
                String reply = resourceWrite(id, token, value);   // write IMMEDIATELY
                out("A_WROTE token=" + token + " reply=\"" + reply + "\" t=" + now());
            } else {
                out("A_SKIPPED_lockLost token=" + token + " t=" + now());
            }
            out("A_DONE lockLostFinal=" + lockLost + " tListenerLost=" + tListenerLost);
        } else { // role B
            out("B_ACQUIRED pid=" + pid + " token=" + token + " t=" + now());
            String reply = resourceWrite(id, token, value);        // register B's token first
            out("B_WROTE token=" + token + " reply=\"" + reply + "\" t=" + now());
            if (!holdfile.isEmpty()) {
                while (!Files.exists(Paths.get(holdfile))) {
                    Thread.sleep(50);
                }
            }
            try { lock.release(); } catch (Exception e) { /* session may be gone */ }
        }

        try { client.close(); } catch (Exception e) { }
    }

    // ---- fencing token = sequence number of this holder's ephemeral lock node ----
    static long extractToken(InterProcessMutex lock) {
        try {
            Field td = InterProcessMutex.class.getDeclaredField("threadData");
            td.setAccessible(true);
            Map<?, ?> map = (Map<?, ?>) td.get(lock);
            Object lockData = map.get(Thread.currentThread());
            if (lockData != null) {
                Field lp = lockData.getClass().getDeclaredField("lockPath");
                lp.setAccessible(true);
                return seqOf((String) lp.get(lockData));
            }
        } catch (Exception e) { /* fall through to participant-node fallback */ }
        try {
            List<String> parts = new ArrayList<>(lock.getParticipantNodes());
            Collections.sort(parts);                 // holder = lowest sequence
            if (!parts.isEmpty()) return seqOf(parts.get(0));
        } catch (Exception e) { }
        return -1;
    }

    static long seqOf(String path) {
        Matcher m = Pattern.compile("(\\d+)$").matcher(path);
        return m.find() ? Long.parseLong(m.group(1)) : -1;
    }

    // ---- external resource write (plain socket; does NOT consult ZK) ----
    static String resourceWrite(String clientId, long token, String val) {
        String[] hp = resource.split(":");
        try (Socket s = new Socket()) {
            s.connect(new InetSocketAddress(hp[0], Integer.parseInt(hp[1])), 3000);
            OutputStream o = s.getOutputStream();
            o.write(("WRITE " + clientId + " " + token + " " + val + "\n").getBytes(StandardCharsets.UTF_8));
            o.flush();
            BufferedReader r = new BufferedReader(new InputStreamReader(s.getInputStream(), StandardCharsets.UTF_8));
            String line = r.readLine();
            return line == null ? "(no reply)" : line;
        } catch (Exception e) {
            return "(resource error: " + e.getClass().getSimpleName() + " " + e.getMessage() + ")";
        }
    }

    static long now() { return System.currentTimeMillis(); }
    static void out(String s) { System.out.println(s); System.out.flush(); }

    static void parse(String[] a) {
        for (int i = 0; i < a.length - 1; i += 2) {
            switch (a[i]) {
                case "--role": role = a[i + 1]; break;
                case "--id": id = a[i + 1]; break;
                case "--zk": zk = a[i + 1]; break;
                case "--lockpath": lockpath = a[i + 1]; break;
                case "--resource": resource = a[i + 1]; break;
                case "--session": session = Integer.parseInt(a[i + 1]); break;
                case "--value": value = a[i + 1]; break;
                case "--gofile": gofile = a[i + 1]; break;
                case "--holdfile": holdfile = a[i + 1]; break;
            }
        }
    }
}
