package org.suixing.app.core;

/** An accepted sample with its position in the track. */
public final class TrackPoint {
    public final long sequence;
    public final int segment;
    public final LocationFix fix;

    public TrackPoint(long sequence, int segment, LocationFix fix) {
        this.sequence = sequence;
        this.segment = segment;
        this.fix = fix;
    }
}
