package org.suixing.app.map;

/** Main-thread owner of the SDK's process authorization and applied consent. */
final class MapSdkSession {
    interface PrivacyMode {
        void setAgreed(boolean agreed);
    }

    interface Startup {
        void initialize(MapReadiness.Authorization.Observer onAuthorization);
    }

    private final MapReadiness.Authorization authorization = new MapReadiness.Authorization();
    private boolean initialized;
    private boolean consentApplied;

    MapReadiness.Authorization authorization() {
        return authorization;
    }

    void enable(PrivacyMode privacy, Startup startup) {
        if (!consentApplied) {
            privacy.setAgreed(true);
            consentApplied = true;
        }
        if (!initialized) {
            startup.initialize(authorization::update);
            initialized = true;
        }
    }

    void withdraw(PrivacyMode privacy) {
        if (consentApplied) {
            privacy.setAgreed(false);
            consentApplied = false;
        }
    }
}
