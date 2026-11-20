package org.suixing.app.map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class MapReadinessTest {
    @Test public void replacementReceivesCachedAuthorizationFailure() {
        MapReadiness.Authorization authorization = new MapReadiness.Authorization();
        List<String> first = new ArrayList<>();
        MapReadiness panel = observe(authorization, first);
        authorization.update(230);
        panel.close();

        List<String> second = new ArrayList<>();
        MapReadiness replacement = observe(authorization, second);
        replacement.engineLoaded();
        replacement.renderData(true);

        List<String> failure = Collections.singletonList("百度地图授权失败（错误码 230）");
        assertEquals(failure, first);
        assertEquals(failure, second);
    }

    @Test public void outcomesArrivingBetweenPanelsAreReplayed() {
        MapReadiness.Authorization authorization = new MapReadiness.Authorization();
        List<String> first = new ArrayList<>();
        observe(authorization, first).close();
        authorization.update(230);
        List<String> second = new ArrayList<>();

        observe(authorization, second);

        assertTrue(first.isEmpty());
        assertEquals(Collections.singletonList("百度地图授权失败（错误码 230）"), second);
    }

    @Test public void engineLoadAndSuccessfulAuthorizationStillNeedUsableData() {
        MapReadiness.Authorization authorization = new MapReadiness.Authorization();
        List<String> events = new ArrayList<>();
        MapReadiness panel = observe(authorization, events);
        panel.engineLoaded();
        authorization.update(0);
        panel.renderData(false);
        assertTrue(events.isEmpty());

        panel.renderData(true);
        panel.renderData(true);
        panel.timeout();

        assertEquals(Collections.singletonList("ready"), events);
    }

    @Test public void validDataAndEngineLoadWaitForAuthorization() {
        MapReadiness.Authorization authorization = new MapReadiness.Authorization();
        List<String> events = new ArrayList<>();
        MapReadiness panel = observe(authorization, events);
        panel.renderData(true);
        panel.engineLoaded();
        assertTrue(events.isEmpty());

        authorization.update(0);
        authorization.update(230);

        assertEquals(Arrays.asList("ready", "百度地图授权失败（错误码 230）"), events);
    }

    @Test public void missingAuthorizationTimesOutAndIgnoresLateSuccess() {
        MapReadiness.Authorization authorization = new MapReadiness.Authorization();
        List<String> events = new ArrayList<>();
        MapReadiness panel = observe(authorization, events);
        panel.engineLoaded();
        panel.renderData(true);

        panel.timeout();
        authorization.update(0);

        assertEquals(Collections.singletonList("百度地图授权结果等待超时"), events);
    }

    @Test public void authorizedEngineWithNoValidDataReportsLoadTimeout() {
        MapReadiness.Authorization authorization = new MapReadiness.Authorization();
        authorization.update(0);
        List<String> events = new ArrayList<>();
        MapReadiness panel = observe(authorization, events);
        panel.engineLoaded();

        panel.timeout();
        panel.renderData(true);

        assertEquals(Collections.singletonList("百度地图底图加载超时"), events);
    }

    @Test public void removedAuthorizationObserverReceivesNoFutureResults() {
        MapReadiness.Authorization authorization = new MapReadiness.Authorization();
        List<Integer> statuses = new ArrayList<>();
        MapReadiness.Authorization.Observer observer = statuses::add;
        authorization.observe(observer);
        authorization.update(0);

        authorization.remove(observer);
        authorization.update(230);

        assertEquals(Collections.singletonList(0), statuses);
    }

    private static MapReadiness observe(MapReadiness.Authorization authorization, List<String> events) {
        MapReadiness panel = new MapReadiness(authorization, () -> events.add("ready"), events::add);
        panel.observeAuthorization();
        return panel;
    }
}
