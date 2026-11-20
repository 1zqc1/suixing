package org.suixing.app.core;

import java.util.List;

/** Computes metrics for accepted points in sequence order. */
public final class TrackMetrics {
    private static final double EARTH_RADIUS_METERS = 6_371_000;

    private TrackMetrics() {}

    public static double distanceMeters(List<TrackPoint> points) {
        double totalMeters = 0;
        TrackPoint previous = null;
        for (TrackPoint point : points) {
            if (previous != null && previous.segment == point.segment) {
                totalMeters += haversineMeters(previous.fix.latitude, previous.fix.longitude,
                        point.fix.latitude, point.fix.longitude);
            }
            previous = point;
        }
        return totalMeters;
    }

    public static long durationMillis(List<TrackPoint> points) {
        if (points.size() < 2) {
            return 0;
        }
        return points.get(points.size() - 1).fix.elapsedMillis - points.get(0).fix.elapsedMillis;
    }

    public static double haversineMeters(double firstLatitude, double firstLongitude,
                                         double lastLatitude, double lastLongitude) {
        double firstLatitudeRadians = Math.toRadians(firstLatitude);
        double lastLatitudeRadians = Math.toRadians(lastLatitude);
        double latitudeHalfSine = Math.sin((lastLatitudeRadians - firstLatitudeRadians) / 2);
        double longitudeHalfSine = Math.sin(Math.toRadians(lastLongitude - firstLongitude) / 2);
        double haversine = latitudeHalfSine * latitudeHalfSine
                + Math.cos(firstLatitudeRadians) * Math.cos(lastLatitudeRadians)
                * longitudeHalfSine * longitudeHalfSine;
        return 2 * EARTH_RADIUS_METERS * Math.asin(Math.sqrt(Math.min(1, haversine)));
    }
}
