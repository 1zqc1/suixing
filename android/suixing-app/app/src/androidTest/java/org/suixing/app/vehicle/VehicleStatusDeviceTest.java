package org.suixing.app.vehicle;

import android.content.res.AssetManager;
import android.content.res.Configuration;
import android.graphics.Rect;
import android.test.InstrumentationTestCase;
import android.view.View;
import android.view.ViewGroup;
import android.widget.RadioButton;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.IOException;
import java.io.StringReader;

public class VehicleStatusDeviceTest extends InstrumentationTestCase {
    private static final String CONFIRMED_SAMPLE = "{\"schema_version\":\"0.1\",\"source\":\"mock\",\"brake_feedback\":\"APPLIED\",";

    public void testThreeOriginalAssetsAndIndependentSwitching() throws IOException {
        AssetManager assets = getInstrumentation().getTargetContext().getAssets();
        VehicleStatus normal = VehicleScenario.NORMAL.read(assets);
        assertCommonFields(normal);
        assertEquals("normal_ready", normal.scenarioLabel());
        assertEquals("待机 · READY", normal.systemLabel());
        assertEquals("未请求制动", normal.brakeRequestLabel());
        assertEquals("已释放 · RELEASED", normal.brakeFeedbackLabel());
        assertEquals("在线 · ONLINE", normal.d6Label());
        assertEquals("无 · NONE", normal.reasonLabel());

        VehicleStatus offline = VehicleScenario.SENSOR_OFFLINE.read(assets);
        assertCommonFields(offline);
        assertEquals("d6_offline", offline.scenarioLabel());
        assertEquals("故障安全 · FAULT_SAFE", offline.systemLabel());
        assertEquals("已请求制动", offline.brakeRequestLabel());
        assertEquals("尚未确认施加 · UNKNOWN", offline.brakeFeedbackLabel());
        assertEquals("离线 · OFFLINE", offline.d6Label());
        assertEquals("D6 离线 · D6_OFFLINE", offline.reasonLabel());

        VehicleStatus latched = VehicleScenario.BRAKE_LATCHED.read(assets);
        assertCommonFields(latched);
        assertEquals("brake_latched", latched.scenarioLabel());
        assertEquals("制动锁存 · BRAKE_LATCHED", latched.systemLabel());
        assertEquals("已请求制动", latched.brakeRequestLabel());
        assertEquals("已确认施加 · APPLIED", latched.brakeFeedbackLabel());
        assertEquals("在线 · ONLINE", latched.d6Label());
        assertEquals("检测到危险 · HAZARD", latched.reasonLabel());

        assertEquals("尚未确认施加 · UNKNOWN", VehicleScenario.SENSOR_OFFLINE.read(assets).brakeFeedbackLabel());
        VehicleStatus normalAgain = VehicleScenario.NORMAL.read(assets);
        assertEquals("待机 · READY", normalAgain.systemLabel());
        assertEquals("未请求制动", normalAgain.brakeRequestLabel());
        assertEquals("已释放 · RELEASED", normalAgain.brakeFeedbackLabel());
    }

    public void testInvalidTypesAndUnknownValuesRemainUnknown() throws IOException {
        VehicleStatus status = parse("""
                {"schema_version":"0.1","source":"mock","scenario":"future_case",
                "sample_time_utc":"2026-02-31T00:00:00Z","system_state":"FUTURE",
                "motion_permitted":"true","estop_active":1,"brake_requested":[],"brake_feedback":"DONE",
                "sensors":{"d6":true,"stereo":"FROZEN"},"reason_code":null}
                """);

        assertEquals("未知", status.scenarioLabel());
        assertEquals("未知", status.sampleTimeLabel());
        assertEquals("未知", status.systemLabel());
        assertEquals("运动许可未知", status.motionLabel());
        assertEquals("急停状态未知", status.estopLabel());
        assertEquals("制动请求未知", status.brakeRequestLabel());
        assertEquals("回读未知 · 尚未确认施加", status.brakeFeedbackLabel());
        assertEquals("未知", status.d6Label());
        assertEquals("未知", status.stereoLabel());
        assertEquals("未知", status.reasonLabel());
    }

    public void testMissingFieldsAndWrongSensorsShapeAreUnknown() throws IOException {
        VehicleStatus status = parse("{\"schema_version\":\"0.1\",\"source\":\"mock\",\"sensors\":[]}");

        assertEquals("运动许可未知", status.motionLabel());
        assertEquals("制动请求未知", status.brakeRequestLabel());
        assertEquals("回读未知 · 尚未确认施加", status.brakeFeedbackLabel());
        assertEquals("未知", status.d6Label());
        assertEquals("未知", status.stereoLabel());
    }

    public void testUnsupportedOrMalformedPayloadIsRejected() {
        assertRejected("{\"schema_version\":0.1,\"source\":\"mock\",\"brake_feedback\":\"APPLIED\"}");
        assertRejected("{\"schema_version\":\"0.2\",\"source\":\"mock\"}");
        assertRejected("{\"schema_version\":\"0.1\",\"source\":\"recorded\"}");
        assertRejected("{\"schema_version\":\"0.1\"}");
        assertRejected("[{}]");
        assertRejected("{\"schema_version\":\"0.1\",\"source\":\"mock\"");
        assertRejected("{schema_version:\"0.1\",\"source\":\"mock\"}");
        assertRejected("{\"schema_version\":\"0.1\",\"source\":\"mock\"} {}");
        assertRejected("{\"schema_version\":\"0.1\",\"source\":\"mock\",\"brake_requested\":false,\"brake_requested\":true}");
        assertRejected("{\"schema_version\":\"0.1\",\"source\":\"mock\",\"motion_permitted\":TRUE}");
        assertRejected("{\"schema_version\":\"0.1\",\"source\":\"mock\",\"brake_requested\":FALSE}");
        assertRejected("{\"schema_version\":\"0.1\",\"source\":\"mock\",\"brake_feedback\":\"\\APPLIED\"}");
        assertRejected("{\"schema_version\":\"0.1\",\"source\":\"mock\",\"reason_code\":\"\\uXXXX\"}");
    }

    public void testRawControlCharactersInExtraMembersAreRejected() {
        assertRejected(CONFIRMED_SAMPLE + "\"extra\":\"raw\nline\"}");
        assertRejected(CONFIRMED_SAMPLE + "\"sensors\":{\"extra\":[{\"raw\tname\":true}]}}");
    }

    public void testRawControlCharactersInWrongFieldShapesAreRejected() {
        assertRejected(CONFIRMED_SAMPLE + "\"sensors\":[{\"note\":\"raw\ttab\"}]}");
        assertRejected(CONFIRMED_SAMPLE + "\"system_state\":{\"raw\nname\":null}}");
        assertRejected(CONFIRMED_SAMPLE + "\"motion_permitted\":\"raw\ttab\"}");
    }

    public void testEscapedControlCharactersInIgnoredValuesAcceptThePayload() throws IOException {
        VehicleStatus status = parse(CONFIRMED_SAMPLE
                + "\"extra\":{\"escaped\\tkey\":[\"escaped\\nline\",true,10,{},null]},"
                + "\"sensors\":[{\"note\":\"escaped\\u0009tab\"}],\"motion_permitted\":\"escaped\\ttab\"}");

        assertEquals("已确认施加 · APPLIED", status.brakeFeedbackLabel());
        assertEquals("未知", status.d6Label());
        assertEquals("运动许可未知", status.motionLabel());
    }

    public void testExcessiveNestingInIgnoredValuesIsRejected() {
        StringBuilder payload = new StringBuilder(CONFIRMED_SAMPLE).append("\"extra\":");
        for (int i = 0; i < 64; i++) payload.append('[');
        payload.append("null");
        for (int i = 0; i < 64; i++) payload.append(']');
        assertRejected(payload.append('}').toString());
    }

    public void testScreenSwitchesScenesAndReplacesPreviousStatus() throws Throwable {
        VehicleStatusActivity activity = launchActivity("org.suixing.app", VehicleStatusActivity.class, null);
        try {
            runTestOnUiThread(() -> {
                View content = activity.findViewById(android.R.id.content);
                assertVisibleLabel(content, "合成只读样例 · 未连接实车", "mock · 未连接实车");
                assertVisibleLabel(content, "来源 mock · 格式版本 0.1", "格式版本 0.1");
                assertVisibleLabel(content, "数据版本 m1-handoff-v0.1", "m1-handoff-v0.1");
                assertNotNull(findText(content, "待机 · READY"));
                assertNotNull(findText(content, "无运动许可"));
                assertUsableScrollViewport(findText(content, "待机"));

                select(content, "制动锁存");
                assertNotNull(findText(content, "制动锁存 · BRAKE_LATCHED"));
                assertNotNull(findText(content, "已请求制动"));
                assertNotNull(findText(content, "已确认施加 · APPLIED"));
                assertNotNull(findText(content, "无运动许可"));

                select(content, "D6 离线");
                assertNotNull(findText(content, "故障安全 · FAULT_SAFE"));
                assertNotNull(findText(content, "已请求制动"));
                assertNotNull(findText(content, "尚未确认施加 · UNKNOWN"));
                assertNull(findText(content, "已确认施加 · APPLIED"));
                assertNotNull(findText(content, "无运动许可"));

                select(content, "待机");
                assertNotNull(findText(content, "待机 · READY"));
                assertNotNull(findText(content, "已释放 · RELEASED"));
                assertNotNull(findText(content, "未请求制动"));
                assertNotNull(findText(content, "无运动许可"));
                assertNull(findText(content, "尚未确认施加 · UNKNOWN"));
            });
        } finally {
            runTestOnUiThread(activity::finish);
        }
    }

    private static void assertCommonFields(VehicleStatus status) {
        assertEquals("2026-11-20T00:00:00Z", status.sampleTimeLabel());
        assertEquals("无运动许可", status.motionLabel());
        assertEquals("急停未激活", status.estopLabel());
        assertEquals("在线 · ONLINE", status.stereoLabel());
    }

    private static VehicleStatus parse(String json) throws IOException {
        return VehicleStatusParser.read(new StringReader(json));
    }

    private static void select(View parent, String label) {
        TextView option = findText(parent, label);
        assertTrue(option instanceof RadioButton);
        option.performClick();
        assertTrue(((RadioButton) option).isChecked());
    }

    private static void assertUsableScrollViewport(View option) {
        assertNotNull(option);
        View ancestor = option;
        while (!(ancestor instanceof ScrollView) && ancestor.getParent() instanceof View parent) {
            ancestor = parent;
        }
        assertTrue("Scene choices must be scrollable", ancestor instanceof ScrollView);
        Rect visible = new Rect();
        int touchHeight = Math.round(48 * option.getResources().getDisplayMetrics().density);
        if (ancestor.getGlobalVisibleRect(visible) && visible.height() >= touchHeight) return;
        Configuration config = option.getResources().getConfiguration();
        ViewGroup page = (ViewGroup) ancestor.getParent();
        StringBuilder heights = new StringBuilder();
        for (int i = 0; i < page.getChildCount(); i++) heights.append(' ').append(page.getChildAt(i).getHeight());
        fail("Scroll viewport height " + ancestor.getHeight() + " px, minimum " + touchHeight
                + "; page " + page.getWidth() + "x" + page.getHeight() + " px, padding " + page.getPaddingTop()
                + "/" + page.getPaddingBottom() + ", child heights" + heights + ", config "
                + config.screenWidthDp + "x" + config.screenHeightDp + " dp @" + config.fontScale);
    }

    private static void assertVisibleLabel(View content, String regular, String compact) {
        TextView label = findText(content, regular);
        if (label == null) label = findText(content, compact);
        assertNotNull(regular, label);
        Rect visible = new Rect();
        assertTrue(regular, label.getGlobalVisibleRect(visible) && visible.height() == label.getHeight());
    }

    private static TextView findText(View view, String text) {
        if (view instanceof TextView label && text.contentEquals(label.getText())) return label;
        if (view instanceof ViewGroup group) {
            for (int i = 0; i < group.getChildCount(); i++) {
                TextView match = findText(group.getChildAt(i), text);
                if (match != null) return match;
            }
        }
        return null;
    }

    private void assertRejected(String json) {
        try {
            parse(json);
            fail("Accepted invalid sample: " + json);
        } catch (IOException expected) {
            // An invalid envelope must not produce displayable status values.
        }
    }
}
