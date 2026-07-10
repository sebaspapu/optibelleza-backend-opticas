from fastapi import FastAPI,Depends,HTTPException
from fastapi.params import Body

from app.db.session import engine, SessionLocal

from app.models import user as models
from app.schemas import user as schemas
import socketio as socketio

from sqlalchemy.orm import Session
from sqlalchemy import text

# Routers
from app.api.routers import auth
from app.api.routers import products
from app.api.routers import cart
from app.api.routers import order
from app.api.routers import payment

# Middleware setup
from app.middlewares.cors import setup_cors

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Configurar middlewares
setup_cors(app)

# Registrar routers
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(cart.router)
app.include_router(order.router)
app.include_router(payment.router)
print("hello")

@app.get("/", tags=["Root"])
def is_running():
    return {"message": "🚀 Optibelleza API is running successfully!"}

