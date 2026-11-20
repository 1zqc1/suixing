package org.suixing.app.map;

import android.content.Context;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.widget.FrameLayout;
import android.widget.TextView;

import org.suixing.app.BuildConfig;
import org.suixing.app.core.TrackPoint;

import java.util.List;

/** Displays accepted track points using the available basemap. Use on the main thread. */
public final class MapPanel extends FrameLayout {
    static final int ROUTE_COLOR = 0xff155fbc;
    static final int START_COLOR = 0xff08795b;
    static final int CURRENT_COLOR = 0xff155fbc;

    private static final int DISPLAY_POINT_BUDGET = 1_500;
    private static final String MAP_LOADING = "轨迹示意 · 正在加载百度地图";

    private final SchematicTrackView schematic;
    private final TextView statusLabel;
    private BaiduTrackMap baiduMap;
    private String statusText;
    private String modeLabel = "";
    private boolean destroyed;

    public MapPanel(Context context, boolean privacyAgreed) {
        super(context);
        schematic = new SchematicTrackView(context);
        addView(schematic, new LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT));

        statusLabel = new TextView(context);
        statusLabel.setTextSize(13);
        statusLabel.setTextColor(0xff14283d);
        statusLabel.setPadding(dp(10), dp(5), dp(10), dp(5));
        GradientDrawable badgeBackground = new GradientDrawable();
        badgeBackground.setColor(Color.WHITE);
        badgeBackground.setCornerRadius(dp(8));
        statusLabel.setBackground(badgeBackground);
        statusLabel.setAccessibilityLiveRegion(ACCESSIBILITY_LIVE_REGION_POLITE);
        LayoutParams badgeParams = new LayoutParams(LayoutParams.WRAP_CONTENT,
                LayoutParams.WRAP_CONTENT, Gravity.TOP | Gravity.START);
        badgeParams.setMargins(dp(8), dp(8), dp(8), 0);
        addView(statusLabel, badgeParams);

        if (BuildConfig.BAIDU_MAP_AK.trim().isEmpty()) {
            updateStatus("轨迹示意 · 未配置百度地图 AK");
        } else if (!privacyAgreed) {
            updateStatus("轨迹示意 · 未同意百度地图隐私政策");
        } else {
            updateStatus(MAP_LOADING);
            try {
                baiduMap = new BaiduTrackMap(this,
                        () -> {
                            schematic.setVisibility(GONE);
                            updateStatus("百度地图");
                        }, this::useSchematic);
                baiduMap.initialize(BuildConfig.BAIDU_MAP_AK);
            } catch (RuntimeException | LinkageError failure) {
                useSchematic("百度地图初始化失败");
            }
        }
    }

    public void setTrack(List<TrackPoint> track, TrackPoint current, boolean follow) {
        if (destroyed) {
            return;
        }
        List<List<TrackPoint>> segments = TrackRenderGeometry.sample(track, DISPLAY_POINT_BUDGET);
        schematic.setTrack(segments, current);
        if (baiduMap != null) {
            baiduMap.setTrack(segments, current, follow);
        }
    }

    public void setModeLabel(String modeLabel) {
        this.modeLabel = modeLabel == null ? "" : modeLabel;
        updateStatus(statusText);
    }

    public String getStatusText() {
        return statusText;
    }

    public void onResume() {
        if (baiduMap != null) {
            baiduMap.onResume();
        }
    }

    public void onPause() {
        if (baiduMap != null) {
            baiduMap.onPause();
        }
    }

    public void onDestroy() {
        destroyed = true;
        releaseMap();
    }

    /** Call after destroying the existing map panel when the user withdraws consent. */
    public static void revokeSdkPrivacy(Context context) {
        BaiduTrackMap.revokePrivacy(context.getApplicationContext());
    }

    private void useSchematic(String reason) {
        if (destroyed) {
            return;
        }
        schematic.setVisibility(VISIBLE);
        releaseMap();
        updateStatus("轨迹示意 · " + reason);
    }

    private void releaseMap() {
        BaiduTrackMap map = baiduMap;
        baiduMap = null;
        if (map != null) {
            map.close();
        }
    }

    private void updateStatus(String text) {
        statusText = text;
        statusLabel.setText(modeLabel.isEmpty() ? text : text + "\n" + modeLabel);
    }

    private int dp(float value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
