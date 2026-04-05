# Project Structure

```text
pythonSVIOT/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   └── health.py
│   │       └── router.py
│   ├── core/
│   │   ├── config.py
│   │   └── logger.py
│   ├── db/
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   │   └── base.py
│   ├── schemas/
│   │   └── common.py
│   ├── services/
│   ├── repositories/
│   └── main.py
├── tests/
│   └── test_health.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .dockerignore
├── .gitignore
└── README.md
```

## Vai trò từng thư mục

- `app/main.py`: điểm khởi chạy FastAPI
- `app/api/v1/endpoints/`: chứa các route theo từng chức năng
- `app/core/`: cấu hình hệ thống, logger, biến môi trường
- `app/db/`: kết nối DB, session, base model
- `app/models/`: model SQLAlchemy
- `app/schemas/`: schema Pydantic cho request/response
- `app/services/`: business logic
- `app/repositories/`: tầng làm việc với dữ liệu
- `tests/`: test tự động

## Docker

- `Dockerfile`: build image cho API
- `docker-compose.yml`: chạy container local
- `.dockerignore`: loại trừ file không cần đưa vào image

## Chạy nhanh

```bash
cp .env.example .env
docker compose up --build
```
