import sys
import os

# Agregar el directorio raíz al PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine, Base
from app.models.admin import Admin
from app.core.security import pwd_context

# Importar todos los modelos para que SQLAlchemy los conozca
from app.models import user, product, orders, admin, cart

print("Creando tablas en la base de datos si no existen...")
# Crear todas las tablas si no existen
Base.metadata.create_all(bind=engine)
print("Tablas verificadas/creadas exitosamente!")

db = SessionLocal()

try:
    # Verificar si ya existe un admin con ese email
    existing_admin = db.query(Admin).filter(Admin.email == "admin@optibelleza.com").first()

    if existing_admin:
        print("\n[OK] Ya existe un administrador con ese email")
        print("Email: admin@optibelleza.com")
        print("Password: administrador123")
    else:
        admin = Admin(
            email="admin@optibelleza.com",
            password=pwd_context.hash("administrador123")
        )
        
        db.add(admin)
        db.commit()
        print("\n[OK] Admin creado exitosamente!")
        print("Email: admin@optibelleza.com")
        print("Password: administrador123")
finally:
    db.close()