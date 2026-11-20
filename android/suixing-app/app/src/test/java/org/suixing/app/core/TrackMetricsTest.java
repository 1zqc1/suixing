package org.suixing.app.core;

import static org.junit.Assert.assertEquals;

import java.util.List;

import org.junit.Test;

public class TrackMetricsTest {
    @Test
    public void sumsDistanceOnlyWithinSegments() {
        List<TrackPoint> points = List.of(
                point(1, 0, 0, 1_000, 0),
                point(2, 0, 0, 11_000, 0.001),
                point(3, 1, 0, 35_000, 20),
                point(4, 1, 0, 55_000, 20.002));

        assertEquals(333.585, TrackMetrics.distanceMeters(points), 0.01);
    }

    @Test
    public void durationUsesFirstAndLastElapsedTimeAcrossSegments() {
        List<TrackPoint> points = List.of(
                point(1, 0, 100_000, 1_000, 0),
                point(2, 0, 200_000, 2_500, 0.001),
                point(3, 1, 50_000, 25_000, 20));

        assertEquals(24_000, TrackMetrics.durationMillis(points));
    }

    @Test
    public void emptyAndSingletonTracksHaveZeroMetrics() {
        List<TrackPoint> single = List.of(point(1, 0, 1_000, 500, 114.3));

        assertEquals(0, TrackMetrics.distanceMeters(List.of()), 0);
        assertEquals(0, TrackMetrics.distanceMeters(single), 0);
        assertEquals(0, TrackMetrics.durationMillis(List.of()));
        assertEquals(0, TrackMetrics.durationMillis(single));
    }

    @Test
    public void haversineUsesShortArcAcrossAntimeridian() {
        assertEquals(2_223.90, TrackMetrics.haversineMeters(0, 179.99, 0, -179.99), 0.02);
    }

    private static TrackPoint point(long sequence, int segment, long epochMillis, long elapsedMillis,
                                    double longitude) {
        return new TrackPoint(sequence, segment,
                new LocationFix(epochMillis, elapsedMillis, 0, longitude, 1, "DEMO"));
    }
}
