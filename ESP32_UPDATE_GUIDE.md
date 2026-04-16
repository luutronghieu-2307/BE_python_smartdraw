"""
HƯỚNG DẪN CẬP NHẬT CODE ESP32 ĐỂ HỖ TRỢ DRAWER SYNC

ESP32 hiện tại đã có:
- Nhận lệnh ON/OFF từ sviot/detection
- Gửi trạng thái "ON"/"OFF" lên sviot/status

Để hoàn toàn hỗ trợ drawer sync với server mới, cần cập nhật:
"""

# ============================================================================
# 1. MQTT TOPICS - CẬP NHẬT SUB/PUB
# ============================================================================

# CŨNG (chỉ subscribe sviot/detection):
#define MQTT_SUB_TOPIC              "sviot/detection"
#define MQTT_PUB_TOPIC              "sviot/status"

# MỚI (subscribe cả sviot/drawer/command):
#define MQTT_SUB_TOPIC_DETECTION    "sviot/detection"
#define MQTT_SUB_TOPIC_DRAWER_CMD   "sviot/drawer/command"      // [MỚI]
#define MQTT_PUB_TOPIC_STATUS       "sviot/drawer/status"       // [CẬP NHẬT]
#define MQTT_PUB_TOPIC_HEALTH       "sviot/drawer/health"       // [MỚI]


# ============================================================================
# 2. MQTT EVENT HANDLER - CẬP NHẬT XỬ LÝ TOPICS
# ============================================================================

# CŨNG:
mqtt_event_handler(event) {
    if (MQTT_EVENT_CONNECTED):
        esp_mqtt_client_subscribe(client, MQTT_SUB_TOPIC, 0);
    
    if (MQTT_EVENT_DATA):
        if (strstr(event->data, "\"status\": \"ON\""))
            mqtt_command = 1
        else if (strstr(event->data, "\"status\": \"OFF\""))
            mqtt_command = 0

# MỚI - Cần kiểm tra từng topic:
mqtt_event_handler(event) {
    if (MQTT_EVENT_CONNECTED):
        esp_mqtt_client_subscribe(client, MQTT_SUB_TOPIC_DETECTION, 0);           // sviot/detection
        esp_mqtt_client_subscribe(client, MQTT_SUB_TOPIC_DRAWER_CMD, 0);          // sviot/drawer/command [MỚI]

    if (MQTT_EVENT_DATA):
        // Phân biệt topic
        if (strcmp(event->topic, MQTT_SUB_TOPIC_DETECTION) == 0) {
            // Logic cũ: parse "status": "ON"/"OFF"
            if (strstr(event->data, "\"status\": \"ON\""))
                mqtt_command = 1;
            else if (strstr(event->data, "\"status\": \"OFF\""))
                mqtt_command = 0;
        }
        else if (strcmp(event->topic, MQTT_SUB_TOPIC_DRAWER_CMD) == 0) {
            // [MỚI] Parse lệnh từ server
            // Payload: {"status": "ON|OFF", "timestamp": ..., "command": "open|close"}
            if (strstr(event->data, "\"command\": \"open\"") || strstr(event->data, "\"status\": \"ON\""))
                mqtt_command = 1;      // Open
            else if (strstr(event->data, "\"command\": \"close\"") || strstr(event->data, "\"status\": \"OFF\""))
                mqtt_command = 0;      // Close
        }


# ============================================================================
# 3. PUBLISH STATUS - CẬP NHẬT FORMAT + TOPIC
# ============================================================================

# CŨNG (publish tới sviot/status):
esp_mqtt_client_publish(client, MQTT_PUB_TOPIC, "{\"status\": \"ON\"}", 0, 1, 0);
esp_mqtt_client_publish(client, MQTT_PUB_TOPIC, "{\"status\": \"OFF\"}", 0, 1, 0);

# MỚI - Thêm timestamp + publish tới sviot/drawer/status:
char payload[256];
time_t now = time(NULL);
snprintf(payload, sizeof(payload), 
    "{\"status\": \"%s\", \"timestamp\": %ld}",
    is_drawer_open ? "ON" : "OFF",
    (long)now
);
esp_mqtt_client_publish(client, MQTT_PUB_TOPIC_STATUS, payload, 0, 1, 0);


# ============================================================================
# 4. HEARTBEAT TASK - [MỚI] GỬITRẠNG THÁI ĐỊNH KỲ
# ============================================================================

void drawer_health_task(void *pvParameters) {
    while (1) {
        // Gửi heartbeat mỗi 10 giây
        char payload[256];
        time_t now = time(NULL);
        uint16_t distance = vl53l0x_get_distance_mm();
        
        snprintf(payload, sizeof(payload),
            "{\"ts\": %ld, \"distance\": %u}",
            (long)now,
            distance
        );
        
        esp_mqtt_client_publish(client, MQTT_PUB_TOPIC_HEALTH, payload, 0, 1, 0);
        
        vTaskDelay(pdMS_TO_TICKS(10000)); // 10 giây
    }
}

// Trong app_main():
xTaskCreate(drawer_health_task, "health_task", 2048, NULL, 4, NULL);


# ============================================================================
# 5. LOGIC ĐIỀU KHIỂN - KHÔNG THAY ĐỔI NHIỀU
# ============================================================================

# Flow hiện tại vẫn đúng:
# 1. Nhận mqtt_command (từ sviot/detection hoặc sviot/drawer/command)
# 2. Kiểm tra distance và trạng thái hiện tại
# 3. Điều khiển motor
# 4. Gửi status lên MQTT

# Chỉ cần đảm bảo publish status sau khi motor chạy xong:
void main_logic_task(void *pvParameters) {
    while (1) {
        current_distance = vl53l0x_get_distance_mm();

        if (mqtt_command == 1 && current_distance < 270 && current_distance > 20) {
            if (!is_drawer_open) {
                ESP_LOGI(TAG, "OPENING");
                set_motor_speed(MOTOR_SPEED_VAL);
                vTaskDelay(pdMS_TO_TICKS(1000));
                set_motor_speed(0);
                is_drawer_open = true;
                
                // Gửi status lên sviot/drawer/status
                char payload[256];
                time_t now = time(NULL);
                snprintf(payload, sizeof(payload),
                    "{\"status\": \"ON\", \"timestamp\": %ld}",
                    (long)now
                );
                esp_mqtt_client_publish(client, MQTT_PUB_TOPIC_STATUS, payload, 0, 1, 0);
            }
            mqtt_command = -1;
        }
        
        else if (mqtt_command == 0) {
            if (is_drawer_open) {
                ESP_LOGI(TAG, "CLOSING");
                set_motor_speed(-MOTOR_SPEED_VAL);
                vTaskDelay(pdMS_TO_TICKS(700));
                set_motor_speed(0);
                is_drawer_open = false;
                
                // Gửi status lên sviot/drawer/status
                char payload[256];
                time_t now = time(NULL);
                snprintf(payload, sizeof(payload),
                    "{\"status\": \"OFF\", \"timestamp\": %ld}",
                    (long)now
                );
                esp_mqtt_client_publish(client, MQTT_PUB_TOPIC_STATUS, payload, 0, 1, 0);
            }
            mqtt_command = -1;
        }

        vTaskDelay(pdMS_TO_TICKS(200));
    }
}


# ============================================================================
# 6. CHECKLIST CẬP NHẬT ESP32
# ============================================================================

[ ] Cập nhật MQTT topic defines
[ ] Cập nhật subscribe callbacks để xử lý cả 2 topics
[ ] Cập nhật publish format (thêm timestamp)
[ ] Cập nhật publish topic (sviot/drawer/status)
[ ] Thêm health heartbeat task
[ ] Test MQTT connection
[ ] Test subscribe từ 2 topics
[ ] Test publish status với timestamp
[ ] Test motor control từ sviot/drawer/command

# ============================================================================
# 7. TEST MQTT TỬ TERMINAL
# ============================================================================

# Xem status từ ESP32:
mosquitto_sub -h localhost -t "sviot/drawer/status" -v

# Xem health heartbeat từ ESP32:
mosquitto_sub -h localhost -t "sviot/drawer/health" -v

# Gửi lệnh mở từ server:
mosquitto_pub -h localhost -t "sviot/drawer/command" -m '{"command":"open", "status":"ON", "timestamp":1234567890}'

# Gửi lệnh đóng từ server:
mosquitto_pub -h localhost -t "sviot/drawer/command" -m '{"command":"close", "status":"OFF", "timestamp":1234567890}'
"""
