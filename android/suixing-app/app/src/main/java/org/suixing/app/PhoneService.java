package org.suixing.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import org.suixing.app.core.LocationFix;

public final class PhoneService extends Service implements LocationListener {
    static final String TOKEN = "sessionToken";
    private static final String STOP = "org.suixing.app.STOP";
    private static final String CHANNEL = "phone-tracking";
    private TrackApp app;
    private TrackApp.Run run;
    private LocationManager manager;

    static boolean precise(Context context) {
        return context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }
    static boolean gpsOn(Context context) {
        try {
            LocationManager location = (LocationManager) context.getSystemService(LOCATION_SERVICE);
            return location != null && location.isProviderEnabled(LocationManager.GPS_PROVIDER);
        } catch (RuntimeException e) { return false; }
    }

    @Override public void onCreate() {
        super.onCreate();
        app = (TrackApp) getApplication();
        manager = (LocationManager) getSystemService(LOCATION_SERVICE);
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        TrackApp.Run current = app.active;
        if (intent == null || !app.phoneActive() || app.finishing) {
            stopSelf(startId);
            return START_NOT_STICKY;
        }
        if (intent.getLongExtra(TOKEN, -1) != current.startElapsed) return START_NOT_STICKY;
        if (STOP.equals(intent.getAction())) {
            app.stop("已从通知结束记录", false);
            return START_NOT_STICKY;
        }
        if (run == current) return START_NOT_STICKY;
        run = current;
        if (!app.consent || !precise(this) || !gpsOn(this)) {
            app.stop("精确定位授权或系统 GPS 不可用", true);
            return START_NOT_STICKY;
        }
        try {
            Notification notification = notification();
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
            } else startForeground(1, notification);
            manager.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, this, Looper.getMainLooper());
        } catch (SecurityException e) {
            app.stop("定位权限已撤回或系统不允许前台定位", true);
        } catch (RuntimeException e) {
            app.stop("无法启动前台 GPS，请检查定位权限与系统设置", true);
        }
        return START_NOT_STICKY;
    }
    private Notification notification() {
        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationManager notifications = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            notifications.createNotificationChannel(new NotificationChannel(CHANNEL, "手机轨迹记录",
                    NotificationManager.IMPORTANCE_LOW));
            builder = new Notification.Builder(this, CHANNEL);
        } else builder = new Notification.Builder(this);
        int flags = PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT;
        Intent open = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        Intent end = new Intent(this, PhoneService.class).setAction(STOP).putExtra(TOKEN, run.startElapsed);
        return builder.setSmallIcon(R.drawable.ic_track).setContentTitle("随行正在记录手机轨迹")
                .setContentText("GPS 定位仅保存在本机").setOngoing(true).setOnlyAlertOnce(true)
                .setContentIntent(PendingIntent.getActivity(this, 0, open, flags))
                .addAction(new Notification.Action.Builder(android.R.drawable.ic_media_pause, "结束记录",
                        PendingIntent.getService(this, 1, end, flags)).build()).build();
    }
    @Override public void onLocationChanged(Location loc) {
        if (!app.consent || !precise(this)) { app.stop("定位授权已撤回", true); return; }
        boolean mock = Build.VERSION.SDK_INT >= 31 ? loc.isMock() : loc.isFromMockProvider();
        app.location(run, new LocationFix(loc.getTime(), loc.getElapsedRealtimeNanos() / 1_000_000L,
                loc.getLatitude(), loc.getLongitude(), loc.hasAccuracy() ? loc.getAccuracy() : Double.NaN,
                mock ? "PHONE_GPS_MOCK" : TrackApp.PHONE), SystemClock.elapsedRealtime());
    }
    @Override public void onProviderDisabled(String provider) {
        if (run == app.active && LocationManager.GPS_PROVIDER.equals(provider)) app.stop("系统 GPS 已关闭", true);
    }
    @Override public void onProviderEnabled(String provider) {}
    @Override public void onStatusChanged(String provider, int status, Bundle extras) {}
    @Override public IBinder onBind(Intent intent) { return null; }
    @Override public void onDestroy() {
        try { if (manager != null) manager.removeUpdates(this); } catch (SecurityException ignored) {}
        stopForeground(true);
        if (run != null && run == app.active && !app.finishing) app.stop("定位服务已中断", true);
        super.onDestroy();
    }
}
