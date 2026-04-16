# Hướng Dẫn Triển Khai MQTT Integration

## 📁 **Bước 1: Chuyển đến thư mục dự án**
```bash
cd /home/tronghieu/Desktop/pythonSVIOT
```

## 🔧 **Bước 2: Rebuild Docker Image với MQTT Support**
```bash
docker-compose build
```

## 🚀 **Bước 3: Khởi Động Hệ Thống**
```bash
docker-compose up -d
```

> **Lưu ý:** desktop viewer đã được bật. Nếu máy bạn có giao diện đồ họa, khi API khởi động sẽ tự mở cửa sổ OpenCV xem stream camera.
>
> Nếu chạy bằng Docker trên Linux, hãy cho phép container truy cập X11 trước khi `up`:
> `xhost +local:root`

## 📊 **Bước 4: Kiểm Tra Logs**
```bash
# Xem logs của API service
docker-compose logs -f api

# Hoặc theo container name
docker logs -f python-sviot-api
```

## 🔍 **Bước 5: Monitor MQTT Messages**

### **Cài đặt mosquitto-clients (nếu chưa có)**
```bash
sudo apt install mosquitto-clients
```

### **Subscribe để xem messages**
```bash
# Mở terminal mới, chạy lệnh này để xem real-time messages
mosquitto_sub -h localhost -t sviot/detection -v
```

### **Publish test message (optional)**
```bash
mosquitto_pub -h localhost -t sviot/detection -m '{"test": "message"}'
```

## ⚙️ **Cấu Hình MQTT Broker**

File `.env` đã được cập nhật tự động. Kiểm tra các biến sau:

```env
MQTT_BROKER=mqtt-broker      # Tên service của MQTT broker trong Docker Compose
MQTT_PORT=1883              # Port mặc định của Mosquitto
MQTT_TOPIC=sviot/detection
MQTT_COOLDOWN_SECONDS=5     # Thời gian giữa các lần gửi ON
FIREBASE_CREDENTIALS_PATH=./serviceAccountKey.json
FIREBASE_DEFAULT_TOPIC=sviot-users
```

> Lưu ý: file `serviceAccountKey.json` chỉ dùng ở backend và không nên commit lên git.

## 🔔 **FCM Setup**

### **Backend API để đăng ký token từ Flutter**
```bash
POST /api/v1/fcm/token
```

### **Payload mẫu**
```json
{
  "token": "fcm_device_token_from_flutter",
  "platform": "android",
  "device_id": "flutter-device-001"
}
```

### **Luồng triển khai**
1. Flutter lấy FCM token từ `firebase_messaging`.
2. Flutter gọi API `/api/v1/fcm/token` để lưu token.
3. Khi BE detect người và đọc `has_item`, BE gửi push notification qua Firebase.

### **Docker Compose Setup**
- Docker Compose file đã được cập nhật để chạy MQTT broker (mosquitto) cùng network với API.
- MQTT broker service tên là `mqtt-broker`, container name `python-sviot-mqtt`.
- Port 1883 được expose ra host, vì vậy có thể subscribe từ host bằng `localhost:1883`.

## 🐛 **Troubleshooting**

### **1. Lỗi "Cannot connect to MQTT broker"**
```bash
# Kiểm tra MQTT broker có đang chạy không
docker ps | grep mqtt

# Test kết nối từ host
nc -zv localhost 1883
```

### **2. Không thấy MQTT messages**
```bash
# Kiểm tra logs của API
docker-compose logs api | grep -i mqtt

# Kiểm tra xem pipeline có chạy không
docker-compose logs api | grep -i "people_count"
```

### **3. Rebuild không cập nhật changes**
```bash
# Xóa container cũ và rebuild
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## 📡 **Logic MQTT đã triển khai**

### **Khi camera phát hiện:**
- Có người VÀ DI_XA = "CO" → Gửi `ON` (mỗi 5 giây)
- Không có người HOẶC không có DI_XA = "CO" → Gửi `OFF` (một lần duy nhất)

### **Payload mẫu:**
```json
{
  "status": "ON",
  "timestamp": 1712401234.567,
  "people_count": 1,
  "has_di_xa_co": true,
  "source": "pythonSVIOT"
}
```

## 🎯 **Test Nhanh**

### **Test MQTT State Manager (không cần broker)**
```bash
cd /home/tronghieu/Desktop/pythonSVIOT
python3 test_mqtt_integration.py
```
Chọn `n` khi hỏi "Test MQTT connection?" để test logic mà không cần kết nối thật.

### **Kiểm tra cấu hình**
```bash
cd /home/tronghieu/Desktop/pythonSVIOT
python3 -c "
import sys
sys.path.insert(0, '.')
from app.core.config import settings
print(f'MQTT Broker: {settings.mqtt_broker}:{settings.mqtt_port}')
print(f'MQTT Topic: {settings.mqtt_topic}')
print(f'Cooldown: {settings.mqtt_cooldown_seconds}s')
"
```

## 📞 **Hỗ Trợ**

Nếu gặp vấn đề:
1. Kiểm tra logs: `docker-compose logs api`
2. Kiểm tra MQTT connection: `mosquitto_sub -h localhost -t sviot/detection -v`
3. Kiểm tra file `.env` có đúng cấu hình không

Hệ thống đã sẵn sàng hoạt động sau khi rebuild Docker image!