# Kế Hoạch Điều Khiển Động Cơ ESP32 qua MQTT

## 📋 **Tổng quan**

Hệ thống Python SVIOT đã tích hợp MQTT, publish messages `ON`/`OFF` lên topic `sviot/detection` khi phát hiện người có DI_XA = "CO". Kế hoạch này mô tả cách xây dựng firmware cho ESP32 để:

1. Kết nối WiFi và MQTT broker (cùng broker với server Python).
2. Subscribe topic `sviot/detection`.
3. Khi nhận message `ON` → điều khiển động cơ xoay **bên phải 2 giây**.
4. Khi nhận message `OFF` → điều khiển động cơ xoay **bên trái 2 giây**.

## 🛠️ **Phần cứng cần thiết**

| Component | Mô tả | Ghi chú |
|-----------|-------|---------|
| ESP32 Dev Board | Vi điều khiển WiFi/Bluetooth | ESP32-WROOM-32, NodeMCU-32S, etc. |
| Động cơ DC/Servo | Tuỳ chọn:<br>• Động cơ DC 5‑12V (cần driver)<br>• Servo motor (SG90, MG996) | Servo dễ điều khiển, góc xoay cố định. |
| Driver động cơ (nếu dùng DC) | Module L298N hoặc TB6612FNG | Điều khiển chiều quay và tốc độ. |
| Nguồn cấp | Nguồn riêng cho động cơ (tuỳ điện áp) | Tránh dùng nguồn USB nếu động cơ công suất lớn. |
| Dây nối, breadboard | Kết nối linh kiện | |
| Điện trở, tụ (tuỳ chọn) | Bảo vệ chống nhiễu | |

## 🔌 **Sơ đồ kết nối (Wiring Diagram)**

### **Trường hợp dùng Servo Motor**
- Servo signal pin → GPIO 13 (hoặc bất kỳ GPIO có PWM)
- Servo VCC → 5V (cấp từ nguồn ngoài nếu cần)
- Servo GND → GND chung với ESP32

### **Trường hợp dùng DC Motor + L298N**
| L298N | ESP32 | Động cơ DC |
|-------|-------|------------|
| IN1   | GPIO 12 | |
| IN2   | GPIO 14 | |
| ENA   | GPIO 27 (PWM) | |
| OUT1  | | Chân 1 động cơ |
| OUT2  | | Chân 2 động cơ |
| 12V   | Nguồn ngoài 7‑12V | |
| GND   | GND chung | |

**Lưu ý:** Nối GND của nguồn động cơ với GND của ESP32.

## 📡 **Cấu hình MQTT Broker**

Broker hiện đang chạy trong Docker container `python-sviot-mqtt`, expose port **1883** ra host.

- **Broker address:** `192.168.x.x` (IP của máy chạy Docker) hoặc `localhost` nếu ESP32 kết nối cùng mạng LAN.
- **Port:** 1883
- **Topic:** `sviot/detection`
- **Message format:** JSON, ví dụ:
  ```json
  {"status": "ON", "timestamp": 123456789.0, ...}
  ```
  Chỉ cần parse field `status` là "ON" hoặc "OFF".

## 🧩 **Kiến trúc Firmware**

### **Framework & Thư viện**
- **Framework:** Arduino Core for ESP32 (dễ phát triển, hỗ trợ đầy đủ WiFi, MQTT, PWM).
- **Thư viện chính:**
  - `WiFi.h` – kết nối WiFi.
  - `PubSubClient.h` – MQTT client.
  - `ESP32Servo.h` (nếu dùng servo) hoặc `analogWrite()` (PWM cho DC motor).

### **Luồng chính**
1. Khởi tạo Serial monitor (debug).
2. Kết nối WiFi với SSID/password đã cấu hình.
3. Kết nối MQTT broker với client ID duy nhất.
4. Subscribe topic `sviot/detection`.
5. Trong loop:
   - Duy trì kết nối MQTT (reconnect nếu mất).
   - Khi có message, parse `status`.
   - Nếu `status == "ON"` → gọi hàm `rotateRight(2000)`.
   - Nếu `status == "OFF"` → gọi hàm `rotateLeft(2000)`.
   - Tránh xung đột: chỉ thực hiện một hành động tại một thời điểm, không interrupt.

## 🧪 **Các bước triển khai**

### **Bước 1: Cài đặt môi trường phát triển**
1. Cài Arduino IDE hoặc PlatformIO (VS Code extension).
2. Thêm board ESP32 trong Board Manager (URL: `https://espressif.github.io/arduino-esp32/package_esp32_index.json`).
3. Cài đặt thư viện `PubSubClient` (bởi Nick O’Leary) qua Library Manager.

### **Bước 2: Tạo sketch mới**
- Tạo file `.ino` với cấu trúc:
  ```cpp
  #include <WiFi.h>
  #include <PubSubClient.h>
  
  // WiFi credentials
  const char* ssid = "your_SSID";
  const char* password = "your_PASSWORD";
  
  // MQTT broker details
  const char* mqtt_server = "192.168.x.x";
  const int mqtt_port = 1883;
  const char* mqtt_topic = "sviot/detection";
  
  WiFiClient espClient;
  PubSubClient client(espClient);
  
  // Motor control pins
  const int motor_in1 = 12;
  const int motor_in2 = 14;
  const int motor_ena = 27;
  
  void setup() { ... }
  void loop() { ... }
  
  // Hàm kết nối WiFi
  void setup_wifi() { ... }
  
  // Hàm kết nối/reconnect MQTT
  void reconnect() { ... }
  
  // Callback khi nhận MQTT message
  void callback(char* topic, byte* payload, unsigned int length) { ... }
  
  // Hàm điều khiển động cơ
  void rotateRight(int duration_ms) { ... }
  void rotateLeft(int duration_ms) { ... }
  void stopMotor() { ... }
  ```

### **Bước 3: Điền thông tin mạng và broker**
- Thay `your_SSID`, `your_PASSWORD`.
- Đặt `mqtt_server` thành IP của máy chạy broker (có thể dùng `ifconfig` để xem IP).

### **Bước 4: Implement motor control**
- **Với DC motor:** sử dụng digitalWrite để set chiều quay, analogWrite để set tốc độ (tuỳ chọn).
- **Với Servo:** dùng thư viện Servo, write góc (0–180).

### **Bước 5: Upload và test**
1. Nạp code lên ESP32.
2. Mở Serial Monitor (baud 115200) để xem trạng thái kết nối.
3. Đảm bảo ESP32 và broker cùng mạng.
4. Dùng `mosquitto_pub` hoặc Python script publish thử message ON/OFF để kiểm tra.

## ⚠️ **Xử lý lỗi và tối ưu**

- **Reconnect MQTT:** nếu mất kết nối, tự động reconnect sau 5 giây.
- **Debounce message:** tránh xử lý cùng một message nhiều lần (so sánh payload trước đó).
- **Timeout động cơ:** dùng `millis()` thay vì `delay()` để không block loop.
- **Logging:** gửi log qua Serial và có thể publish lên topic debug.

## 📄 **Tài liệu tham khảo**

- [Arduino Core for ESP32](https://github.com/espressif/arduino-esp32)
- [PubSubClient Library](https://github.com/knolleary/pubsubclient)
- [L298N Driver Tutorial](https://lastminuteengineers.com/l298n-dc-stepper-driver-arduino-tutorial/)
- [ESP32 Servo Library](https://github.com/madhephaestus/ESP32Servo)

## ✅ **Tiêu chí hoàn thành**

- [ ] ESP32 kết nối WiFi thành công.
- [ ] Subscribe topic `sviot/detection` và nhận message từ broker.
- [ ] Khi nhận `ON`, động cơ xoay phải 2 giây.
- [ ] Khi nhận `OFF`, động cơ xoay trái 2 giây.
- [ ] Hệ thống hoạt động ổn định, tự động reconnect khi mất mạng.

## 🚀 **Bước tiếp theo**

Sau khi plan được duyệt, có thể chuyển sang **Code mode** để viết firmware chi tiết, hoặc **Debug mode** để test và sửa lỗi.

---
*Plan được tạo ngày: 2026‑04‑06*  
*Dự án: Python SVIOT + ESP32 Motor Control*