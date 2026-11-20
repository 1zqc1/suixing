package org.suixing.app.core;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertSame;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class TrackFilterTest {
    private final TrackFilter filter = new TrackFilter();

    @Test
    public void acceptsDemoPathInFirstSegment() {
        assertPoint(1, 0, new LocationFix(1_760_000_001_000L, 1_000, 30.5, 114.3, 3, "DEMO"));
        assertPoint(2, 0, new LocationFix(1_760_000_002_000L, 2_000, 30.5, 114.300021, 3, "DEMO"));
        assertPoint(3, 0, new LocationFix(1_760_000_003_000L, 3_000, 30.5, 114.300042, 3, "DEMO"));
    }

    @Test
    public void rejectsInvalidCoordinatesAndAccuracy() {
        double[][] inputs = {
                {Double.NaN, 0, 1}, {0, Double.NaN, 1}, {90.1, 0, 1}, {-90.1, 0, 1},
                {0, 180.1, 1}, {0, -180.1, 1}, {Double.POSITIVE_INFINITY, 0, 1},
                {0, Double.NEGATIVE_INFINITY, 1}, {0, 0, 0}, {0, 0, -1},
                {0, 0, Double.NaN}, {0, 0, Double.POSITIVE_INFINITY}
        };
        for (double[] input : inputs) {
            LocationFix invalid = new LocationFix(0, 1_000, input[0], input[1], input[2], "GPS");
            assertRejected(TrackFilter.Status.INVALID, filter.evaluate(invalid, 1_000));
        }
        assertRejected(TrackFilter.Status.INVALID, filter.evaluate(null, 1_000));

        assertPoint(1, 0, new LocationFix(0, 1_000, 90, -180, 1, "GPS"));
    }

    @Test
    public void enforcesAccuracyLimitWithoutAdvancingBaseline() {
        assertRejected(TrackFilter.Status.INACCURATE, filter.evaluate(fix(1_001, 0, 80.01), 1_001));
        assertPoint(1, 0, fix(1_000, 0, 80));
    }

    @Test
    public void acceptsOnlyFixesWithinMonotonicFreshnessWindow() {
        assertRejected(TrackFilter.Status.STALE, filter.evaluate(fix(999, 0, 1), 16_000));
        assertRejected(TrackFilter.Status.STALE, filter.evaluate(fix(17_001, 0, 1), 16_000));

        assertTrue(filter.evaluate(fix(1_000, 0, 1), 16_000).isAccepted());
        assertTrue(filter.evaluate(fix(17_000, 0.0001, 1), 16_000).isAccepted());
    }

    @Test
    public void rejectsDuplicateAndOlderElapsedTimesDespiteNewerEpoch() {
        assertPoint(1, 0, fix(2_000, 0, 1));
        assertRejected(TrackFilter.Status.OUT_OF_ORDER,
                filter.evaluate(new LocationFix(60_000, 2_000, 0, 0.0001, 1, "GPS"), 2_000));
        assertRejected(TrackFilter.Status.OUT_OF_ORDER,
                filter.evaluate(new LocationFix(61_000, 1_999, 0, 0.0001, 1, "GPS"), 2_000));
        assertPoint(2, 0, fix(2_001, 0.0001, 1));
    }

    @Test
    public void recoversAfterJumpUsingLastAcceptedTimestampAndPosition() {
        assertPoint(1, 0, fix(1_000, 0, 1));
        assertRejected(TrackFilter.Status.JUMP, filter.evaluate(fix(6_000, 0.0006, 1), 6_000));
        assertPoint(2, 0, fix(5_999, 0.0005, 1));
    }

    @Test
    public void accountsForBothAccuracyEstimatesInJumpLimit() {
        assertPoint(1, 0, fix(1_000, 0, 4));
        assertRejected(TrackFilter.Status.JUMP, filter.evaluate(fix(2_000, 0.00037, 6), 2_000));
        assertPoint(2, 0, fix(2_000, 0.00035, 6));
    }

    @Test
    public void opensNewSegmentOnlyAfterGapExceedsTwentySeconds() {
        assertPoint(1, 0, fix(1_000, 0, 1));
        assertRejected(TrackFilter.Status.JUMP, filter.evaluate(fix(21_000, 2, 1), 21_000));
        assertPoint(2, 1, fix(21_001, 2, 1));
        assertPoint(3, 1, fix(22_001, 2.0001, 1));
    }

    @Test
    public void rejectsJitterUsingMinimumAndAccuracyScaledThresholds() {
        assertPoint(1, 0, fix(1_000, 0, 1));
        assertRejected(TrackFilter.Status.NO_MOVEMENT, filter.evaluate(fix(2_000, 0.00001, 1), 2_000));
        assertRejected(TrackFilter.Status.NO_MOVEMENT, filter.evaluate(fix(2_000, 0.00002, 10), 2_000));
        assertPoint(2, 0, fix(2_000, 0.00003, 10));
    }

    @Test
    public void resetStartsSequenceAndSegmentFromBeginning() {
        assertPoint(1, 0, fix(1_000, 0, 1));
        assertPoint(2, 1, fix(21_001, 2, 1));

        filter.reset();

        assertPoint(1, 0, fix(1_000, 3, 1));
    }

    private void assertPoint(long sequence, int segment, LocationFix fix) {
        TrackFilter.Result result = filter.evaluate(fix, fix.elapsedMillis);
        assertEquals(TrackFilter.Status.ACCEPTED, result.status);
        assertTrue(result.isAccepted());
        assertNotNull(result.point);
        assertEquals(sequence, result.point.sequence);
        assertEquals(segment, result.point.segment);
        assertSame(fix, result.point.fix);
    }

    private static void assertRejected(TrackFilter.Status status, TrackFilter.Result result) {
        assertEquals(status, result.status);
        assertFalse(result.isAccepted());
        assertNull(result.point);
        assertNotNull(result.reason);
        assertFalse(result.reason.isEmpty());
    }

    private static LocationFix fix(long elapsedMillis, double longitude, double accuracyMeters) {
        return new LocationFix(1_760_000_000_000L + elapsedMillis, elapsedMillis, 0, longitude,
                accuracyMeters, "GPS");
    }
}
