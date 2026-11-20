# Android B1/B2 Implementation Plan

> **For agentic workers:** use subagent-driven-development for scoped implementation and review. Execute continuously within the user-approved B1/B2 scope.

**Goal:** installable Chinese Android app with real-time/simulated tracks and local replay.
**Architecture:** pure Java track core, SQLite persistence, foreground phone-location service, consent-gated Baidu map adapter and honest schematic fallback.
**Tech Stack:** Java17 source, JDK21, AGP8.9.2, Gradle8.11.1, SDK35, BaiduMapSDK_Map9.0.0.
**Spec:** docs/superpowers/specs/2026-11-20-android-live-track-design.md

## Global Constraints
No vehicle command or cloud upload; no invented live telemetry. AK absent must remain usable and visibly schematic. Map SDK initialization only after consent and AK configured. WGS84 storage, BD09LL rendering conversion. Preserve existing baseline. Work on feat/android-b1-b2-live-track; no remote push.

### Task 0: GitHub examples and development tools (complete)
User requested this before app implementation. Compared Android platform-samples, BaiduMapTrace and YunMap. Installed and locally verified mobile-next/mobile-mcp 1.0.18; configured suixing_mobile in Codex with local-device tools. Installed Google android/skills permission, testing, edge-to-edge and ANR audit skills pinned to c72942584fff970dac86ced78b367fce0c441e52. See docs/android-github-tooling.md for evidence and application boundaries.

### Task 1: Track domain and unit tests
Files under android/suixing-app/app/src/main/java/org/suixing/app/core and corresponding src/test.
Write tests first, observe intended failure, implement, then run testDebugUnitTest. Commit only owned files.
Interfaces:
- LocationFix(long epochMillis,long elapsedMillis,double latitude,double longitude,double accuracyMeters,String source), final fields with those names.
- TrackPoint(long sequence,int segment,LocationFix fix), final fields sequence/segment/fix.
- TrackFilter.evaluate(LocationFix fix,long nowElapsedMillis) -> Result with public status, point, reason and isAccepted(); reset().
- TrackFilter.Status ACCEPTED, INVALID, INACCURATE, STALE, OUT_OF_ORDER, JUMP, NO_MOVEMENT.
- TrackMetrics.distanceMeters(List<TrackPoint>), durationMillis(List<TrackPoint>), static haversineMeters(double,double,double,double).
Rules: reject nonfinite/out-of-range coordinate or accuracy<=0; accuracy>80; age>15000ms or future>1000ms; elapsed<=last accepted. Rejected fixes never advance last accepted. Gap>20000ms accepts into new segment with jump baseline reset. Otherwise reject distance greater than max(12*dtSeconds,3*(previousAccuracy+accuracy)+10). Optional jitter threshold max(1.5,accuracy*0.3). Accepted sequence starts1, segment starts0. Distance sums only within same segment; durations use elapsed, never epoch.
Tests include valid demo path, NaN/range, stale/future, poor accuracy, duplicate/order, jump recovery, gap segmentation, cross-segment metrics and wall-clock changes.

### Task 2: Map rendering adapter
Own map/ classes; no Activity/store/service changes.
Public MapPanel extends FrameLayout: constructor(Context,boolean privacyAgreed); setTrack(List<TrackPoint>,TrackPoint current,boolean follow); setModeLabel(String); onResume/onPause/onDestroy; getStatusText().
Use BuildConfig.BAIDU_MAP_AK. Missing AK or declined consent must not call Baidu SDK; render clearly labeled schematic with north arrow/grid/route/start/current markers. Preserve separate segments.
With configured AK, setAgreePrivacy before initialize, HTTPS enabled, BD09LL display and official CoordinateConverter GPS conversion. Update current marker and per-segment polylines; follow camera on demand. Auth/native failures must be visible and degrade without crash. No fabricated map labels/roads. Fixed SDK dependency9.0.0.

### Task 3: Activity, persistence and phone location
Parent owns all remaining app classes, XML, assets and build config.
Implement SQLite per-session point persistence and interrupted-session recovery; app-level tracking state survives Activity recreation. GPS foreground service starts after precise permission and consent, uses monotonic timestamp and accuracy, stops/unregisters on end. Demo timer does not ask for location; source DEMO explicit.
Chinese UI includes source switch, start/stop, follow-location, status/metrics, history selector/replay, JSONL export. Controls disabled or explained while recording. Runtime location denial does not break demo. Offline state distinguishes map availability from ongoing local GPS recording. Preview-only read-only risk contract documented.

### Task 4: Verification and delivery
Run unit tests, assembleDebug, clean offline rebuild; sign/report SHA1. On emulator install org.suixing.app, verify demo grows, stop persists, history replays, process restart retains history; exercise location permission denial and synthetic GPS if supported. Capture screenshot/recording. Broad code review of state lifecycle, consent, persistence and timestamps; fix important findings.
Write README, AK setup/package/signature instructions, regression cases/results and remaining real-phone/AK limits. Commit only project/spec/doc changes; leave remote unchanged.
