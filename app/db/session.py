from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import os

# Support Postgres (production) and a local SQLite fallback for demos/tests.
# Use APP_ENV to decide: non-production -> sqlite, production -> postgres.
print(f"DEBUG: settings.app_env is '{settings.app_env}'")
if settings.app_env.lower() not in ("production", "prod"):
    # Development / local: use a local file-based sqlite database.
    db_path = settings.database_name or "./test2.db"
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.abspath(db_path)}"
    # For SQLite, need check_same_thread=False when using with multiple threads.
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Production: use Postgres (credentials come from settings / .env)
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql+psycopg2://{settings.database_username}:{settings.database_password}"
        f"@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"
    )
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_size=10, max_overflow=20)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()