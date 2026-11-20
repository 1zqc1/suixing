package org.suixing.app.vehicle;

import android.content.res.AssetManager;

import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

enum VehicleScenario {
    NORMAL("normal_ready", "待机", "normal.json"),
    SENSOR_OFFLINE("d6_offline", "D6 离线", "sensor-offline.json"),
    BRAKE_LATCHED("brake_latched", "制动锁存", "brake-latched.json");

    final String id;
    final String label;
    private final String file;

    VehicleScenario(String id, String label, String file) {
        this.id = id;
        this.label = label;
        this.file = file;
    }

    static VehicleScenario fromId(String id) {
        for (VehicleScenario scenario : values()) {
            if (scenario.id.equals(id)) return scenario;
        }
        return null;
    }

    VehicleStatus read(AssetManager assets) throws IOException {
        String path = VehicleStatus.DATA_VERSION + "/vehicle-status/" + file;
        try (InputStreamReader input = new InputStreamReader(assets.open(path), StandardCharsets.UTF_8.newDecoder())) {
            VehicleStatus status = VehicleStatusParser.read(input);
            if (status.scenario != null && !id.equals(status.scenario)) {
                throw new IOException("Vehicle status scenario does not match its asset");
            }
            return status;
        }
    }
}
