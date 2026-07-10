from pydantic_settings import BaseSettings

# Defaults provided so the app can run in a local demo mode without
# requiring a Postgres server or AWS credentials. These values can be
# overridden by creating a `.env` file or setting environment variables.
class Settings(BaseSettings):

    # App environment
    # Use 'development' or 'production'. In production set APP_ENV=production
    app_env: str = "development"
    # Debug flag (should be False in production)
    debug: bool = True
    # Base URLs (useful to centralize frontend/backend endpoints)
    backend_base_url: str = "http://127.0.0.1:8000"
    frontend_base_url: str = "http://localhost:5173"
    websocket_url: str = "ws://127.0.0.1:8000/ws1"
    # CORS origins can be provided as a comma-separated string in the env
    cors_origins: str = "http://127.0.0.1:3000"

    # Database settings
    database_hostname: str = "sqlite"  # use 'sqlite' to trigger local sqlite fallback
    database_password: str = ""
    database_name: str = "./test2.db"
    database_username: str = ""
    database_port: str = "0"

    # JWT / Auth
    # Set SECRET_KEY in your .env for production
    secret_key: str = ""
    algorithm: str = "HS256"

    # AWS (optional)
    aws_access_key_id: str = ""
    aws_secret_key: str = ""
    aws_region: str = ""
    # S3 bucket name (if using S3)
    s3_bucket_name: str = ""

    # Stripe: set these in .env (no defaults in code)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    # SendGrid / Email - set in .env
    sendgrid_api_key: str = ""
    notification_email: str = ""
    sendgrid_from_email: str = ""
    # Sandbox mode: True for development to avoid sending real emails
    sendgrid_sandbox_mode: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


from dotenv import load_dotenv
import os
load_dotenv()

settings = Settings()

# Ajuste mínimo de URLs según el ambiente (no cambia otras partes del código).
# - Si `APP_ENV` es 'production' se sugieren/derivan valores de producción
#   cuando no se hayan provisto explícitamente en el .env.
# - En desarrollo se aseguran los valores por defecto en localhost.
try:
    env = settings.app_env.lower()
except Exception:
    env = "development"

if env in ("production", "prod"):
    # Si no se especificó BACKEND/FRONTEND/WS en .env, usar placeholders seguros
    if settings.backend_base_url in (None, "", "http://127.0.0.1:8000"):
        settings.backend_base_url = "https://api.your-backend.example"
    if settings.frontend_base_url in (None, "", "http://127.0.0.1:3000"):
        settings.frontend_base_url = "https://your-frontend.vercel.app"
    # Derivar websocket desde backend si no se proporcionó uno explícito
    if not settings.websocket_url or settings.websocket_url.startswith("ws://127.0.0.1"):
        try:
            from re import sub

            host_part = sub(r"^https?://", "", settings.backend_base_url)
            ws_proto = "wss" if settings.backend_base_url.startswith("https") else "ws"
            settings.websocket_url = f"{ws_proto}://{host_part}/ws1"
        except Exception:
            # fallback razonable
            settings.websocket_url = "wss://api.your-backend.example/ws1"
    # CORS: garantizar que incluya la URL del frontend si no se definió otra
    if settings.cors_origins in (None, "", "http://127.0.0.1:3000"):
        settings.cors_origins = settings.frontend_base_url
else:
    # Desarrollo: asegurar los valores localhost si no están presentes
    if not settings.backend_base_url:
        settings.backend_base_url = "http://127.0.0.1:8000"
    if not settings.frontend_base_url:
        settings.frontend_base_url = "http://127.0.0.1:3000"
    if not settings.websocket_url:
        settings.websocket_url = "ws://127.0.0.1:8000/ws1"
    if not settings.cors_origins:
        settings.cors_origins = "http://127.0.0.1:3000"


def origin_matches_frontend(origin: str) -> bool:
    """Simple, tolerant comparison between an Origin header and the configured frontend URL.

    Returns True when the origin matches `settings.frontend_base_url`. It also
    accepts the common localhost/127.0.0.1 variants so local dev requests match.
    """
    try:
        if not origin:
            return False
        origin_norm = origin.rstrip('/')
        frontend = (settings.frontend_base_url or '').rstrip('/')
        if origin_norm == frontend:
            return True
        # accept simple localhost/127.0.0.1 variants
        if origin_norm == frontend.replace('127.0.0.1', 'localhost'):
            return True
        if origin_norm == frontend.replace('localhost', '127.0.0.1'):
            return True
        return False
    except Exception:
        return False
