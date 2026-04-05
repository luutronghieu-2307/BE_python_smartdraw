from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "pythonSVIOT API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "sqlite:///./app.db"
    rtsp_url: str = ""
    yolo_model_path: str = "asssets/yolov8n.pt"
    mobilenet_model_path: str = "asssets/MobileNetV2_best.pth"
    mobilenet_labels_path: str = "asssets/mobilenetv2.txt"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
