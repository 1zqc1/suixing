package org.suixing.app.core;

/** Applies the fix quality and motion rules to one recording. */
public final class TrackFilter {
    private static final double MAX_ACCURACY_METERS = 80;
    private static final long MAX_AGE_MILLIS = 15_000;
    private static final long MAX_FUTURE_MILLIS = 1_000;
    private static final long SEGMENT_GAP_MILLIS = 20_000;
    private static final double MAX_SPEED_METERS_PER_SECOND = 12;

    public enum Status { ACCEPTED, INVALID, INACCURATE, STALE, OUT_OF_ORDER, JUMP, NO_MOVEMENT }

    public static final class Result {
        public final Status status;
        public final TrackPoint point;
        public final String reason;

        private Result(Status status, TrackPoint point, String reason) {
            this.status = status;
            this.point = point;
            this.reason = reason;
        }

        public boolean isAccepted() {
            return status == Status.ACCEPTED;
        }
    }

    private TrackPoint lastAccepted;

    public Result evaluate(LocationFix fix, long nowElapsedMillis) {
        if (!isValid(fix)) {
            return new Result(Status.INVALID, null, "定位坐标或精度无效");
        }
        if (fix.accuracyMeters > MAX_ACCURACY_METERS) {
            return new Result(Status.INACCURATE, null, "定位精度低于要求");
        }
        if (exceedsInterval(nowElapsedMillis, fix.elapsedMillis, MAX_AGE_MILLIS)) {
            return new Result(Status.STALE, null, "定位已过期");
        }
        if (exceedsInterval(fix.elapsedMillis, nowElapsedMillis, MAX_FUTURE_MILLIS)) {
            return new Result(Status.STALE, null, "定位时间超前");
        }
        if (lastAccepted == null) {
            return accept(fix, 0);
        }

        LocationFix previous = lastAccepted.fix;
        if (fix.elapsedMillis <= previous.elapsedMillis) {
            return new Result(Status.OUT_OF_ORDER, null, "定位时间重复或倒序");
        }
        if (exceedsInterval(fix.elapsedMillis, previous.elapsedMillis, SEGMENT_GAP_MILLIS)) {
            return accept(fix, lastAccepted.segment + 1);
        }

        double elapsedSeconds = (fix.elapsedMillis - previous.elapsedMillis) / 1_000.0;
        double distanceMeters = TrackMetrics.haversineMeters(previous.latitude, previous.longitude,
                fix.latitude, fix.longitude);
        double accuracyAllowanceMeters = 3 * (previous.accuracyMeters + fix.accuracyMeters) + 10;
        double jumpLimitMeters = Math.max(MAX_SPEED_METERS_PER_SECOND * elapsedSeconds,
                accuracyAllowanceMeters);
        if (distanceMeters > jumpLimitMeters) {
            return new Result(Status.JUMP, null, "定位点偏离轨迹过远");
        }
        if (distanceMeters < Math.max(1.5, fix.accuracyMeters * 0.3)) {
            return new Result(Status.NO_MOVEMENT, null, "移动距离低于定位抖动阈值");
        }
        return accept(fix, lastAccepted.segment);
    }

    public void reset() {
        lastAccepted = null;
    }

    private Result accept(LocationFix fix, int segment) {
        long sequence = lastAccepted == null ? 1 : lastAccepted.sequence + 1;
        lastAccepted = new TrackPoint(sequence, segment, fix);
        return new Result(Status.ACCEPTED, lastAccepted, "");
    }

    private static boolean isValid(LocationFix fix) {
        return fix != null
                && fix.latitude >= -90 && fix.latitude <= 90
                && fix.longitude >= -180 && fix.longitude <= 180
                && fix.accuracyMeters > 0 && fix.accuracyMeters < Double.POSITIVE_INFINITY;
    }

    private static boolean exceedsInterval(long later, long earlier, long intervalMillis) {
        return earlier <= Long.MAX_VALUE - intervalMillis && later > earlier + intervalMillis;
    }
}
