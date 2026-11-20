package org.suixing.app.map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;
import org.suixing.app.core.LocationFix;
import org.suixing.app.core.TrackPoint;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class TrackRenderGeometryTest {
    @Test public void samplingPreservesEverySegmentEndpointWithinBudget() {
        List<TrackPoint> track = new ArrayList<>();
        for (int i = 0; i < 200; i++) {
            track.add(point(i, i < 100 ? 0 : 1, 39, 116 + i * 0.001));
        }

        List<List<TrackPoint>> segments = TrackRenderGeometry.sample(track, 10);

        assertEquals(2, segments.size());
        assertEquals(10, segments.get(0).size() + segments.get(1).size());
        assertEquals(track.get(0), segments.get(0).get(0));
        assertEquals(track.get(99), segments.get(0).get(segments.get(0).size() - 1));
        assertEquals(track.get(100), segments.get(1).get(0));
        assertEquals(track.get(199), segments.get(1).get(segments.get(1).size() - 1));
        assertEquals(200, track.size());
    }

    @Test public void singletonSegmentRemainsWhenEndpointsConsumeBudget() {
        TrackPoint first = point(0, 0, 39, 116);
        TrackPoint middle = point(1, 0, 39, 116.001);
        TrackPoint last = point(2, 0, 39, 116.002);
        TrackPoint isolated = point(3, 1, 39, 116.01);

        List<List<TrackPoint>> segments = TrackRenderGeometry.sample(
                Arrays.asList(first, middle, last, isolated), 2);

        assertEquals(Arrays.asList(Arrays.asList(first, last), Arrays.asList(isolated)), segments);
    }

    @Test public void schematicPreservesOrientationAndKeepsCurrentInView() {
        TrackPoint southwest = point(0, 0, 60, 116);
        TrackPoint northeast = point(1, 0, 60.01, 116.01);
        TrackPoint current = point(2, 0, 60.02, 116.02);
        List<List<TrackPoint>> segments = Arrays.asList(Arrays.asList(southwest, northeast));

        TrackRenderGeometry.Projection projection =
                TrackRenderGeometry.Projection.fit(segments, current, 300, 300);

        double east = projection.x(northeast) - projection.x(southwest);
        double north = projection.y(southwest) - projection.y(northeast);
        assertTrue(east > 0);
        assertTrue(north > 0);
        assertEquals(0.5, east / north, 0.001);
        assertTrue(projection.x(current) <= 300.001);
        assertTrue(projection.y(current) >= -0.001);
    }

    @Test public void schematicCrossesDateLineWithoutWrappingAcrossTheWorld() {
        TrackPoint west = point(0, 0, 0, 179.999);
        TrackPoint east = point(1, 0, 0, -179.999);
        List<List<TrackPoint>> segments = Arrays.asList(Arrays.asList(west, east));

        TrackRenderGeometry.Projection projection =
                TrackRenderGeometry.Projection.fit(segments, null, 200, 100);

        assertEquals(200, projection.x(east) - projection.x(west), 0.001);
        assertEquals(50, projection.y(west), 0.001);
    }

    private static TrackPoint point(long sequence, int segment, double lat, double lon) {
        return new TrackPoint(sequence, segment,
                new LocationFix(sequence, sequence, lat, lon, 4, "test"));
    }
}
