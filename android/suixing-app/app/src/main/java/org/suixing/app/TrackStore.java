package org.suixing.app;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;
import android.util.JsonWriter;
import org.suixing.app.core.LocationFix;
import org.suixing.app.core.TrackPoint;
import java.io.IOException;
import java.io.Writer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Owned by the recorder's serial worker. Each accepted sample commits before publication. */
final class TrackStore extends SQLiteOpenHelper {
    static final class Session {
        final long id, started;
        final Long ended;
        final String source, status;
        final int count;
        final boolean mock;

        Session(Cursor row) {
            id = row.getLong(0);
            started = row.getLong(1);
            ended = row.isNull(2) ? null : row.getLong(2);
            source = row.getString(3);
            status = row.getString(4);
            count = row.getInt(5);
            mock = row.getInt(6) != 0;
        }
    }

    TrackStore(Context context, String name) { super(context, name, null, 1); }

    @Override public void onConfigure(SQLiteDatabase db) { db.setForeignKeyConstraintsEnabled(true); }

    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE sessions(id INTEGER PRIMARY KEY, start_ms INTEGER NOT NULL,"
                + "end_ms INTEGER, source TEXT NOT NULL, status TEXT NOT NULL)");
        db.execSQL("CREATE TABLE points(session_id INTEGER NOT NULL REFERENCES sessions(id),"
                + "seq INTEGER NOT NULL, segment INTEGER NOT NULL, utc_ms INTEGER NOT NULL,"
                + "elapsed_ms INTEGER NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,"
                + "accuracy REAL NOT NULL, source TEXT NOT NULL, PRIMARY KEY(session_id,seq))");
    }
    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        throw new IllegalStateException("不支持的轨迹数据库版本");
    }
    void recover() {
        getWritableDatabase().execSQL("UPDATE sessions SET status='INTERRUPTED' WHERE status='ACTIVE'");
    }

    long begin(String source, long now) {
        ContentValues values = new ContentValues();
        values.put("start_ms", now);
        values.put("source", source);
        values.put("status", "ACTIVE");
        return getWritableDatabase().insertOrThrow("sessions", null, values);
    }

    void append(long id, TrackPoint point) {
        LocationFix fix = point.fix;
        ContentValues values = new ContentValues();
        values.put("session_id", id);
        values.put("seq", point.sequence);
        values.put("segment", point.segment);
        values.put("utc_ms", fix.epochMillis);
        values.put("elapsed_ms", fix.elapsedMillis);
        values.put("lat", fix.latitude);
        values.put("lon", fix.longitude);
        values.put("accuracy", fix.accuracyMeters);
        values.put("source", fix.source);
        getWritableDatabase().insertOrThrow("points", null, values);
    }

    void finish(long id, String status, long end) {
        ContentValues values = new ContentValues();
        values.put("status", status);
        values.put("end_ms", end);
        if (getWritableDatabase().update("sessions", values, "id=? AND status='ACTIVE'", args(id)) != 1) {
            throw new IllegalStateException("记录状态已改变");
        }
    }

    private static String[] args(long id) { return new String[]{Long.toString(id)}; }

    List<Session> history() {
        List<Session> result = new ArrayList<>();
        String sql = "SELECT s.id,start_ms,end_ms,s.source,status,COUNT(p.seq),"
                + "MAX(CASE WHEN p.source='PHONE_GPS_MOCK' THEN 1 ELSE 0 END) "
                + "FROM sessions s LEFT JOIN points p ON s.id=p.session_id "
                + "WHERE status!='ACTIVE' GROUP BY s.id ORDER BY s.id DESC";
        try (Cursor cursor = getReadableDatabase().rawQuery(sql, null)) {
            while (cursor.moveToNext()) result.add(new Session(cursor));
        }
        return Collections.unmodifiableList(result);
    }

    private Cursor pointRows(long id) {
        return getReadableDatabase().rawQuery("SELECT seq,segment,utc_ms,elapsed_ms,lat,lon,accuracy,source "
                + "FROM points WHERE session_id=? ORDER BY seq", args(id));
    }

    private static TrackPoint point(Cursor row) {
        return new TrackPoint(row.getLong(0), row.getInt(1), new LocationFix(row.getLong(2),
                row.getLong(3), row.getDouble(4), row.getDouble(5), row.getDouble(6), row.getString(7)));
    }

    List<TrackPoint> points(long id) {
        List<TrackPoint> result = new ArrayList<>();
        try (Cursor row = pointRows(id)) {
            while (row.moveToNext()) result.add(point(row));
        }
        return Collections.unmodifiableList(result);
    }

    void writeJsonl(Session session, Writer out) throws IOException {
        JsonWriter header = new JsonWriter(out);
        header.beginObject().name("schema").value("suixing.track.v1").name("type").value("session")
                .name("sessionId").value(session.id).name("source").value(session.source)
                .name("status").value(session.status).name("coordinateSystem").value("WGS84")
                .name("startedEpochMillis").value(session.started).name("endedEpochMillis").value(session.ended)
                .name("pointCount").value(session.count).endObject();
        out.write('\n');
        try (Cursor row = pointRows(session.id)) {
            while (row.moveToNext()) {
                TrackPoint p = point(row);
                JsonWriter json = new JsonWriter(out);
                json.beginObject().name("type").value("point").name("sessionId").value(session.id)
                        .name("sequence").value(p.sequence).name("segment").value(p.segment)
                        .name("epochMillis").value(p.fix.epochMillis)
                        .name("elapsedMillis").value(p.fix.elapsedMillis)
                        .name("coordinateSystem").value("WGS84")
                        .name("latitude").value(p.fix.latitude).name("longitude").value(p.fix.longitude)
                        .name("accuracyMeters").value(p.fix.accuracyMeters)
                        .name("source").value(p.fix.source).endObject();
                out.write('\n');
            }
        }
    }
}
