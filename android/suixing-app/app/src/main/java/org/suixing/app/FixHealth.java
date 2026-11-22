package org.suixing.app;

final class FixHealth {
    private static final long TIMEOUT_MS = 15000;
    private FixHealth() {}

    static String describe(long started, long lastCallback, long lastFresh, long now, String reason) {
        if (lastCallback < 0) {
            return now - started > TIMEOUT_MS ? "未收到 GPS 定位，请到开阔处重试" : "等待首次 GPS 定位";
        }
        if (now - lastCallback > TIMEOUT_MS) return "GPS 信号中断，保留此前轨迹";
        if (now - (lastFresh < 0 ? started : lastFresh) > TIMEOUT_MS) {
            return reason + " · 暂无有效定位，保留此前轨迹";
        }
        return reason;
    }
}
