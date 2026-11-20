#include <stdio.h>
#include "esp_log.h"
#include "esp_psram.h"
#include "esp_wn_models.h"
#include "esp_mn_models.h"
#include "model_path.h"

void app_main(void)
{
    const char *tag = "suixing_sr";
    srmodel_list_t *models = esp_srmodel_init("model");
    if (models == NULL) {
        ESP_LOGE(tag, "Speech model partition could not be loaded");
        return;
    }
    char *wake_model = esp_srmodel_filter(models, ESP_WN_PREFIX, NULL);
    char *command_model = esp_srmodel_filter(models, ESP_MN_PREFIX, NULL);
    if (wake_model == NULL || command_model == NULL) {
        ESP_LOGE(tag, "WakeNet or MultiNet model missing from partition");
        esp_srmodel_deinit(models);
        return;
    }
    if (esp_wn_handle_from_name(wake_model) == NULL ||
        esp_mn_handle_from_name(command_model) == NULL) {
        ESP_LOGE(tag, "Could not resolve both speech model interfaces");
        esp_srmodel_deinit(models);
        return;
    }
    ESP_LOGI(tag, "WakeNet=%s MultiNet=%s PSRAM=%zu bytes",
             wake_model, command_model, esp_psram_get_size());
    esp_srmodel_deinit(models);
}
