package org.suixing.app.core;

/** A WGS84 location sample with wall-clock and monotonic timestamps. */
public final class LocationFix {
    public final long epochMillis;
    public final long elapsedMillis;
    public final double latitude;
    public final double longitude;
    public final double accuracyMeters;
    public final String source;

    public LocationFix(long epochMillis, long elapsedMillis, double latitude, double longitude,
                       double accuracyMeters, String source) {
        this.epochMillis = epochMillis;
        this.elapsedMillis = elapsedMillis;
        this.latitude = latitude;
        this.longitude = longitude;
        this.accuracyMeters = accuracyMeters;
        this.source = source;
    }
}
