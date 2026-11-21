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
Actual artifact audit: CoordinateConverter is in the separate official BaiduMapSDK_Util:9.0.0 component (Map/base/common lack it). Add that one dependency to app/build.gradle as part of this task. On explicit consent withdrawal, Activity may call public static MapPanel.revokeSdkPrivacy(Context), which touches the SDK only if this adapter previously initialized it; destroy existing MapPanel first. Normal Activity destruction must not revoke global consent for another recreated panel.

### Task 3: Activity, persistence and phone location
Parent owns all remaining app classes, XML, assets and build config.
Implement SQLite per-session point persistence and interrupted-session recovery; app-level tracking state survives Activity recreation. GPS foreground service starts after precise permission and consent, uses monotonic timestamp and accuracy, stops/unregisters on end. Demo timer does not ask for location; source DEMO explicit.
Chinese UI includes source switch, start/stop, follow-location, status/metrics, history selector/replay, JSONL export. Controls disabled or explained while recording. Runtime location denial does not break demo. Offline state distinguishes map availability from ongoing local GPS recording. Preview-only read-only risk contract documented.

### Task 4: Verification and delivery
Depends on user-added Task5. Final whole-branch review and deliverable packaging occur after M1 B page integration.
Run unit tests, assembleDebug, clean offline rebuild; sign/report SHA1. On emulator install org.suixing.app, verify demo grows, stop persists, history replays, process restart retains history; exercise location permission denial and synthetic GPS if supported. Capture screenshot/recording. Broad code review of state lifecycle, consent, persistence and timestamps; fix important findings.
Write README, AK setup/package/signature instructions, regression cases/results and remaining real-phone/AK limits. Commit only project/spec/doc changes; leave remote unchanged.

### Task 5: User handoff M1 — B read-only vehicle status and regression
User supplied m1-handoff-v0.1 folder and README(2).md and explicitly requested continuing their teammateB tasks. Read the new spec section; implement the three independent JSON scenarios as an honest local mock-status page linked from the existing app.

Authoritative input folder: D:/xwechat_files/wxid_vhwsqgr6pe3122_5f84/msg/file/2026-11/m1-handoff-v0.1(1)/m1-handoff-v0.1. Parent audited verify.py and checked every manifest path/hash, then ran it: PASS SHA-256,3 D6 rows,2 stereo pairs,3 vehicle statuses,2 risk cases. Preserve fixture bytes.

Own new vehicle/ model/parser/presentation/Activity or component, exact fixtures under assets/m1-handoff-v0.1/vehicle-status/, AndroidManifest activity entry and a small MainActivity entry; app README/docs and targeted host/device tests. Preserve tracking core/map/service/store behavior and existing tests. Work after Task3 fixes pass; do not mix into that fix commit.

Display all fields from schema0.1: source mock, scenario, sample_time_utc (synthetic display only), system_state, motion_permitted, estop_active, brake_requested, brake_feedback, sensors.d6/stereo, reason_code. Normal: READY, no motion permission, no brake request, RELEASED, sensors ONLINE. Offline: FAULT_SAFE, D6 OFFLINE, requested true, feedback UNKNOWN and explicitly not confirmed applied, no motion permission. Latched: BRAKE_LATCHED, requested true, feedback APPLIED and explicitly confirmed applied, no motion permission. Source/version/no-real-vehicle labels always visible. Independent scenarios must not carry prior state into next selection.

Strict boolean/enum/schema handling: missing/invalid/unknown input shows unknown or clear unsupported-data state; never silently coerce strings to booleans or infer positive/confirmed states. No control command, transport connection, ROS processing, live risk fusion or fabricated vehicle online status. New page usable without map AK or phone permission. Prefer dedicated simple scrollable Activity with private exported=false entry, accessible48dp controls and system insets; navigation must preserve phone recording. If demo stop-on-leave applies, make resulting saved state honest.

Tests first for meaningful state/parser semantics. Real Android JSON parser behavior may be tested using existing device runner; pure presentation/validation logic can be JVM tested without broad dependency additions. Cover3 original fixtures, request-vs-feedback distinction, READY+motion=false, independent switching, invalid booleans and unknown/malformed data. Capture3 UI states on emulator after implementation. Handoff report includes data version, SHA256, code commit, command, expected/actual and evidence paths. Commit scoped changes locally, no push.
