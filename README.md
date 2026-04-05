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
