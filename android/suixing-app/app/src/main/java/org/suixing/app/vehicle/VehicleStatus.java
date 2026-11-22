package org.suixing.app.vehicle;

final class VehicleStatus {
    static final String DATA_VERSION = "m1-handoff-v0.1";
    static final String SCHEMA_VERSION = "0.1";
    static final String SOURCE = "mock";
    private static final String UNKNOWN = "未知";

    enum SystemState {
        READY("待机"), FAULT_SAFE("故障安全"), BRAKE_LATCHED("制动锁存");

        final String label;
        SystemState(String label) { this.label = label + " · " + name(); }
    }

    enum BrakeFeedback {
        RELEASED("已释放"), APPLIED("已确认施加"), UNKNOWN("尚未确认施加");

        final String label;
        BrakeFeedback(String label) { this.label = label + " · " + name(); }
    }

    enum SensorHealth {
        ONLINE("在线"), OFFLINE("离线");

        final String label;
        SensorHealth(String label) { this.label = label + " · " + name(); }
    }

    enum Reason {
        NONE("无"), D6_OFFLINE("D6 离线"), HAZARD("检测到危险");

        final String label;
        Reason(String label) { this.label = label + " · " + name(); }
    }

    final String scenario;
    private final String sampleTimeUtc;
    private final SystemState system;
    private final Boolean motionPermitted;
    private final Boolean estopActive;
    private final Boolean brakeRequested;
    private final BrakeFeedback brakeFeedback;
    private final SensorHealth d6;
    private final SensorHealth stereo;
    private final Reason reason;

    VehicleStatus(String scenario, String sampleTimeUtc, SystemState system,
            Boolean motionPermitted, Boolean estopActive, Boolean brakeRequested,
            BrakeFeedback brakeFeedback, SensorHealth d6, SensorHealth stereo, Reason reason) {
        this.scenario = scenario;
        this.sampleTimeUtc = sampleTimeUtc;
        this.system = system;
        this.motionPermitted = motionPermitted;
        this.estopActive = estopActive;
        this.brakeRequested = brakeRequested;
        this.brakeFeedback = brakeFeedback;
        this.d6 = d6;
        this.stereo = stereo;
        this.reason = reason;
    }

    String scenarioLabel() { return scenario == null ? UNKNOWN : scenario; }
    String sampleTimeLabel() { return sampleTimeUtc == null ? UNKNOWN : sampleTimeUtc; }
    String systemLabel() { return system == null ? UNKNOWN : system.label; }
    String d6Label() { return d6 == null ? UNKNOWN : d6.label; }
    String stereoLabel() { return stereo == null ? UNKNOWN : stereo.label; }
    String reasonLabel() { return reason == null ? UNKNOWN : reason.label; }

    String motionLabel() {
        return booleanLabel(motionPermitted, "有运动许可", "无运动许可", "运动许可未知");
    }

    String estopLabel() {
        return booleanLabel(estopActive, "急停已激活", "急停未激活", "急停状态未知");
    }

    String brakeRequestLabel() {
        return booleanLabel(brakeRequested, "已请求制动", "未请求制动", "制动请求未知");
    }

    String brakeFeedbackLabel() {
        return brakeFeedback == null ? "回读未知 · 尚未确认施加" : brakeFeedback.label;
    }

    private static String booleanLabel(Boolean value, String yes, String no, String unknown) {
        if (value == null) return unknown;
        return value ? yes : no;
    }
}
