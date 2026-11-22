package org.suixing.app.vehicle;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.IOException;

public final class VehicleStatusActivity extends Activity {
    private static final int BACKGROUND = 0xfff4f7f6;
    private static final int INK = 0xff183430;
    private static final int MUTED = 0xff485f59;
    private static final int TEAL = 0xff00685f;
    private static final int BANNER = 0xffe1eeeb;
    private static final String SELECTED_SCENARIO = "vehicle.scenario";

    private VehicleScenario selected = VehicleScenario.NORMAL;
    private LinearLayout details;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (state != null) {
            VehicleScenario restored = VehicleScenario.fromId(state.getString(SELECTED_SCENARIO));
            if (restored != null) selected = restored;
        }
        configureSystemBars();

        LinearLayout page = column();
        page.setBackgroundColor(BACKGROUND);
        page.setOnApplyWindowInsetsListener(this::applySystemInsets);
        boolean shortWindow = getResources().getConfiguration().screenHeightDp < 300;
        if (!shortWindow) page.addView(header());
        page.addView(provenanceBanner(shortWindow));

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        LinearLayout body = column();
        body.setPadding(dp(16), 0, dp(16), dp(16));
        if (shortWindow) body.addView(header());
        body.addView(sceneSelector());
        details = column();
        details.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        body.addView(details);
        scroll.addView(body);
        page.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(page);
        page.requestApplyInsets();
        display(selected);
    }

    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        out.putString(SELECTED_SCENARIO, selected.id);
    }

    private LinearLayout provenanceBanner(boolean shortWindow) {
        LinearLayout banner = column();
        int margin = dp(shortWindow ? 8 : 16);
        int padding = dp(shortWindow ? 6 : 8);
        banner.setPadding(dp(shortWindow ? 8 : 12), padding, dp(shortWindow ? 8 : 12), padding);
        banner.setBackground(surface(BANNER));

        String schema = "格式版本 " + VehicleStatus.SCHEMA_VERSION;
        if (shortWindow) {
            banner.addView(label(VehicleStatus.SOURCE + " · 未连接实车", 14, TEAL, true));
            banner.addView(label(schema, 14, INK, false));
            banner.addView(label(VehicleStatus.DATA_VERSION, 14, INK, false));
        } else {
            banner.addView(label("合成只读样例 · 未连接实车", 16, TEAL, true));
            banner.addView(label("来源 " + VehicleStatus.SOURCE + " · " + schema, 14, INK, false));
            banner.addView(label("数据版本 " + VehicleStatus.DATA_VERSION, 14, INK, false));
        }

        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.setMargins(margin, shortWindow ? dp(4) : 0, margin, shortWindow ? dp(4) : dp(8));
        banner.setLayoutParams(params);
        return banner;
    }

    private LinearLayout header() {
        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(16), dp(4), dp(8), dp(4));
        TextView title = label("车况样例", 26, INK, true);
        if (Build.VERSION.SDK_INT >= 28) title.setAccessibilityHeading(true);
        header.addView(title, new LinearLayout.LayoutParams(0, -2, 1));
        Button back = new Button(this, null, android.R.attr.borderlessButtonStyle);
        back.setText("返回轨迹");
        back.setTextSize(16);
        back.setTextColor(TEAL);
        back.setMinimumHeight(dp(48));
        back.setMinHeight(dp(48));
        back.setMinimumWidth(dp(48));
        back.setOnClickListener(v -> finish());
        header.addView(back);
        return header;
    }

    private RadioGroup sceneSelector() {
        RadioGroup group = new RadioGroup(this);
        Configuration config = getResources().getConfiguration();
        boolean horizontal = config.screenWidthDp >= 360 && config.fontScale < 1.25f;
        group.setOrientation(horizontal ? LinearLayout.HORIZONTAL : LinearLayout.VERTICAL);
        group.setSaveFromParentEnabled(false);
        for (VehicleScenario scenario : VehicleScenario.values()) {
            RadioButton option = new RadioButton(this);
            option.setId(View.generateViewId());
            option.setTag(scenario);
            option.setText(scenario.label);
            option.setTextColor(INK);
            option.setTextSize(15);
            option.setMinHeight(dp(48));
            option.setMinimumHeight(dp(48));
            group.addView(option, horizontal ? new RadioGroup.LayoutParams(0, -2, 1)
                    : new RadioGroup.LayoutParams(-1, -2));
            if (scenario == selected) group.check(option.getId());
        }
        group.setOnCheckedChangeListener((view, id) -> {
            View option = view.findViewById(id);
            if (option != null) display((VehicleScenario) option.getTag());
        });
        return group;
    }

    private void display(VehicleScenario scenario) {
        selected = scenario;
        details.removeAllViews();
        VehicleStatus status;
        try {
            status = scenario.read(getAssets());
        } catch (IOException invalid) {
            LinearLayout message = card();
            message.addView(label("样例不可用", 19, INK, true));
            message.addView(label("无法读取该样例，或样例格式与版本 0.1 不兼容。", 15, MUTED, false));
            details.addView(message);
            return;
        }

        LinearLayout state = card();
        state.addView(label("系统状态", 14, MUTED, false));
        state.addView(label(status.systemLabel(), 21, INK, true));
        details.addView(state);

        LinearLayout safety = card();
        addRow(safety, "运动许可", status.motionLabel());
        addRow(safety, "急停", status.estopLabel());
        addRow(safety, "制动请求", status.brakeRequestLabel());
        addRow(safety, "制动执行回读", status.brakeFeedbackLabel());
        details.addView(safety);

        LinearLayout sensors = card();
        addRow(sensors, "D6 雷达", status.d6Label());
        addRow(sensors, "双目相机", status.stereoLabel());
        addRow(sensors, "原因码", status.reasonLabel());
        details.addView(sensors);

        LinearLayout context = card();
        addRow(context, "场景", status.scenarioLabel());
        addRow(context, "合成样本 UTC", status.sampleTimeLabel());
        details.addView(context);
    }

    private void addRow(LinearLayout card, String field, String value) {
        LinearLayout row = new LinearLayout(this);
        row.setGravity(Gravity.TOP);
        row.setPadding(0, dp(5), 0, dp(5));
        TextView caption = label(field, 14, MUTED, false);
        caption.setPadding(0, 0, dp(8), 0);
        row.addView(caption, new LinearLayout.LayoutParams(0, -2, 2));
        row.addView(label(value, 15, INK, true), new LinearLayout.LayoutParams(0, -2, 3));
        card.addView(row);
    }

    private LinearLayout card() {
        LinearLayout card = column();
        card.setPadding(dp(12), dp(8), dp(12), dp(8));
        card.setBackground(surface(Color.WHITE));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(-1, -2);
        params.topMargin = dp(8);
        card.setLayoutParams(params);
        return card;
    }

    private GradientDrawable surface(int color) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(12));
        return shape;
    }

    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private TextView label(String text, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(text);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private int dp(int size) {
        return Math.round(size * getResources().getDisplayMetrics().density);
    }

    @SuppressWarnings("deprecation")
    private void configureSystemBars() {
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
                | (Build.VERSION.SDK_INT >= 26 ? View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR : 0));
        getWindow().setStatusBarColor(Color.TRANSPARENT);
        getWindow().setNavigationBarColor(Build.VERSION.SDK_INT >= 26 ? BACKGROUND : INK);
        if (Build.VERSION.SDK_INT >= 29) getWindow().setNavigationBarContrastEnforced(false);
    }

    @SuppressWarnings("deprecation")
    private WindowInsets applySystemInsets(View view, WindowInsets insets) {
        if (Build.VERSION.SDK_INT >= 30) {
            android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
        } else {
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
        }
        return insets;
    }
}
