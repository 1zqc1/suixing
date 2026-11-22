package org.suixing.app;

import org.junit.Test;
import static org.junit.Assert.*;

public class FixHealthTest {
    @Test public void stationaryFreshCallbackKeepsSignalAliveWithoutAcceptedPoint() {
        assertEquals("位置稳定", FixHealth.describe(0, 25000, 25000, 26000, "位置稳定"));
    }
    @Test public void staleCallbacksAndSilencePreserveReasonAndSignalLoss() {
        assertTrue(FixHealth.describe(0, 20000, 1000, 22000, "定位已过期").contains("已过期"));
        assertTrue(FixHealth.describe(0, 20000, 1000, 22000, "定位已过期").contains("有效定位"));
        assertTrue(FixHealth.describe(0, 20000, 20000, 38000, "正常").contains("中断"));
    }
    @Test public void newSessionWaitsBeforeReportingAbsence() {
        assertTrue(FixHealth.describe(30000, -1, -1, 31000, "").contains("等待"));
        assertTrue(FixHealth.describe(30000, -1, -1, 50000, "").contains("未收到"));
    }
}
