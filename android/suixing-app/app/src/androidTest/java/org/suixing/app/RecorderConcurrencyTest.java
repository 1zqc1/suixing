package org.suixing.app;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.location.Criteria;
import android.location.LocationManager;
import android.os.Build;
import android.os.SystemClock;
import android.test.InstrumentationTestCase;
import android.view.View;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Device integration tests. Run the GPS cases on an emulator with precise permission and GPS enabled. */
public class RecorderConcurrencyTest extends InstrumentationTestCase {
    private Instrumentation device;
    private Context context;
    private TrackApp app;
    private Activity screen;
    private final List<TrackApp.Run> testRuns = new ArrayList<>();
    private boolean originalDecision, originalConsent;

    @Override protected void setUp() throws Exception {
        super.setUp();
        device = getInstrumentation();
        context = device.getTargetContext();
        app = (TrackApp) context.getApplicationContext();
        awaitMain(() -> app.ready);
        onMain(() -> {
            originalDecision = app.decided; originalConsent = app.consent;
            assertNull("Tests require an idle app", app.active);
            app.decided = true;
        });
    }

    @Override protected void tearDown() throws Exception {
        try {
            onMain(() -> {
                if (testRuns.contains(app.active) && app.active != null) app.stop("测试结束", false);
                if (screen != null) screen.finish();
                app.consent = originalConsent; app.decided = originalDecision;
            });
            awaitMain(() -> app.active == null);
            try (TrackStore database = new TrackStore(context, "tracks.db")) {
                for (TrackApp.Run run : testRuns) {
                    String[] id = {String.valueOf(run.id)};
                    database.getWritableDatabase().delete("points", "session_id=?", id);
                    database.getWritableDatabase().delete("sessions", "id=?", id);
                }
            }
        } finally { super.tearDown(); }
    }

    public void testBlockedDocumentWriteAllowsNewSessionAndPointToCommit() throws Exception {
        TrackApp.Run previous = startDemo();
        awaitMain(() -> app.frame.count > 0);
        onMain(() -> app.stop("测试记录", false));
        awaitMain(() -> app.active == null);
        CountDownLatch insideWrite = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ByteArrayOutputStream destination = new ByteArrayOutputStream() {
            @Override public synchronized void write(byte[] data, int offset, int length) {
                insideWrite.countDown();
                try {
                    if (!release.await(15, TimeUnit.SECONDS)) throw new IllegalStateException("write timed out");
                } catch (InterruptedException e) { throw new AssertionError(e); }
                super.write(data, offset, length);
            }
        };
        try {
            app.export(previous.id, () -> destination);
            assertTrue("Writer did not start", insideWrite.await(5, TimeUnit.SECONDS));
            TrackApp.Run next = startDemo();
            awaitMain(() -> app.frame.count > 0);
            try (TrackStore reader = new TrackStore(context, "tracks.db")) {
                assertFalse("Expected a durable point while output is blocked", reader.points(next.id).isEmpty());
            }
        } finally { release.countDown(); }
    }

    public void testCancelBeforeServiceCallback() throws Exception {
        openPhone();
        onMain(() -> {
            startPhoneClick();
            click("结束记录");
        });
        awaitMain(() -> app.active == null);
        assertSavedSession("SAVED", 0);
        device.waitForIdleSync();
    }

    public void testSchematicFitsWholeTrackAndHasNoToggleAfterMultiplePoints() throws Exception {
        onMain(() -> app.consent = false);
        screen = device.startActivitySync(new Intent(context, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        device.waitForIdleSync();
        onMain(() -> {
            click("模拟轨迹");
            click("开始记录");
            assertNotNull("Expected a demo session to start", app.active);
            assertEquals(TrackApp.DEMO, app.active.source);
            testRuns.add(app.active);
        });
        awaitMain(() -> app.frame.count >= 2);
        onMain(() -> {
            ArrayList<View> matches = new ArrayList<>();
            screen.getWindow().getDecorView().findViewsWithText(matches, "轨迹示意 · 自动显示全程",
                    View.FIND_VIEWS_WITH_CONTENT_DESCRIPTION);
            assertEquals(1, matches.size());
            assertFalse(matches.get(0).isEnabled());
        });
    }

    public void testGpsDisabledBetweenStartAndServiceCallback() throws Exception {
        assertTrue("GPS test-provider case is emulator-only",
                "ranchu".equals(Build.HARDWARE) || "goldfish".equals(Build.HARDWARE));
        LocationManager manager = (LocationManager) context.getSystemService(Context.LOCATION_SERVICE);
        String gps = LocationManager.GPS_PROVIDER;
        manager.addTestProvider(gps, false, true, false, false, true, true, true,
                Criteria.POWER_LOW, Criteria.ACCURACY_FINE);
        try {
            manager.setTestProviderEnabled(gps, true);
            openPhone();
            onMain(() -> {
                startPhoneClick();
                manager.setTestProviderEnabled(gps, false);
                assertFalse(PhoneService.gpsOn(context));
            });
            awaitMain(() -> app.active == null);
            assertSavedSession("INTERRUPTED", 0);
        } finally {
            manager.removeTestProvider(gps);
        }
    }

    private void assertSavedSession(String status, int count) {
        try (TrackStore reader = new TrackStore(context, "tracks.db")) {
            TrackStore.Session item = reader.history().get(0);
            assertEquals(testRuns.get(0).id, item.id);
            assertEquals(status, item.status);
            assertEquals(count, item.count);
        }
    }
    private TrackApp.Run startDemo() {
        onMain(() -> testRuns.add(app.begin(TrackApp.DEMO)));
        return testRuns.get(testRuns.size() - 1);
    }
    private void openPhone() throws Exception {
        assertTrue("Grant precise location to the test install", PhoneService.precise(context));
        assertTrue("Enable emulator GPS before this case", PhoneService.gpsOn(context));
        onMain(() -> app.consent = true);
        Intent intent = new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        screen = device.startActivitySync(intent);
        device.waitForIdleSync();
        onMain(() -> click("手机 GPS"));
    }
    private void startPhoneClick() {
        click("开始记录");
        assertTrue("Expected an accepted service start", app.phoneActive());
        testRuns.add(app.active);
    }
    private void click(String caption) {
        ArrayList<View> matches = new ArrayList<>();
        screen.getWindow().getDecorView().findViewsWithText(matches, caption, View.FIND_VIEWS_WITH_TEXT);
        for (View view : matches) {
            if (view.isEnabled() && caption.contentEquals(view.getContentDescription() == null
                    ? "" : view.getContentDescription())) {
                view.performClick();
                return;
            }
        }
        fail("Clickable control missing: " + caption);
    }
    private interface MainCheck { boolean get(); }
    private void awaitMain(MainCheck check) {
        long end = SystemClock.elapsedRealtime() + 4500;
        AtomicBoolean result = new AtomicBoolean();
        do {
            onMain(() -> result.set(check.get()));
            if (result.get()) return;
            SystemClock.sleep(25);
        } while (SystemClock.elapsedRealtime() < end);
        fail("Timed out waiting for recorder progress");
    }
    private void onMain(Runnable runnable) {
        // Let assertions return to the test runner instead of escaping the main looper.
        Throwable[] thrown = new Throwable[1];
        device.runOnMainSync(() -> {
            try { runnable.run(); } catch (Throwable error) { thrown[0] = error; }
        });
        if (thrown[0] != null) throw new AssertionError(thrown[0]);
    }
}
