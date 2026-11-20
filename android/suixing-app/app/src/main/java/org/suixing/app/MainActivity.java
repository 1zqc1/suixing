package org.suixing.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.*;
import org.suixing.app.core.TrackPoint;
import org.suixing.app.map.MapPanel;
import java.text.DateFormat;
import java.util.Collections;
import java.util.Date;
import java.util.List;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final int LOCATION = 10, NOTIFICATIONS = 11, DOCUMENT = 12;
    private static final int INK = 0xff183430, MUTED = 0xff485f59, TEAL = 0xff00685f, BG = 0xfff4f7f6;
    private TrackApp app;
    private boolean resumed, mapConsent, follow = true, phone, consentOpen, requestingLocation;
    private long generation, exportId = -1, restoreId = -1;
    private MapPanel map;
    private FrameLayout mapSlot;
    private LinearLayout page, metrics;
    private RadioButton demoRadio, phoneRadio;
    private Button record, center, history, play, export, leave, privacy, notifyButton;
    private TextView mode, feedback, signal, network, countValue, distanceValue, timeValue;
    private TrackStore.Session selected;
    private TrackApp.Saved saved;
    private boolean replaying;
    private int shown;
    private Object lastTrack;
    private int lastShown = -1;
    private String netText = "正在检查网络";
    private final Runnable update = this::render;
    private final Runnable clock = new Runnable() {
        @Override public void run() {
            render();
            if (resumed) app.main.postDelayed(this, 1000);
        }
    };
    private final Runnable playNext = new Runnable() {
        @Override public void run() {
            if (!replaying || saved == null) return;
            int size = saved.points.size();
            shown = Math.min(size, shown + Math.max(1, (size + 119) / 120));
            if (shown == size) {
                replaying = false;
                app.message = "回放结束";
            } else app.main.postDelayed(this, 700);
            render();
        }
    };
    private final BroadcastReceiver networkReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) { updateNetwork(); }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        app = (TrackApp) getApplication();
        if (state != null) {
            phone = state.getBoolean("phone"); follow = state.getBoolean("follow", true);
            restoreId = state.getLong("history", -1); exportId = state.getLong("export", -1);
            requestingLocation = state.getBoolean("requestingLocation");
        }
        if (app.active != null) phone = app.phoneActive();
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
                | (Build.VERSION.SDK_INT >= 26 ? View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR : 0));
        getWindow().setStatusBarColor(Color.TRANSPARENT);
        getWindow().setNavigationBarColor(Build.VERSION.SDK_INT >= 26 ? BG : INK);
        if (Build.VERSION.SDK_INT >= 29) getWindow().setNavigationBarContrastEnforced(false);
        buildPage();
        render();
    }
    private void buildPage() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true); scroll.setBackgroundColor(BG);
        scroll.setOnApplyWindowInsetsListener((v, inset) -> {
            int left = inset.getSystemWindowInsetLeft(), top = inset.getSystemWindowInsetTop();
            int right = inset.getSystemWindowInsetRight(), bottom = inset.getSystemWindowInsetBottom();
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = inset.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                left = bars.left; top = bars.top; right = bars.right; bottom = bars.bottom;
            }
            v.setPadding(left, top, right, bottom);
            return inset;
        });
        page = new LinearLayout(this);
        page.setOrientation(LinearLayout.VERTICAL); page.setPadding(dp(16), dp(10), dp(16), dp(24));
        scroll.addView(page); setContentView(scroll);
        LinearLayout header = row();
        TextView title = label("随行轨迹", 28, INK, true);
        header.addView(title, weight());
        privacy = button("隐私设置", false, v -> consentDialog());
        header.addView(privacy); page.addView(header);
        RadioGroup sources = new RadioGroup(this);
        sources.setOrientation(LinearLayout.HORIZONTAL);
        demoRadio = radio("模拟轨迹"); phoneRadio = radio("手机 GPS");
        sources.addView(demoRadio, weight()); sources.addView(phoneRadio, weight());
        (phone ? phoneRadio : demoRadio).setChecked(true);
        sources.setOnCheckedChangeListener((group, id) -> {
            boolean choosePhone = id == phoneRadio.getId();
            if (phone == choosePhone || app.active != null) return;
            phone = choosePhone;
            clearHistory(); app.frame = TrackApp.Frame.empty(); app.message = "准备记录"; render();
        });
        page.addView(sources);
        mode = label("", 18, TEAL, true); add(page, mode, 8);
        feedback = label("", 16, INK, false); add(page, feedback, 4);
        record = button("开始记录", true, v -> recordClick()); add(page, record, 8);
        mapSlot = new FrameLayout(this);
        LinearLayout.LayoutParams mapParams = new LinearLayout.LayoutParams(-1, dp(218));
        mapParams.topMargin = dp(12); page.addView(mapSlot, mapParams);
        center = button("跟随当前位置", false, v -> {
            follow = !follow; lastShown = -1; render();
        });
        add(page, center, 2);
        metrics = row(); metrics.setPadding(dp(8), dp(12), dp(8), dp(12)); metrics.setBackground(background(Color.WHITE, 12));
        countValue = metric("轨迹点"); distanceValue = metric("距离"); timeValue = metric("时长");
        add(page, metrics, 6);
        signal = label("", 16, INK, false); add(page, signal, 10);
        network = label("", 16, MUTED, false); add(page, network, 6);
        notifyButton = button("允许显示记录通知", false, v -> notificationPermission()); add(page, notifyButton, 2);
        add(page, label("本地历史", 21, INK, true), 18);
        history = button("选择历史记录", false, v -> chooseHistory()); add(page, history, 4);
        LinearLayout actions = row();
        play = button("回放轨迹", false, v -> toggleReplay());
        export = button("导出 JSONL", false, v -> selectDocument());
        actions.addView(play, weight()); actions.addView(export, weight()); add(page, actions, 2);
        leave = button("返回实时视图", false, v -> {
            clearHistory(); app.message = "准备记录"; render();
        });
        add(page, leave, 2);
    }
    private RadioButton radio(String text) {
        RadioButton radio = new RadioButton(this);
        radio.setText(text); radio.setTextSize(16); radio.setMinHeight(dp(48));
        radio.setContentDescription(text); radio.setId(View.generateViewId()); return radio;
    }
    private TextView metric(String text) {
        LinearLayout column = new LinearLayout(this); column.setOrientation(LinearLayout.VERTICAL);
        TextView number = label("—", 19, INK, true);
        number.setGravity(Gravity.CENTER); column.addView(number);
        TextView caption = label(text, 15, MUTED, false);
        caption.setGravity(Gravity.CENTER); column.addView(caption);
        metrics.addView(column, weight()); return number;
    }
    private int dp(int n) { return Math.round(n * getResources().getDisplayMetrics().density); }
    private LinearLayout row() {
        LinearLayout result = new LinearLayout(this); result.setGravity(Gravity.CENTER_VERTICAL); return result;
    }
    private static LinearLayout.LayoutParams weight() { return new LinearLayout.LayoutParams(0, -2, 1); }
    private void add(LinearLayout box, View child, int topMargin) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = dp(topMargin); box.addView(child, lp);
    }
    private GradientDrawable background(int color, int radius) {
        GradientDrawable bg = new GradientDrawable(); bg.setColor(color); bg.setCornerRadius(dp(radius)); return bg;
    }
    private TextView label(String text, int size, int color, boolean bold) {
        TextView view = new TextView(this); view.setText(text); view.setTextColor(color); view.setTextSize(size);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD); return view;
    }
    private Button button(String text, boolean primary, View.OnClickListener action) {
        Button b = new Button(this, null, primary ? android.R.attr.buttonStyle : android.R.attr.borderlessButtonStyle);
        b.setText(text); b.setContentDescription(text); b.setTextSize(16); b.setAllCaps(false);
        b.setMinHeight(dp(48)); b.setMinimumHeight(dp(48)); b.setMinWidth(dp(48));
        b.setTextColor(new android.content.res.ColorStateList(
                new int[][]{new int[]{-android.R.attr.state_enabled}, new int[]{}},
                new int[]{0xff74847f, primary ? Color.WHITE : TEAL}));
        if (primary) b.setBackground(new android.graphics.drawable.RippleDrawable(
                android.content.res.ColorStateList.valueOf(0x4466aa99), background(TEAL, 10), null));
        b.setOnClickListener(action); return b;
    }
    private void caption(Button b, String text) { b.setText(text); b.setContentDescription(text); }
    private void setMap(boolean consent) {
        if (map != null) {
            if (resumed) map.onPause();
            map.onDestroy(); mapSlot.removeView(map);
        }
        mapConsent = consent; map = new MapPanel(this, consent);
        mapSlot.addView(map); if (resumed) map.onResume();
        lastTrack = null; lastShown = -1;
    }

    private void render() {
        if (isDestroyed() || isFinishing()) return;
        if (map == null || mapConsent != app.consent) setMap(app.consent);
        boolean active = app.active != null;
        if (active && selected != null) clearHistory();
        boolean viewing = selected != null;
        boolean enabled = app.ready && !app.savingConsent;
        demoRadio.setEnabled(enabled && !active); phoneRadio.setEnabled(enabled && !active);
        privacy.setEnabled(enabled);
        record.setEnabled(enabled && !app.finishing && !requestingLocation && !viewing);
        history.setEnabled(enabled && !active);
        play.setEnabled(!active && saved != null && !saved.points.isEmpty());
        export.setEnabled(!active && saved != null && !replaying);
        leave.setVisibility(viewing ? View.VISIBLE : View.GONE);
        notifyButton.setVisibility(app.phoneActive() && Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                ? View.VISIBLE : View.GONE);
        caption(record, active ? (app.finishing ? "正在保存…" : "结束记录") : "开始记录");
        caption(play, replaying ? "取消回放" : "回放轨迹");
        caption(center, follow ? "位置跟随 · 已开启" : "位置跟随 · 已关闭");
        String source = active ? app.active.source : (phone ? TrackApp.PHONE : TrackApp.DEMO);
        String modeText = viewing ? (replaying ? "历史回放" : "历史轨迹") + " · " + sourceName(selected.source)
                : sourceName(source) + (active ? " · 记录中" : " · 实时视图");
        mode.setText(modeText); map.setModeLabel(modeText);
        boolean showLive = !viewing && (active || source.equals(app.frame.source));
        List<TrackPoint> points = viewing && saved != null ? saved.points
                : showLive ? app.frame.points : Collections.emptyList();
        int n = viewing ? Math.min(shown, points.size()) : points.size();
        TrackPoint last = n == 0 ? null : points.get(n - 1);
        if (points != lastTrack || n != lastShown) {
            map.setTrack(n == points.size() ? points : points.subList(0, n), last, follow);
            lastTrack = points; lastShown = n;
        }
        center.setEnabled(last != null);
        int count = viewing ? n : showLive ? app.frame.count : 0;
        double distance = viewing ? (n > 0 ? saved.distances[n - 1] : 0) : showLive ? app.frame.distance : 0;
        long duration = viewing ? (n > 0 ? last.fix.elapsedMillis - points.get(0).fix.elapsedMillis : 0)
                : showLive ? app.frame.duration : 0;
        countValue.setText(String.valueOf(count));
        distanceValue.setText(distance < 1000 ? String.format(Locale.CHINA, "%.0f m", distance)
                : String.format(Locale.CHINA, "%.2f km", distance / 1000));
        timeValue.setText(String.format(Locale.ROOT, "%d:%02d", duration / 60000, duration / 1000 % 60));
        double accuracy = viewing && last != null ? last.fix.accuracyMeters : showLive ? app.frame.accuracy : Double.NaN;
        String accuracyText = Double.isNaN(accuracy) || Double.isInfinite(accuracy) ? "—" : String.format(Locale.CHINA, "%.1f m", accuracy);
        signal.setText("定位精度  " + accuracyText + (viewing && selected.mock ? " · 含系统模拟定位" : ""));
        netTextToView();
        String state = app.message;
        if (active && !app.finishing) {
            state = app.phoneActive() ? FixHealth.describe(app.active.startElapsed, app.frame.callback,
                    app.frame.fresh, SystemClock.elapsedRealtime(), app.frame.status)
                    : "固定示例路线 · 每秒采样";
        }
        feedback.setText(state);
        if (viewing) caption(history, selectedLabel(selected));
        else caption(history, "选择历史记录");
        if (resumed && app.ready && !app.decided && !consentOpen && !app.savingConsent) consentDialog();
        if (resumed && app.ready && restoreId >= 0 && !active) restoreHistory();
    }
    private void netTextToView() { network.setText(netText + " · 轨迹在本机保存"); }
    private void updateNetwork() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        try {
            Network connection = cm.getActiveNetwork();
            NetworkCapabilities cap = cm.getNetworkCapabilities(connection);
            if (cap == null || !cap.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) {
                netText = "离线，在线底图可能不可用";
            } else if (!cap.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) {
                netText = "网络已连接，互联网尚未验证";
            } else netText = "网络已连接";
        } catch (RuntimeException e) { netText = "网络状态未知"; }
        netTextToView();
    }
    private static String sourceName(String source) {
        return TrackApp.DEMO.equals(source) ? "模拟轨迹 DEMO" : "手机 GPS";
    }
    private String selectedLabel(TrackStore.Session session) {
        return DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT).format(new Date(session.started))
                + " · " + sourceName(session.source) + (session.mock ? "（系统模拟）" : "") + " · "
                + session.count + " 点 · " + ("SAVED".equals(session.status) ? "已结束" : "已中断");
    }

    private void consentDialog() {
        if (consentOpen || !app.ready || isFinishing()) return;
        consentOpen = true;
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("位置与隐私")
                .setMessage("手机 GPS 需精确定位，轨迹与历史保存在本机。仅在配置 AK 并同意后，百度地图 SDK 才会联网加载底图。随行尚未连接车辆。你可以随时撤回同意，也可以只使用模拟轨迹和历史。")
                .setPositiveButton("同意", (d,w) -> app.setConsent(true))
                .setNegativeButton(app.consent ? "撤回同意" : "仅使用模拟和历史", (d,w) -> {
                    boolean revoke = app.consent;
                    app.setConsent(false);
                    if (revoke) MapPanel.revokeSdkPrivacy(this);
                }).create();
        dialog.setCancelable(app.decided);
        dialog.setOnDismissListener(d -> consentOpen = false);
        dialog.show();
    }
    private void recordClick() {
        if (app.active != null) { app.stop("记录已结束", false); return; }
        if (!phone) { clearHistory(); app.begin(TrackApp.DEMO); return; }
        if (!app.consent) { consentDialog(); return; }
        if (!PhoneService.precise(this)) {
            if (shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_FINE_LOCATION)) {
                new AlertDialog.Builder(this).setTitle("手机轨迹需要精确位置")
                        .setMessage("大致位置无法可靠记录步行轨迹。请在下一步选择“精确”，也可以继续使用模拟模式。")
                        .setPositiveButton("申请精确位置", (d,w) -> requestLocation())
                        .setNegativeButton("取消", null).show();
            } else requestLocation();
            return;
        }
        beginPhone();
    }
    private void requestLocation() {
        requestingLocation = true; render();
        requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION}, LOCATION);
    }
    private void beginPhone() {
        if (!resumed || !phone || !app.consent || !PhoneService.precise(this)) return;
        if (!PhoneService.gpsOn(this)) {
            showSettings("系统 GPS 未开启", "请开启系统位置服务后再开始记录。", new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS));
            return;
        }
        clearHistory();
        TrackApp.Run run = app.begin(TrackApp.PHONE);
        if (run == null) return;
        try {
            Intent service = new Intent(this, PhoneService.class).putExtra(PhoneService.TOKEN, run.startElapsed);
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(service); else startService(service);
        } catch (RuntimeException e) { app.stop("前台定位服务启动失败", true); }
    }
    private void notificationPermission() {
        if (Build.VERSION.SDK_INT < 33) return;
        new AlertDialog.Builder(this).setTitle("显示记录通知")
                .setMessage("允许后可在通知栏查看手机记录并结束定位。")
                .setPositiveButton("继续", (d,w) -> requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIFICATIONS))
                .setNegativeButton("取消", null).show();
    }
    private void showSettings(String title, String details, Intent intent) {
        new AlertDialog.Builder(this).setTitle(title).setMessage(details)
                .setPositiveButton("打开设置", (d,w) -> {
                    try { startActivity(intent); } catch (ActivityNotFoundException e) { tell("此设备未提供相应设置页面"); }
                }).setNegativeButton("返回", null).show();
    }
    private Intent appSettings() { return new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName())); }
    private void tell(String message) { app.message = message; render(); Toast.makeText(this, message, Toast.LENGTH_SHORT).show(); }

    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(code, permissions, grants);
        if (code == LOCATION) {
            requestingLocation = false;
            if (grants.length == 0) { tell("定位授权已取消"); return; }
            if (PhoneService.precise(this)) {
                // Permission callbacks can precede onResume.
                if (resumed) beginPhone(); else startWhenResumed = true;
            } else {
                boolean approximate = checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
                String reason = approximate ? "仅授予大致位置，手机轨迹需要精确定位" : "未获定位权限，可使用模拟轨迹和历史";
                tell(reason);
                if (!shouldShowRequestPermissionRationale(Manifest.permission.ACCESS_FINE_LOCATION)) {
                    showSettings("精确定位未授权", reason + "。可在应用设置的权限页面调整。", appSettings());
                }
            }
        } else if (code == NOTIFICATIONS && Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                if (!shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)) {
                    showSettings("记录通知未开启", "手机定位仍可使用，通知可在应用设置中开启。", appSettings());
                } else tell("通知未开启，可回到随行结束定位");
            }
        }
        render();
    }
    private boolean startWhenResumed;

    private void clearHistory() {
        generation++; restoreId = -1; replaying = false;
        app.main.removeCallbacks(playNext); selected = null; saved = null; shown = 0;
    }
    private boolean valid(long token) { return token == generation && app.active == null && !isDestroyed() && !isFinishing(); }
    private void chooseHistory() {
        cancelReplay();
        long token = ++generation;
        app.history((sessions,error) -> {
            if (!valid(token) || !resumed) return;
            if (error != null) { tell(error); return; }
            if (sessions.isEmpty()) { tell("暂无历史记录，结束一次记录后可在这里查看"); return; }
            String[] options = new String[sessions.size()];
            for (int i = 0; i < options.length; i++) options[i] = selectedLabel(sessions.get(i));
            new AlertDialog.Builder(this).setTitle("选择本地轨迹").setItems(options,
                    (d,i) -> { if (valid(token)) select(sessions.get(i)); })
                    .setNegativeButton("取消", null).show();
        });
    }
    private void restoreHistory() {
        long wanted = restoreId; restoreId = -1;
        long token = ++generation;
        app.history((sessions,error) -> {
            if (!valid(token)) return;
            if (error != null) { tell(error); return; }
            for (TrackStore.Session session : sessions) if (session.id == wanted) { select(session); break; }
        });
    }
    private void select(TrackStore.Session session) {
        clearHistory(); long token = generation; selected = session;
        app.message = "正在读取历史轨迹"; render();
        app.load(session.id, (data,error) -> {
            if (!valid(token)) return;
            if (error != null) { clearHistory(); tell(error); return; }
            saved = data; shown = data.points.size();
            app.message = shown == 0 ? "该次记录没有收到可保存的定位点" : "已载入本地轨迹"; render();
        });
    }
    private void cancelReplay() {
        if (!replaying) return;
        replaying = false; app.main.removeCallbacks(playNext);
        shown = saved.points.size(); app.message = "已取消回放"; render();
    }
    private void toggleReplay() {
        if (replaying) { cancelReplay(); return; }
        if (saved == null || saved.points.isEmpty()) return;
        shown = 0; replaying = true; app.message = "正在回放已保存的轨迹"; playNext.run();
    }
    private void selectDocument() {
        if (selected == null) return;
        exportId = selected.id;
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType("application/octet-stream").putExtra(Intent.EXTRA_TITLE, "suixing-track-" + exportId + ".jsonl");
        try { startActivityForResult(intent, DOCUMENT); }
        catch (ActivityNotFoundException e) { exportId = -1; tell("设备没有可用的文档保存器"); }
    }
    @Override protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        if (code != DOCUMENT) return;
        long id = exportId; exportId = -1;
        if (result != RESULT_OK || data == null || data.getData() == null || id < 0) { tell("导出已取消"); return; }
        app.export(id, data.getData());
    }
    @Override protected void onStart() {
        super.onStart();
        app.listener = update;
        IntentFilter changes = new IntentFilter(ConnectivityManager.CONNECTIVITY_ACTION);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(networkReceiver, changes, RECEIVER_NOT_EXPORTED);
        else registerReceiver(networkReceiver, changes);
        updateNetwork();
    }
    @Override protected void onResume() {
        super.onResume(); resumed = true;
        if (map != null) map.onResume();
        if (app.phoneActive() && (!app.consent || !PhoneService.precise(this))) app.stop("精确定位授权已撤回", true);
        if (startWhenResumed) { startWhenResumed = false; beginPhone(); }
        clock.run();
    }
    @Override protected void onPause() {
        resumed = false; app.main.removeCallbacks(clock); cancelReplay();
        if (map != null) map.onPause(); super.onPause();
    }
    @Override protected void onStop() {
        unregisterReceiver(networkReceiver);
        if (app.listener == update) app.listener = null;
        if (app.active != null && TrackApp.DEMO.equals(app.active.source) && !isChangingConfigurations()) {
            app.stop("模拟记录随界面转入后台而结束", false);
        }
        super.onStop();
    }
    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        out.putBoolean("phone", phone); out.putBoolean("follow", follow);
        out.putLong("history", selected == null ? restoreId : selected.id);
        out.putLong("export", exportId); out.putBoolean("requestingLocation", requestingLocation);
    }
    @Override public void onBackPressed() {
        if (replaying) cancelReplay();
        else if (selected != null) { clearHistory(); app.message = "准备记录"; render(); }
        else super.onBackPressed();
    }
    @Override protected void onDestroy() {
        generation++;
        if (map != null) map.onDestroy();
        super.onDestroy();
    }
}
