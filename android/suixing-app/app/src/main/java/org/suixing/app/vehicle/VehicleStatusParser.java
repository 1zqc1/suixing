package org.suixing.app.vehicle;

import com.google.gson.Strictness;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;

import java.io.IOException;
import java.io.Reader;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;
import java.util.regex.Pattern;

import org.suixing.app.vehicle.VehicleStatus.BrakeFeedback;
import org.suixing.app.vehicle.VehicleStatus.Reason;
import org.suixing.app.vehicle.VehicleStatus.SensorHealth;
import org.suixing.app.vehicle.VehicleStatus.SystemState;

final class VehicleStatusParser {
    private static final Pattern UTC = Pattern.compile("[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?Z");
    private static final int MAX_IGNORED_CONTAINER_DEPTH = 32;

    private VehicleStatusParser() {}

    static VehicleStatus read(Reader input) throws IOException {
        JsonReader json = new JsonReader(input);
        json.setStrictness(Strictness.STRICT);
        if (json.peek() != JsonToken.BEGIN_OBJECT) throw new IOException("Expected a vehicle status object");
        String version = null, source = null, scenario = null, sampleTime = null;
        Boolean motionPermitted = null, estopActive = null, brakeRequested = null;
        SystemState system = null;
        BrakeFeedback feedback = null;
        SensorHealth d6 = null, stereo = null;
        Reason reason = null;

        Set<String> seen = new HashSet<>();
        json.beginObject();
        while (json.hasNext()) {
            switch (nextUniqueName(json, seen)) {
                case "schema_version" -> version = readString(json);
                case "source" -> source = readString(json);
                case "scenario" -> scenario = readString(json);
                case "sample_time_utc" -> sampleTime = readString(json);
                case "system_state" -> system = readEnum(json, SystemState.class);
                case "motion_permitted" -> motionPermitted = readBoolean(json);
                case "estop_active" -> estopActive = readBoolean(json);
                case "brake_requested" -> brakeRequested = readBoolean(json);
                case "brake_feedback" -> feedback = readEnum(json, BrakeFeedback.class);
                case "sensors" -> {
                    if (json.peek() != JsonToken.BEGIN_OBJECT) {
                        discardValue(json);
                        break;
                    }
                    Set<String> seenSensors = new HashSet<>();
                    json.beginObject();
                    while (json.hasNext()) {
                        switch (nextUniqueName(json, seenSensors)) {
                            case "d6" -> d6 = readEnum(json, SensorHealth.class);
                            case "stereo" -> stereo = readEnum(json, SensorHealth.class);
                            default -> discardValue(json);
                        }
                    }
                    json.endObject();
                }
                case "reason_code" -> reason = readEnum(json, Reason.class);
                default -> discardValue(json);
            }
        }
        json.endObject();
        if (json.peek() != JsonToken.END_DOCUMENT) throw new IOException("Unexpected data after vehicle status");
        if (!VehicleStatus.SCHEMA_VERSION.equals(version) || !VehicleStatus.SOURCE.equals(source)) {
            throw new IOException("Unsupported vehicle status version or source");
        }
        VehicleScenario knownScenario = VehicleScenario.fromId(scenario);
        return new VehicleStatus(knownScenario == null ? null : knownScenario.id, validatedUtc(sampleTime),
                system, motionPermitted, estopActive, brakeRequested, feedback, d6, stereo, reason);
    }

    private static String nextUniqueName(JsonReader json, Set<String> seen) throws IOException {
        String name = json.nextName();
        if (!seen.add(name)) throw new IOException("Repeated field in vehicle status");
        return name;
    }

    private static String readString(JsonReader json) throws IOException {
        if (json.peek() == JsonToken.STRING) return json.nextString();
        discardValue(json);
        return null;
    }

    private static Boolean readBoolean(JsonReader json) throws IOException {
        if (json.peek() == JsonToken.BOOLEAN) return json.nextBoolean();
        discardValue(json);
        return null;
    }

    private static void discardValue(JsonReader json) throws IOException {
        // Gson 2.11's skipValue omits strict control-character checks on quoted names and strings.
        int depth = 0;
        do {
            JsonToken token = json.peek();
            switch (token) {
                case BEGIN_ARRAY, BEGIN_OBJECT -> {
                    if (depth == MAX_IGNORED_CONTAINER_DEPTH) throw new IOException("Vehicle status nesting is too deep");
                    if (token == JsonToken.BEGIN_ARRAY) json.beginArray();
                    else json.beginObject();
                    depth++;
                }
                case END_ARRAY -> {
                    json.endArray();
                    depth--;
                }
                case END_OBJECT -> {
                    json.endObject();
                    depth--;
                }
                case NAME -> json.nextName();
                case STRING, NUMBER -> json.nextString();
                case BOOLEAN -> json.nextBoolean();
                case NULL -> json.nextNull();
                default -> throw new IOException("Incomplete vehicle status value");
            }
        } while (depth > 0);
    }

    private static <E extends Enum<E>> E readEnum(JsonReader json, Class<E> type) throws IOException {
        String value = readString(json);
        if (value == null) return null;
        try {
            return Enum.valueOf(type, value);
        } catch (IllegalArgumentException unknown) {
            return null;
        }
    }

    private static String validatedUtc(String value) {
        if (value == null || !UTC.matcher(value).matches()) return null;
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.ROOT);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        format.setLenient(false);
        return format.parse(value, new ParsePosition(0)) == null ? null : value;
    }
}
