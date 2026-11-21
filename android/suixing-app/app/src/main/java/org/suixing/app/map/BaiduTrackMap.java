package org.suixing.app.map;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.widget.FrameLayout;

import com.baidu.mapapi.CoordType;
import com.baidu.mapapi.RequestAuthResultListener;
import com.baidu.mapapi.SDKInitializer;
import com.baidu.mapapi.map.BaiduMap;
import com.baidu.mapapi.map.BitmapDescriptor;
import com.baidu.mapapi.map.BitmapDescriptorFactory;
import com.baidu.mapapi.map.MapStatusUpdateFactory;
import com.baidu.mapapi.map.Marker;
import com.baidu.mapapi.map.MarkerOptions;
import com.baidu.mapapi.map.Overlay;
import com.baidu.mapapi.map.Polyline;
import com.baidu.mapapi.map.PolylineOptions;
import com.baidu.mapapi.map.TextureMapView;
import com.baidu.mapapi.map.WidthType;
import com.baidu.mapapi.model.LatLng;
import com.baidu.mapapi.utils.CoordinateConverter;

import org.suixing.app.core.TrackPoint;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/** Owns the Baidu SDK view for one panel. Construct only after opt-in and AK validation. */
final class BaiduTrackMap {
    private static final String TAG = "BaiduTrackMap";
    private static final long LOAD_TIMEOUT_MILLIS = 12_000;
    private static final MapSdkSession SDK_SESSION = new MapSdkSession();

    /** Retains the result of the process request even when every panel has been closed. */
    private static final class ProcessAuthListener implements RequestAuthResultListener {
        private final Handler main = new Handler(Looper.getMainLooper());
        private final MapReadiness.Authorization.Observer result;
        private boolean canceled;

        ProcessAuthListener(MapReadiness.Authorization.Observer result) {
            this.result = result;
        }

        @Override public void onAuthResult(int status, String message) {
            main.post(() -> {
                if (!canceled) {
                    result.onResult(status);
                }
            });
        }

        void cancel() {
            canceled = true;
            release(() -> SDKInitializer.removeAuthResultListener(this));
        }
    }

    private final FrameLayout parent;
    private final Runnable onLoaded;
    private final MapReadiness.FailureListener onFailure;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final MapReadiness readiness;
    private final Runnable loadTimeout;
    private final List<Overlay> route = new ArrayList<>();

    private TextureMapView view;
    private BaiduMap map;
    private CoordinateConverter converter;
    private BitmapDescriptor startIcon;
    private BitmapDescriptor currentIcon;
    private BitmapDescriptor singlePointIcon;
    private Marker startMarker;
    private Marker currentMarker;
    private TrackPoint shownStart;
    private TrackPoint shownCurrent;
    private List<List<TrackPoint>> segments = Collections.emptyList();
    private List<List<TrackPoint>> shownSegments = Collections.emptyList();
    private TrackPoint current;
    private LatLng cameraTarget;
    private boolean follow;
    private boolean previouslyFollowing;
    private boolean closed;

    BaiduTrackMap(FrameLayout parent, Runnable onLoaded, MapReadiness.FailureListener onFailure) {
        this.parent = parent;
        this.onLoaded = onLoaded;
        this.onFailure = onFailure;
        readiness = new MapReadiness(SDK_SESSION.authorization(), this::mapReady, this::fail);
        loadTimeout = readiness::timeout;
    }

    void initialize(String ak) {
        Context app = parent.getContext().getApplicationContext();
        SDK_SESSION.enable(agreed -> SDKInitializer.setAgreePrivacy(app, agreed),
                result -> initializeSdk(app, ak, result));
        readiness.observeAuthorization();
        if (closed) {
            // A cached failure already selected the schematic.
            return;
        }

        view = new TextureMapView(parent.getContext());
        map = Objects.requireNonNull(view.getMap());
        converter = new CoordinateConverter().from(CoordinateConverter.CoordType.GPS);
        startIcon = markerIcon(MapPanel.START_COLOR, 9);
        currentIcon = markerIcon(MapPanel.CURRENT_COLOR, 6);
        singlePointIcon = markerIcon(MapPanel.ROUTE_COLOR, 3);
        map.setOnMapLoadedCallback(() -> main.post(readiness::engineLoaded));
        map.setOnMapRenderValidDataListener((valid, code, message) ->
                main.post(() -> readiness.renderData(valid)));
        parent.addView(view, 0, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
    }

    private static void initializeSdk(Context app, String ak,
                                      MapReadiness.Authorization.Observer result) {
        SDKInitializer.setHttpsEnable(true);
        SDKInitializer.setApiKey(ak);
        SDKInitializer.setCoordType(CoordType.BD09LL);
        ProcessAuthListener listener = new ProcessAuthListener(result);
        SDKInitializer.addAuthResultListener(listener);
        try {
            SDKInitializer.initialize(app);
        } catch (RuntimeException | LinkageError failure) {
            listener.cancel();
            throw failure;
        }
    }

    static void revokePrivacy(Context app) {
        release(() -> SDK_SESSION.withdraw(agreed -> SDKInitializer.setAgreePrivacy(app, agreed)));
    }

    void setTrack(List<List<TrackPoint>> segments, TrackPoint current, boolean follow) {
        this.segments = segments;
        this.current = current;
        this.follow = follow;
        if (readiness.isReady()) {
            render();
        }
    }

    void onResume() {
        try {
            view.onResume();
            if (!readiness.isReady()) {
                main.removeCallbacks(loadTimeout);
                main.postDelayed(loadTimeout, LOAD_TIMEOUT_MILLIS);
            }
        } catch (RuntimeException | LinkageError failure) {
            fail("百度地图恢复失败");
        }
    }

    void onPause() {
        main.removeCallbacks(loadTimeout);
        try {
            view.onPause();
        } catch (RuntimeException | LinkageError failure) {
            fail("百度地图暂停失败");
        }
    }

    void close() {
        closed = true;
        readiness.close();
        main.removeCallbacksAndMessages(null);
        if (map != null) {
            release(map::clear);
        }
        if (view != null) {
            release(view::onDestroy);
        }
        if (map != null) {
            release(() -> map.setOnMapLoadedCallback(null));
            release(() -> map.setOnMapRenderValidDataListener(null));
        }
        if (view != null) {
            release(() -> parent.removeView(view));
        }
        recycle(startIcon);
        recycle(currentIcon);
        recycle(singlePointIcon);
    }

    private void mapReady() {
        main.removeCallbacks(loadTimeout);
        render();
        if (!closed) {
            onLoaded.run();
        }
    }

    private void fail(String reason) {
        if (!closed) {
            onFailure.onFailure(reason);
        }
    }

    private void render() {
        try {
            updateRoute();
            TrackPoint start = segments.isEmpty() ? null : segments.get(0).get(0);
            if (start != shownStart) {
                startMarker = updateMarker(startMarker, start, startIcon, "起点", 4);
                shownStart = start;
            }
            if (current != shownCurrent) {
                currentMarker = updateMarker(currentMarker, current, currentIcon, "当前位置", 5);
                shownCurrent = current;
            }
            updateCamera();
        } catch (RuntimeException | LinkageError failure) {
            fail("百度地图轨迹绘制失败");
        }
    }

    private void updateRoute() {
        for (int i = 0; i < segments.size(); i++) {
            List<TrackPoint> segment = segments.get(i);
            boolean existing = i < shownSegments.size();
            if (existing && segment.equals(shownSegments.get(i))) {
                continue;
            }
            Overlay overlay = existing ? route.get(i) : null;
            if (segment.size() == 1) {
                if (overlay instanceof Polyline) {
                    overlay.remove();
                    overlay = null;
                }
                overlay = updateMarker((Marker) overlay, segment.get(0), singlePointIcon, "", 3);
            } else {
                List<LatLng> positions = new ArrayList<>(segment.size());
                for (TrackPoint point : segment) {
                    positions.add(toMapCoordinate(point));
                }
                if (overlay instanceof Polyline) {
                    ((Polyline) overlay).setPoints(positions);
                } else {
                    if (overlay != null) {
                        overlay.remove();
                    }
                    overlay = Objects.requireNonNull(map.addOverlay(new PolylineOptions()
                            .points(positions).widthType(WidthType.PixelWidth).width(dp(4))
                            .color(MapPanel.ROUTE_COLOR).zIndex(2).clickable(false)));
                }
            }
            if (existing) {
                route.set(i, overlay);
            } else {
                route.add(overlay);
            }
        }
        for (int i = route.size() - 1; i >= segments.size(); i--) {
            route.remove(i).remove();
        }
        shownSegments = segments;
    }

    private Marker updateMarker(Marker marker, TrackPoint point, BitmapDescriptor icon,
                                String title, int zIndex) {
        if (point == null) {
            if (marker != null) {
                marker.remove();
            }
            return null;
        }
        LatLng position = toMapCoordinate(point);
        if (marker != null) {
            marker.setPosition(position);
            return marker;
        }
        return (Marker) Objects.requireNonNull(map.addOverlay(new MarkerOptions()
                .position(position).icon(icon).anchor(0.5f, 0.5f).title(title)
                .zIndex(zIndex).clickable(false)));
    }

    private void updateCamera() {
        LatLng position = currentMarker != null ? currentMarker.getPosition()
                : startMarker == null ? null : startMarker.getPosition();
        if (position != null) {
            if (cameraTarget == null) {
                map.setMapStatus(MapStatusUpdateFactory.newLatLngZoom(position, 17f));
                cameraTarget = position;
            } else if (follow && (!previouslyFollowing || !position.equals(cameraTarget))) {
                map.animateMapStatus(MapStatusUpdateFactory.newLatLng(position), 250);
                cameraTarget = position;
            }
        } else {
            cameraTarget = null;
        }
        previouslyFollowing = follow;
    }

    private LatLng toMapCoordinate(TrackPoint point) {
        return Objects.requireNonNull(converter.coord(
                new LatLng(point.fix.latitude, point.fix.longitude)).convert());
    }

    private BitmapDescriptor markerIcon(int color, int radiusDp) {
        float radius = dp(radiusDp);
        float outline = dp(2);
        int size = (int) Math.ceil(2 * (radius + outline + 1));
        Bitmap bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
        try {
            Canvas canvas = new Canvas(bitmap);
            Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
            paint.setColor(Color.WHITE);
            canvas.drawCircle(size / 2f, size / 2f, radius + outline, paint);
            paint.setColor(color);
            canvas.drawCircle(size / 2f, size / 2f, radius, paint);
            return Objects.requireNonNull(BitmapDescriptorFactory.fromBitmap(bitmap));
        } finally {
            bitmap.recycle();
        }
    }

    private static void recycle(BitmapDescriptor icon) {
        if (icon != null) {
            release(icon::recycle);
        }
    }

    private static void release(Runnable cleanup) {
        try {
            cleanup.run();
        } catch (RuntimeException | LinkageError failure) {
            Log.w(TAG, "Map cleanup failed: " + failure.getClass().getSimpleName());
        }
    }

    private float dp(float length) {
        return length * parent.getResources().getDisplayMetrics().density;
    }
}
