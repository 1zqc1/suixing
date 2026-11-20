package org.suixing.app;

import org.junit.Test;
import org.suixing.app.core.LocationFix;
import org.suixing.app.core.TrackPoint;
import java.util.ArrayList;
import java.util.List;
import static org.junit.Assert.*;

public class HistoryPreviewTest {
    @Test public void boundedHistoryPrefixIncludesCurrentAndEveryVisibleSegmentEndpoint() {
        List<TrackPoint> full = new ArrayList<>();
        for (int i = 0; i < 18001; i++) {
            int segment = i < 6001 ? 0 : i < 6012 ? 1 : 2;
            full.add(new TrackPoint(i + 1, segment, new LocationFix(i, i, 1, 1, 3, "DEMO")));
        }
        TrackApp.Saved saved = new TrackApp.Saved(full);
        for (int count : new int[]{0, 1, 6000, 6001, 6002, 6012, 6013, 17990, 18001}) {
            List<TrackPoint> prefix = saved.preview(count);
            assertTrue(prefix.size() <= 1501);
            if (count == 0) { assertTrue(prefix.isEmpty()); continue; }
            assertSame(full.get(count - 1), prefix.get(prefix.size() - 1));
            for (int endpoint : new int[]{0, 6000, 6001, 6011, 6012}) {
                if (endpoint < count) assertTrue(prefix.contains(full.get(endpoint)));
            }
        }
        assertEquals(18001, full.size());
    }
}
