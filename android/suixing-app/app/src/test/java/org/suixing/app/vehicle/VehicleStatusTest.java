package org.suixing.app.vehicle;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class VehicleStatusTest {
    @Test public void readyStillShowsMotionDeniedWhenTheFieldIsFalse() {
        VehicleStatus status = new VehicleStatus("normal_ready", null, VehicleStatus.SystemState.READY,
                false, false, false, VehicleStatus.BrakeFeedback.RELEASED,
                VehicleStatus.SensorHealth.ONLINE, VehicleStatus.SensorHealth.ONLINE,
                VehicleStatus.Reason.NONE);

        assertEquals("待机 · READY", status.systemLabel());
        assertEquals("无运动许可", status.motionLabel());
        assertEquals("未请求制动", status.brakeRequestLabel());
        assertEquals("已释放 · RELEASED", status.brakeFeedbackLabel());
    }

    @Test public void theExecutionLabelOnlyDependsOnFeedback() {
        VehicleStatus offline = new VehicleStatus("d6_offline", null, VehicleStatus.SystemState.FAULT_SAFE,
                false, false, true, VehicleStatus.BrakeFeedback.UNKNOWN,
                VehicleStatus.SensorHealth.OFFLINE, VehicleStatus.SensorHealth.ONLINE,
                VehicleStatus.Reason.D6_OFFLINE);
        VehicleStatus latched = new VehicleStatus("brake_latched", null, VehicleStatus.SystemState.BRAKE_LATCHED,
                false, false, true, VehicleStatus.BrakeFeedback.APPLIED,
                VehicleStatus.SensorHealth.ONLINE, VehicleStatus.SensorHealth.ONLINE,
                VehicleStatus.Reason.HAZARD);

        assertEquals("已请求制动", offline.brakeRequestLabel());
        assertEquals("尚未确认施加 · UNKNOWN", offline.brakeFeedbackLabel());
        assertEquals("已请求制动", latched.brakeRequestLabel());
        assertEquals("已确认施加 · APPLIED", latched.brakeFeedbackLabel());
    }

    @Test public void missingValuesHaveExplicitUnknownLabels() {
        VehicleStatus status = new VehicleStatus(null, null, null, null, null, null, null, null, null, null);

        assertEquals("未知", status.systemLabel());
        assertEquals("运动许可未知", status.motionLabel());
        assertEquals("急停状态未知", status.estopLabel());
        assertEquals("制动请求未知", status.brakeRequestLabel());
        assertEquals("回读未知 · 尚未确认施加", status.brakeFeedbackLabel());
        assertEquals("未知", status.d6Label());
        assertEquals("未知", status.stereoLabel());
        assertEquals("未知", status.reasonLabel());
        assertEquals("未知", status.scenarioLabel());
        assertEquals("未知", status.sampleTimeLabel());
    }
}
