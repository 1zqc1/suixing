package org.suixing.app;

import android.content.Context;
import android.test.InstrumentationTestCase;
import org.suixing.app.core.LocationFix;
import org.suixing.app.core.TrackPoint;
import java.util.List;

public class TrackStoreTest extends InstrumentationTestCase {
    private Context context;
    private TrackStore store;
    private String name;

    @Override protected void setUp() throws Exception {
        super.setUp();
        context = getInstrumentation().getTargetContext();
        name = "track-test-" + System.nanoTime() + ".db";
        store = new TrackStore(context, name);
    }

    @Override protected void tearDown() throws Exception {
        store.close();
        context.deleteDatabase(name);
        super.tearDown();
    }

    public void testOrderedRoundTripAndFinishedSessionSurvivesRecovery() {
        long id = store.begin("PHONE_GPS", 1000);
        store.append(id, new TrackPoint(2, 1,
                new LocationFix(800, 24000, 31.12, 121.2, 3.25, "PHONE_GPS_MOCK")));
        store.append(id, new TrackPoint(1, 0,
                new LocationFix(1000, 1000, 31.1, 121.2, 4, "PHONE_GPS")));
        store.finish(id, "SAVED", 900);
        store.close();
        store = new TrackStore(context, name);
        store.recover();
        List<TrackPoint> points = store.points(id);
        assertEquals(2, points.size());
        assertEquals(1L, points.get(0).sequence);
        TrackPoint last = points.get(1);
        assertEquals(2L, last.sequence);
        assertEquals(1, last.segment);
        assertEquals(800L, last.fix.epochMillis);
        assertEquals(24000L, last.fix.elapsedMillis);
        assertEquals(31.12, last.fix.latitude, 0);
        assertEquals(121.2, last.fix.longitude, 0);
        assertEquals(3.25, last.fix.accuracyMeters, 0);
        assertEquals("PHONE_GPS_MOCK", last.fix.source);
        TrackStore.Session session = store.history().get(0);
        assertEquals("PHONE_GPS", session.source);
        assertEquals("SAVED", session.status);
        assertEquals(900L, session.ended.longValue());
        assertEquals(2, session.count);
        assertTrue(session.mock);
    }

    public void testAbruptExitRecoversEvenEmptySessionsWithoutInventingEndTime() {
        long first = store.begin("DEMO", 2000);
        store.append(first, new TrackPoint(1, 0, new LocationFix(2000, 30, 0, 0, 3, "DEMO")));
        long empty = store.begin("PHONE_GPS", 3000);
        assertTrue(store.history().isEmpty());
        store.close();
        store = new TrackStore(context, name);
        store.recover();
        store.recover();
        List<TrackStore.Session> history = store.history();
        assertEquals(2, history.size());
        assertEquals(empty, history.get(0).id);
        assertEquals(0, history.get(0).count);
        assertNull(history.get(0).ended);
        assertEquals("INTERRUPTED", history.get(1).status);
        assertEquals(1, store.points(first).size());
    }
}
