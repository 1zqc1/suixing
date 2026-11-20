package org.suixing.app.map;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.Set;

/** Tracks process authorization and waits for usable data from each new map engine. */
final class MapReadiness {
    interface FailureListener {
        void onFailure(String reason);
    }

    /** Main-thread cache. SDK authorization can arrive while there are no panels. */
    static final class Authorization {
        interface Observer {
            void onResult(int status);
        }

        private final Set<Observer> observers = new LinkedHashSet<>();
        private Integer status;

        void observe(Observer observer) {
            if (observers.add(observer) && status != null) {
                observer.onResult(status);
            }
        }

        void remove(Observer observer) {
            observers.remove(observer);
        }

        void update(int status) {
            this.status = status;
            // An observer can close its panel while being notified.
            for (Observer observer : new ArrayList<>(observers)) {
                if (observers.contains(observer)) {
                    observer.onResult(status);
                }
            }
        }
    }

    private final Authorization authorization;
    private final Runnable onReady;
    private final FailureListener onFailure;
    private final Authorization.Observer observer = this::authorizationResult;
    private boolean authorized;
    private boolean engineLoaded;
    private boolean validData;
    private boolean ready;
    private boolean closed;

    MapReadiness(Authorization authorization, Runnable onReady, FailureListener onFailure) {
        this.authorization = authorization;
        this.onReady = onReady;
        this.onFailure = onFailure;
    }

    void observeAuthorization() {
        authorization.observe(observer);
    }

    void engineLoaded() {
        engineLoaded = true;
        checkReady();
    }

    void renderData(boolean valid) {
        validData = valid;
        checkReady();
    }

    boolean isReady() {
        return ready;
    }

    void timeout() {
        if (!ready) {
            fail(authorized ? "百度地图底图加载超时" : "百度地图授权结果等待超时");
        }
    }

    void close() {
        closed = true;
        authorization.remove(observer);
    }

    private void authorizationResult(int status) {
        if (status == 0) {
            authorized = true;
            checkReady();
        } else {
            fail("百度地图授权失败（错误码 " + status + "）");
        }
    }

    private void checkReady() {
        if (!closed && !ready && authorized && engineLoaded && validData) {
            ready = true;
            onReady.run();
        }
    }

    private void fail(String reason) {
        if (!closed) {
            close();
            onFailure.onFailure(reason);
        }
    }
}
