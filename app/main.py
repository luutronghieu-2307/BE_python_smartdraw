from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.dependencies import shutdown_vidgear_stream
from app.db.base import Base
from app.db.session import engine
from app.services.light_control import generate_connection_qr
from app.services.live_viewer import start_desktop_viewer, stop_desktop_viewer

logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.on_event("startup")
def startup_event():
    """Application startup event: start the local desktop viewer."""
    from app.models import fcm_token  # noqa: F401

    Base.metadata.create_all(bind=engine)
    generate_connection_qr()
    if settings.enable_desktop_viewer:
        start_desktop_viewer()
    
    # Initialize MQTT subscriptions
    try:
        from app.services.mqtt_subscriber import register_all_handlers
        from app.services.mqtt_client import get_mqtt_client
        
        register_all_handlers()
        
        mqtt_client = get_mqtt_client()
        if mqtt_client.is_connected() or mqtt_client.connect():
            # Subscribe to drawer status and health topics
            mqtt_client.subscribe(settings.mqtt_drawer_status_topic, qos=0)
            mqtt_client.subscribe(settings.mqtt_drawer_health_topic, qos=0)
            mqtt_client.subscribe(settings.mqtt_item_status_topic, qos=0)
            
            # Set message handler
            from app.services.mqtt_subscriber import get_mqtt_subscriber
            subscriber = get_mqtt_subscriber()
            mqtt_client.set_message_handler(subscriber.handle_message)
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to initialize MQTT subscriptions: {e}")


@app.on_event("shutdown")
def shutdown_event():
    """Application shutdown event: stops the viewer and VidGear stream."""
    # Force OFF any pending drawer command
    try:
        from app.services.drawer_state import get_drawer_state_manager
        drawer_manager = get_drawer_state_manager()
        if drawer_manager.force_off():
            from app.services.mqtt_client import get_mqtt_client
            mqtt_client = get_mqtt_client()
            mqtt_client.publish_drawer_command("close")
    except Exception as e:
        logger.warning(f"Error forcing drawer OFF during shutdown: {e}")
    
    stop_desktop_viewer()
    shutdown_vidgear_stream()


app.include_router(api_router, prefix="/api/v1")

media_dir = Path("media")
media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running"}
