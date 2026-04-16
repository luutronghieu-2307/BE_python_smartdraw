# pythonSVIOT API

Project scaffold backend API Python chuẩn dùng FastAPI.

## Cấu trúc
- `app/main.py`: entrypoint ứng dụng
- `app/api/v1/endpoints/`: các route theo module
- `app/core/`: cấu hình, logger, constants
- `app/db/`: session, base model
- `app/models/`: SQLAlchemy models
- `app/schemas/`: Pydantic schemas
- `app/services/`: business logic
- `app/repositories/`: tầng truy cập dữ liệu
- `tests/`: test cases

## Chạy local
- Cài dependencies từ `pyproject.toml`
- Chạy app bằng Uvicorn: `uvicorn app.main:app --reload`

## Chạy bằng Docker
- Sao chép biến môi trường: `cp .env.example .env`
- Build image: `docker compose build`
- Chạy service: `docker compose up`
- API sẽ chạy tại `http://localhost:8000`

## YOLOv8 person detection
- Swagger upload ảnh: `POST /api/v1/detect/person/upload`
- Kết quả trả về: `image_url` của ảnh đã vẽ bounding box cho người
- Ảnh đã xử lý được lưu trong `media/detections/`

## MobileNetV2 classification
- Swagger upload ảnh: `POST /api/v1/classify/mobilenet/upload`
- Kết quả trả về: `image_url` của ảnh đã gắn nhãn dự đoán
- Ảnh đã xử lý được lưu trong `media/mobilenet/`

## Combined detection + classification pipeline
- Swagger upload ảnh: `POST /api/v1/pipeline/upload`
- YOLOv8 sẽ detect tất cả người trong ảnh, crop từng ROI theo thứ tự trái sang phải, rồi MobileNetV2 sẽ phân loại từng ROI
- Kết quả trả về: tọa độ bbox, nhãn, confidence và `image_url` của ảnh đã vẽ bounding box + nhãn

## Light control for Flutter mobile app
- API điều khiển đèn: `POST /api/v1/light/control`
- Body: `{ "state": "on" }` hoặc `{ "state": "off" }`
- QR bootstrap tự sinh lúc backend khởi động và lưu tại `media/qr/server-connection-qr.png`
- Có thể mở trực tiếp: `GET /api/v1/light/qr`
- QR chứa JSON compact gồm `u` và `e`
- Format QR: `{ "u": "http://<ip>:8000", "e": "/api/v1/light/control" }`

## Docker networking for same Wi‑Fi QR
- API container chạy bằng `network_mode: host` để QR tự dùng đúng IP LAN của máy chạy backend
- Điện thoại cần ở cùng Wi‑Fi với máy chạy Docker để quét QR và gọi API được ngay

## Thư viện đã ghim
- `fastapi==0.115.0`
- `uvicorn[standard]==0.30.6`
- `pydantic-settings==2.4.0`
- `sqlalchemy==2.0.32`
- `alembic==1.13.2`
- `numpy==1.26.4`
- `opencv-python==4.9.0.80`
- `vidgear[videocapture]==0.3.2`
- `ultralytics==8.2.103`
- `torch==2.2.2`
- `torchvision==0.17.2`
