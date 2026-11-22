package org.suixing.app.map;

import org.suixing.app.core.TrackPoint;

import java.util.ArrayList;
import java.util.List;
import java.util.RandomAccess;

final class TrackRenderGeometry {
    private TrackRenderGeometry() { }

    /** Only interior samples are dropped to meet the budget. */
    static List<List<TrackPoint>> sample(List<TrackPoint> track, int budget) {
        List<TrackPoint> points = track instanceof RandomAccess ? track : new ArrayList<>(track);
        List<Integer> ends = new ArrayList<>();
        int mandatory = 0;
        int start = 0;
        for (int i = 1; i <= points.size(); i++) {
            if (i == points.size() || points.get(i).segment != points.get(i - 1).segment) {
                ends.add(i);
                mandatory += Math.min(2, i - start);
                start = i;
            }
        }

        List<List<TrackPoint>> segments = new ArrayList<>(ends.size());
        int totalInterior = points.size() - mandatory;
        int available = Math.min(totalInterior, Math.max(0, budget - mandatory));
        int interiorSeen = 0;
        int interiorAllocated = 0;
        start = 0;
        for (int end : ends) {
            int size = end - start;
            interiorSeen += Math.max(0, size - 2);
            int allocatedSoFar = totalInterior == 0 ? 0
                    : (int) ((long) available * interiorSeen / totalInterior);
            int count = Math.min(2, size) + allocatedSoFar - interiorAllocated;
            List<TrackPoint> segment = new ArrayList<>(count);
            segment.add(points.get(start));
            for (int i = 1; i < count; i++) {
                int index = start + (int) ((long) i * (size - 1) / (count - 1));
                segment.add(points.get(index));
            }
            segments.add(segment);
            interiorAllocated = allocatedSoFar;
            start = end;
        }
        return segments;
    }

    /** A local north-up approximation over the accepted WGS84 points. */
    static final class Projection {
        private static final double MIN_SPAN_DEGREES = 0.00015;

        private final double referenceLongitude;
        private final double longitudeScale;
        private final double centerX;
        private final double centerLatitude;
        private final double pixelsPerDegree;
        private final double halfWidth;
        private final double halfHeight;

        private Projection(double referenceLongitude, double longitudeScale,
                           double centerX, double centerLatitude, double pixelsPerDegree,
                           double width, double height) {
            this.referenceLongitude = referenceLongitude;
            this.longitudeScale = longitudeScale;
            this.centerX = centerX;
            this.centerLatitude = centerLatitude;
            this.pixelsPerDegree = pixelsPerDegree;
            this.halfWidth = width / 2;
            this.halfHeight = height / 2;
        }

        static Projection fit(List<List<TrackPoint>> segments, TrackPoint current,
                              double width, double height) {
            TrackPoint anchor = segments.isEmpty() ? current : segments.get(0).get(0);
            if (anchor == null) {
                return new Projection(0, 1, 0, 0, 0, width, height);
            }
            double longitude = anchor.fix.longitude;
            double minX = current == null ? 0 : Math.min(0, longitudeDelta(current, longitude));
            double maxX = current == null ? 0 : Math.max(0, longitudeDelta(current, longitude));
            double minLat = current == null ? anchor.fix.latitude
                    : Math.min(anchor.fix.latitude, current.fix.latitude);
            double maxLat = current == null ? anchor.fix.latitude
                    : Math.max(anchor.fix.latitude, current.fix.latitude);
            for (List<TrackPoint> segment : segments) {
                for (TrackPoint point : segment) {
                    double x = longitudeDelta(point, longitude);
                    minX = Math.min(minX, x);
                    maxX = Math.max(maxX, x);
                    minLat = Math.min(minLat, point.fix.latitude);
                    maxLat = Math.max(maxLat, point.fix.latitude);
                }
            }

            double centerLatitude = (minLat + maxLat) / 2;
            double longitudeScale = Math.cos(Math.toRadians(centerLatitude));
            double xSpan = Math.max(MIN_SPAN_DEGREES, (maxX - minX) * longitudeScale);
            double ySpan = Math.max(MIN_SPAN_DEGREES, maxLat - minLat);
            return new Projection(longitude, longitudeScale, (minX + maxX) / 2 * longitudeScale,
                    centerLatitude, Math.min(width / xSpan, height / ySpan), width, height);
        }

        double x(TrackPoint point) {
            double east = longitudeDelta(point, referenceLongitude) * longitudeScale;
            return halfWidth + (east - centerX) * pixelsPerDegree;
        }

        double y(TrackPoint point) {
            return halfHeight - (point.fix.latitude - centerLatitude) * pixelsPerDegree;
        }

        private static double longitudeDelta(TrackPoint point, double referenceLongitude) {
            return Math.IEEEremainder(point.fix.longitude - referenceLongitude, 360);
        }
    }
}
