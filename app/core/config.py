from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "pythonSVIOT API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_url: str = "sqlite:///./app.db"
    rtsp_url: str = ""
    rtsp_h264_url: str = ""
    yolo_model_path: str = "asssets/yolov8n.pt"
    yolo_conf_threshold: float = 0.25
    rtsp_use_udp: bool = True
    rtsp_low_latency: bool = True
    camera_frame_width: int = 640
    camera_frame_height: int = 360
    camera_capture_warmup_seconds: float = 5.0
    camera_preprocess_enabled: bool = True
    camera_disable_autofocus: bool = True
    camera_disable_auto_exposure: bool = True
    camera_disable_auto_white_balance: bool = True
    camera_enhance_min_mean: float = 55.0
    camera_enhance_max_mean: float = 200.0
    camera_enhance_min_std: float = 18.0
    camera_brightness_alpha: float = 0.98
    camera_brightness_beta: int = -4
    camera_clahe_clip_limit: float = 1.2
    camera_clahe_tile_grid_size: int = 8
    camera_sharpen_enabled: bool = False
    pipeline_ai_frame_stride: int = 2
    pipeline_stream_warmup_seconds: float = 3.0
    pipeline_buffer_maxsize: int = 5
    mobilenet_model_path: str = "asssets/MobileNetV2_best.pth"
    mobilenet_labels_path: str = "asssets/mobilenetv2.txt"
    mobilenet_conf_threshold: float = 0.6
    
    # MQTT Configuration
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic: str = "sviot/detection"
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_qos: int = 1
    mqtt_retain: bool = False
    mqtt_cooldown_seconds: int = 5  # Thời gian giữa các lần gửi ON

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
