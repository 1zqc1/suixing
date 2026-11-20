package org.suixing.app;

import android.app.Application;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import org.suixing.app.core.LocationFix;
import org.suixing.app.core.TrackFilter;
import org.suixing.app.core.TrackMetrics;
import org.suixing.app.core.TrackPoint;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class TrackApp extends Application {
    static final String DEMO = "DEMO", PHONE = "PHONE_GPS";
    final Handler main = new Handler(Looper.getMainLooper());
    private final ScheduledThreadPoolExecutor io = new ScheduledThreadPoolExecutor(1);
    private final ExecutorService documentIo = Executors.newSingleThreadExecutor();
    private TrackStore store;
    private SharedPreferences preferences;
    private final List<double[]> demo = new ArrayList<>();

    // UI state and transitions are main-thread owned.
    boolean ready, consent, decided, savingConsent, finishing;
    Run active;
    Frame frame = Frame.empty();
    String message = "正在读取本地记录";
    Runnable listener;

    static final class Run {
        final String source;
        final long startElapsed = SystemClock.elapsedRealtime();
        // Everything below is worker-owned.
        long id, callback = -1, fresh = -1;
        int count, demoIndex;
        boolean failed;
        double distance, accuracy = Double.NaN;
        TrackPoint first, last;
        final TrackFilter filter = new TrackFilter();
        final ArrayList<TrackPoint> preview = new ArrayList<>();
        List<TrackPoint> published = Collections.emptyList();
        ScheduledFuture<?> timer;
        Run(String source) { this.source = source; }
    }

    static final class Frame {
        final List<TrackPoint> points;
        final int count;
        final long duration, callback, fresh;
        final double distance, accuracy;
        final String status, source;
        Frame(List<TrackPoint> points, int count, long duration, double distance, double accuracy,
              long callback, long fresh, String status, String source) {
            this.points = points; this.count = count; this.duration = duration; this.distance = distance;
            this.accuracy = accuracy; this.callback = callback; this.fresh = fresh;
            this.status = status; this.source = source;
        }
        static Frame empty() {
            return new Frame(Collections.emptyList(), 0, 0, 0, Double.NaN, -1, -1, "", "");
        }
    }
    void changed() { if (listener != null) listener.run(); }

    @Override public void onCreate() {
        super.onCreate();
        io.setRemoveOnCancelPolicy(true);
        io.execute(() -> {
            try {
                preferences = getSharedPreferences("privacy", MODE_PRIVATE);
                boolean chosen = preferences.contains("agreed");
                boolean agreed = preferences.getBoolean("agreed", false);
                store = new TrackStore(this, "tracks.db");
                store.recover();
                try (BufferedReader input = new BufferedReader(new InputStreamReader(
                        getAssets().open("demo-track.csv"), StandardCharsets.UTF_8))) {
                    input.readLine();
                    String line;
                    while ((line = input.readLine()) != null) {
                        String[] fields = line.split(",");
                        demo.add(new double[]{Double.parseDouble(fields[0]), Double.parseDouble(fields[1])});
                    }
                }
                if (demo.isEmpty()) throw new IOException("示例轨迹为空");
                main.post(() -> {
                    decided = chosen; consent = agreed; ready = true; message = "准备记录"; changed();
                });
            } catch (IOException | RuntimeException e) {
                main.post(() -> { message = "本地记录初始化失败，请检查存储空间后重启"; changed(); });
            }
        });
    }

    void setConsent(boolean agreed) {
        if (savingConsent || !ready) return;
        savingConsent = true;
        if (!agreed) {
            consent = false;
            if (phoneActive()) stop("已撤回定位授权", false);
        }
        changed();
        io.execute(() -> {
            boolean saved;
            try { saved = preferences.edit().putBoolean("agreed", agreed).commit(); }
            catch (RuntimeException e) { saved = false; }
            final boolean ok = saved;
            main.post(() -> {
                savingConsent = false;
                decided = true;
                consent = agreed && ok;
                message = ok ? (consent ? "已同意隐私设置" : "可使用模拟轨迹和本地历史")
                        : "隐私设置未能保存，本次已关闭定位和联网地图";
                changed();
            });
        });
    }

    boolean phoneActive() { return active != null && PHONE.equals(active.source); }

    Run begin(String source) {
        if (!ready || active != null || (PHONE.equals(source) && (!consent || !PhoneService.precise(this)))) return null;
        Run run = new Run(source);
        active = run; frame = Frame.empty(); message = "正在建立记录"; changed();
        io.execute(() -> {
            try {
                run.id = store.begin(source, System.currentTimeMillis());
                publish(run, DEMO.equals(source) ? "模拟轨迹记录中" : "等待首次 GPS 定位");
                if (DEMO.equals(source)) {
                    run.timer = io.scheduleWithFixedDelay(() -> {
                        double[] coordinate = demo.get(run.demoIndex);
                        run.demoIndex = (run.demoIndex + 1) % demo.size();
                        long elapsed = SystemClock.elapsedRealtime();
                        record(run, new LocationFix(System.currentTimeMillis(), elapsed,
                                coordinate[0], coordinate[1], 3, DEMO), elapsed);
                    }, 0, 1, TimeUnit.SECONDS);
                }
            } catch (RuntimeException e) { fail(run); }
        });
        return run;
    }

    void location(Run run, LocationFix fix, long received) {
        if (run == null || run != active || finishing) return;
        io.execute(() -> record(run, fix, received));
    }
    private void record(Run run, LocationFix fix, long received) {
        if (run.failed) return;
        try {
            run.callback = received;
            run.accuracy = fix.accuracyMeters;
            TrackFilter.Result result = run.filter.evaluate(fix, received);
            String reason = result.reason;
            if (result.isAccepted()) {
                TrackPoint point = result.point;
                store.append(run.id, point);
                if (run.first == null) run.first = point;
                if (run.last != null && run.last.segment == point.segment) {
                    run.distance += TrackMetrics.haversineMeters(run.last.fix.latitude, run.last.fix.longitude,
                            point.fix.latitude, point.fix.longitude);
                }
                run.last = point;
                run.count++;
                run.preview.add(point);
                if (run.preview.size() >= 4000 && run.count % 512 == 0) thinPreview(run.preview);
                run.published = Collections.unmodifiableList(new ArrayList<>(run.preview));
                run.fresh = received;
                reason = DEMO.equals(run.source) ? "正在记录模拟轨迹" : "GPS 定位正常";
            } else if (result.status == TrackFilter.Status.NO_MOVEMENT) {
                run.fresh = received;
                reason = "位置稳定，已忽略定位抖动";
            }
            if (fix.source.endsWith("_MOCK")) reason += " · 系统模拟定位";
            publish(run, reason);
        } catch (RuntimeException e) { fail(run); }
    }

    // Keep the ends of every segment. SQLite always retains the original points.
    private static void thinPreview(ArrayList<TrackPoint> preview) {
        int write = 1;
        int size = preview.size();
        for (int i = 1; i < size - 1; i++) {
            TrackPoint p = preview.get(i);
            if (i % 2 == 0 || p.segment != preview.get(i - 1).segment || p.segment != preview.get(i + 1).segment) {
                preview.set(write++, p);
            }
        }
        preview.set(write++, preview.get(size - 1));
        preview.subList(write, size).clear();
    }

    private void publish(Run run, String reason) {
        long duration = run.last == null ? 0 : run.last.fix.elapsedMillis - run.first.fix.elapsedMillis;
        Frame next = new Frame(run.published, run.count, duration, run.distance, run.accuracy, run.callback,
                run.fresh, reason, run.source);
        main.post(() -> { if (active == run) { frame = next; changed(); } });
    }

    private void fail(Run run) {
        run.failed = true;
        main.post(() -> { if (active == run) stop("本地写入失败", true); });
    }

    void stop(String reason, boolean interrupted) {
        Run run = active;
        if (run == null || finishing) return;
        finishing = true;
        if (PHONE.equals(run.source)) stopService(new Intent(this, PhoneService.class));
        message = "正在结束并保存"; changed();
        io.execute(() -> {
            if (run.timer != null) run.timer.cancel(false);
            String result;
            try {
                if (run.id == 0) throw new IllegalStateException();
                store.finish(run.id, interrupted || run.failed ? "INTERRUPTED" : "SAVED", System.currentTimeMillis());
                result = run.failed ? "本地写入失败，记录已中断，历史仅包含已写入的点"
                        : reason + " · 已保存 " + run.count + " 个点";
            } catch (RuntimeException e) { result = "记录未能完成保存，请检查存储空间并重启查看历史"; }
            final String finalMessage = result;
            main.post(() -> {
                if (active == run) {
                    active = null; finishing = false; message = finalMessage; changed();
                }
            });
        });
    }

    interface Result<T> { void accept(T data, String error); }
    void history(Result<List<TrackStore.Session>> callback) {
        io.execute(() -> {
            try {
                List<TrackStore.Session> sessions = store.history();
                main.post(() -> callback.accept(sessions, null));
            } catch (RuntimeException e) { main.post(() -> callback.accept(null, "读取历史失败")); }
        });
    }

    static final class Saved {
        final List<TrackPoint> points;
        final double[] distances;
        private final List<TrackPoint> previewPoints;
        Saved(List<TrackPoint> points) {
            this.points = points;
            if (points.size() <= 1500) {
                previewPoints = points;
            } else {
                ArrayList<TrackPoint> preview = new ArrayList<>(points);
                while (preview.size() > 1500) {
                    int previousSize = preview.size();
                    thinPreview(preview);
                    if (preview.size() == previousSize) break; // Every remaining point is a segment endpoint.
                }
                previewPoints = Collections.unmodifiableList(preview);
            }
            distances = new double[points.size()];
            for (int i = 1; i < points.size(); i++) {
                TrackPoint prev = points.get(i - 1), cur = points.get(i);
                distances[i] = distances[i - 1];
                if (prev.segment == cur.segment) distances[i] += TrackMetrics.haversineMeters(
                        prev.fix.latitude, prev.fix.longitude, cur.fix.latitude, cur.fix.longitude);
            }
        }

        List<TrackPoint> preview(int shown) {
            if (shown == 0) return Collections.emptyList();
            if (shown == points.size()) return previewPoints;
            TrackPoint current = points.get(shown - 1);
            int index = Collections.binarySearch(previewPoints, current,
                    (left, right) -> Long.compare(left.sequence, right.sequence));
            if (index >= 0) return previewPoints.subList(0, index + 1);
            List<TrackPoint> prefix = new ArrayList<>(previewPoints.subList(0, -index - 1));
            prefix.add(current);
            return prefix;
        }
    }
    void load(long id, Result<Saved> callback) {
        io.execute(() -> {
            try {
                Saved saved = new Saved(store.points(id));
                main.post(() -> callback.accept(saved, null));
            } catch (RuntimeException e) { main.post(() -> callback.accept(null, "读取轨迹点失败")); }
        });
    }

    interface DocumentOutput { OutputStream open() throws IOException; }

    void export(long id, Uri target) {
        export(id, () -> getContentResolver().openOutputStream(target, "wt"));
    }

    void export(long id, DocumentOutput destination) {
        documentIo.execute(() -> {
            String result = "导出失败，请检查文档位置和可用空间";
            try {
                TrackStore.Session selected = null;
                List<TrackPoint> points;
                // Completed sessions are immutable. Release all SQLite cursors and connections
                // before the external provider can block on open, write, flush, or close.
                try (TrackStore reader = new TrackStore(this, "tracks.db")) {
                    for (TrackStore.Session session : reader.history()) {
                        if (session.id == id) { selected = session; break; }
                    }
                    if (selected == null) throw new IOException("找不到记录");
                    points = reader.points(id);
                }
                try (OutputStream stream = destination.open()) {
                    if (stream == null) throw new IOException("无法打开文档");
                    try (BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(stream, StandardCharsets.UTF_8))) {
                        TrackStore.writeJsonl(selected, points, writer);
                    }
                }
                result = "已导出 JSONL · " + selected.count + " 个点";
            } catch (IOException | RuntimeException ignored) { /* Report failure after close as well. */ }
            final String feedback = result;
            main.post(() -> { message = feedback; changed(); });
        });
    }
}
