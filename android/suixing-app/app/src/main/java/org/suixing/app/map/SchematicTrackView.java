package org.suixing.app.map;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.util.TypedValue;
import android.view.View;

import org.suixing.app.core.TrackPoint;

import java.util.Collections;
import java.util.List;

/** Draws only the supplied coordinates and reference grid. */
final class SchematicTrackView extends View {
    private static final int GRID_COLOR = 0xffd7e3ec;
    private static final int TEXT_COLOR = 0xff354b62;

    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Path path = new Path();
    private final float density;
    private final float labelSize;
    private List<List<TrackPoint>> segments = Collections.emptyList();
    private TrackPoint current;

    SchematicTrackView(Context context) {
        super(context);
        density = getResources().getDisplayMetrics().density;
        labelSize = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, 13,
                getResources().getDisplayMetrics());
        setBackgroundColor(0xfff1f7fb);
        setContentDescription("轨迹示意图");
        paint.setStrokeCap(Paint.Cap.ROUND);
        paint.setStrokeJoin(Paint.Join.ROUND);
    }

    void setTrack(List<List<TrackPoint>> segments, TrackPoint current) {
        this.segments = segments;
        this.current = current;
        invalidate();
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        drawGrid(canvas);
        float top = Math.min(dp(72), getHeight() * 0.35f);
        drawNorthArrow(canvas, getWidth() - dp(24), top);

        float left = dp(22);
        float width = Math.max(0, getWidth() - 2 * left);
        float height = Math.max(0, getHeight() - top - dp(45));
        if (segments.isEmpty() && current == null) {
            label(canvas, "等待轨迹点", getWidth() / 2f, top + height / 2,
                    Paint.Align.CENTER);
            return;
        }

        TrackRenderGeometry.Projection projection =
                TrackRenderGeometry.Projection.fit(segments, current, width, height);
        canvas.save();
        canvas.translate(left, top);
        drawRoute(canvas, projection);
        if (!segments.isEmpty()) {
            TrackPoint start = segments.get(0).get(0);
            point(canvas, (float) projection.x(start), (float) projection.y(start),
                    dp(9), MapPanel.START_COLOR);
        }
        if (current != null) {
            point(canvas, (float) projection.x(current), (float) projection.y(current),
                    dp(6), MapPanel.CURRENT_COLOR);
        }
        canvas.restore();
        drawLegend(canvas);
    }

    private void drawGrid(Canvas canvas) {
        paint.setColor(GRID_COLOR);
        paint.setStrokeWidth(dp(1));
        float spacing = dp(32);
        for (float x = spacing / 2; x < getWidth(); x += spacing) {
            canvas.drawLine(x, 0, x, getHeight(), paint);
        }
        for (float y = spacing / 2; y < getHeight(); y += spacing) {
            canvas.drawLine(0, y, getWidth(), y, paint);
        }
    }

    private void drawNorthArrow(Canvas canvas, float x, float y) {
        label(canvas, "北", x, y - dp(21), Paint.Align.CENTER);
        paint.setStrokeWidth(dp(2));
        canvas.drawLine(x, y - dp(15), x, y + dp(2), paint);
        canvas.drawLine(x, y - dp(15), x - dp(5), y - dp(9), paint);
        canvas.drawLine(x, y - dp(15), x + dp(5), y - dp(9), paint);
    }

    private void drawRoute(Canvas canvas, TrackRenderGeometry.Projection projection) {
        path.rewind();
        paint.setColor(MapPanel.ROUTE_COLOR);
        for (List<TrackPoint> segment : segments) {
            TrackPoint first = segment.get(0);
            float x = (float) projection.x(first);
            float y = (float) projection.y(first);
            if (segment.size() == 1) {
                canvas.drawCircle(x, y, dp(3), paint);
            } else {
                path.moveTo(x, y);
                for (int i = 1; i < segment.size(); i++) {
                    TrackPoint point = segment.get(i);
                    path.lineTo((float) projection.x(point), (float) projection.y(point));
                }
            }
        }
        paint.setStyle(Paint.Style.STROKE);
        paint.setStrokeWidth(dp(4));
        canvas.drawPath(path, paint);
        paint.setStyle(Paint.Style.FILL);
    }

    private void drawLegend(Canvas canvas) {
        float x = dp(18);
        float y = getHeight() - dp(18);
        if (!segments.isEmpty()) {
            point(canvas, x, y, dp(4), MapPanel.START_COLOR);
            label(canvas, "起点", x + dp(10), y + labelSize / 3, Paint.Align.LEFT);
            x += dp(24) + paint.measureText("起点");
        }
        if (current != null) {
            point(canvas, x, y, dp(4), MapPanel.CURRENT_COLOR);
            label(canvas, "当前位置", x + dp(10), y + labelSize / 3, Paint.Align.LEFT);
        }
    }

    private void point(Canvas canvas, float x, float y, float radius, int color) {
        paint.setColor(Color.WHITE);
        canvas.drawCircle(x, y, radius + dp(2), paint);
        paint.setColor(color);
        canvas.drawCircle(x, y, radius, paint);
    }

    private void label(Canvas canvas, String label, float x, float y, Paint.Align alignment) {
        paint.setColor(TEXT_COLOR);
        paint.setTextSize(labelSize);
        paint.setTextAlign(alignment);
        canvas.drawText(label, x, y, paint);
    }

    private float dp(float value) {
        return value * density;
    }
}
