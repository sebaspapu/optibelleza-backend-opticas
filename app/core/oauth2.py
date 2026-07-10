import jwt
from datetime import datetime,timedelta
from app.db.session import get_db
from fastapi import Depends, status, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas import user as schemas
from app.models import user as models

from typing import Dict,Any

from sqlalchemy import select
from app.core.config import settings
#oauth2_scheme= OAuth2PasswordBearer(tokenUrl='login_admin')
oauth2_scheme = HTTPBearer(auto_error=True)

# Configurar el esquema de seguridad para usar 401 en lugar de 403
class CustomHTTPBearer(HTTPBearer):
    async def __call__(self, request: Request):
        try:
            return await super().__call__(request)
        except HTTPException as e:
            if e.status_code == 403:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No se proporcionó token de autenticación",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            raise e

oauth2_scheme = CustomHTTPBearer(auto_error=True)

target_endpoint = '/login_admin'

# Function to check if an endpoint is present in the app



  
SECREAT_KEY = settings.secret_key
ALGORITHM = settings.algorithm
print(oauth2_scheme)
ACCESS_TOKEN_EXPIRE_MINUTES=5

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECREAT_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_access_token(token: str, credentials_exception):
        try:
            payload = jwt.decode(token, SECREAT_KEY, algorithms=[ALGORITHM])
            role: str = payload.get("role")
            id: str = payload.get("user_id")
            
            if id is None or role is None:
                raise credentials_exception
                
            # Convertir el ID a entero
            try:
                user_id = int(id)
            except ValueError:
                raise credentials_exception
                
            token_data = schemas.Token_data(id=user_id, role=role)
            return token_data
            
        except jwt.PyJWTError as e:
            # Error específico de JWT (token inválido, expirado, etc)
            raise credentials_exception
        except Exception as e:
            # Cualquier otro error inesperado
            print(f"Error inesperado al verificar token: {e}")
            raise credentials_exception

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    token_data = verify_access_token(token, credentials_exception)
   
    user = db.query(models.User).filter(models.User.id == token_data.id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado"
        )

    return {"user": user, "token_data": token_data}

#async def verify_admin(current_user: dict = Depends(get_current_user)):
async def is_admin_middleware(current_user: dict = Depends(get_current_user)):
    """Middleware que verifica si el usuario autenticado tiene rol de administrador.
    
    Criterios según HU:
    - Se ejecuta después de la autenticación (via Depends)
    - Verifica el rol en el token JWT
    - Permite continuar si rol es 'ADMIN'
    - Devuelve 403 si no es admin
    """
    token_data = current_user.get("token_data")
    role = getattr(token_data, "role", None)
    if role is None or str(role).lower() != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador",
        )

    return current_user
