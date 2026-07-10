from fastapi import FastAPI,Depends,HTTPException,APIRouter,status,UploadFile,File,Header,Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import product as product_models
from app.models import cart as cart_models
from app.core import oauth2
from app.schemas import product as schemas
from app.core.config import settings, origin_matches_frontend
from typing import List, Optional
import base64
from app.infra.websocket import websocket_connections,websocket_connections_admin
import stripe
from stripe.error import StripeError

# Configurar Stripe
stripe.api_key = settings.stripe_secret_key

import boto3

# Read AWS / S3 settings from config (values come from .env via Settings)
AWS_ACCESS_KEY = settings.aws_access_key_id
AWS_REGION = settings.aws_region or "ap-south-1"
S3_BUCKET_NAME = settings.s3_bucket_name

# Create an S3 client using settings values
s3 = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY or None,
        aws_secret_access_key=settings.aws_secret_key or None,
        region_name=AWS_REGION or None,

)

router=APIRouter()
s3_bucket_name = S3_BUCKET_NAME or ""

# Use `origin_matches_frontend` from `app.core.config` to compare Origin header
async def client_signal():
       for client in websocket_connections:
                            try:
                                
                                    await client.send_text("user login")
                                    
                            except Exception as e:
                    # Handle disconnected clients if needed
                                            print("Error",e)
                                            pass
       return

#CRUD

# GET ALL PRODUCT MOUNTS (MORE COMPLETE WITH FILTERS)
@router.get("/api/products", response_model=List[schemas.Shoes], tags=["Public"])
def get_products_mounts_all(
    db: Session = Depends(get_db),
    category: Optional[str] = Query(None, description="Filtrar por categoría"),
    type: Optional[str] = Query(None, description="Filtrar por tipo (Featured/New)"),
    limit: int = Query(10, ge=1, le=100, description="Límite de resultados por página"),
    skip: int = Query(0, ge=0, description="Offset de resultados"),
):
    query = db.query(product_models.Shoes)
    if category:
        query = query.filter(product_models.Shoes.shoes_category.ilike(f"%{category}%"))
    if type:
        query = query.filter(product_models.Shoes.shoes_type == type.capitalize())
    
    products = query.offset(skip).limit(limit).all()
    return products

# GET TYPE=FEATURED (OPTIONAL)
@router.get("/api/featured_product_mounts", response_model=List[schemas.Shoes], tags=["Public"])
def read(db: Session = Depends(get_db)):
     
    product_mounts_list = db.query(product_models.Shoes).filter(product_models.Shoes.shoes_type=="Featured").all()

    # Prepare a dictionary with all the required fields
    return product_mounts_list

# GET TYPE=NEW (OPTIONAL)
@router.get("/api/new_product_mounts", response_model=List[schemas.Shoes], tags=["Public"])
def read(db: Session = Depends(get_db)):
     
    product_mounts_list = db.query(product_models.Shoes).filter(product_models.Shoes.shoes_type=="New").all()
   
    # Prepare a dictionary with all the required fields
    return product_mounts_list

# GET A PRODUCT MOUNTS BY ID
#@router.get("/get_post/{id}",response_model=schemas.Shoes)
@router.get("/api/products/{id}",response_model=schemas.Shoes, tags=["Public"])
def get_product_mount_by_id(id:int,db: Session = Depends(get_db)):
    #posts=db.execute(text("SELECT * FROM POSTS WHERE id=:id"),{"id":id})
    product_mount_by_id=db.query(product_models.Shoes).filter(product_models.Shoes.id==id).first()
    if product_mount_by_id==None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"Montura con id: {id}, no fue encontrada")
    return product_mount_by_id

# CREATE PRODUCT MOUNTS
@router.post("/api/admin/products", tags=["Auth - Admin"])
async def create_product_mounts(shoes:schemas.ShoesCreate,db: Session = Depends(get_db),current_user:int=Depends(oauth2.is_admin_middleware),origin: str = Header(None)):
    try:
        print("\n=== Creando o reutilizando producto ===")

        # 1️⃣ Verificar si el producto ya existe en la base de datos
        existing_db_shoe = db.query(product_models.Shoes).filter(product_models.Shoes.name == shoes.name).first()
        if existing_db_shoe:
            print(f"Producto '{shoes.name}' ya existe en la base de datos.")
            return existing_db_shoe

        # 2️⃣ Buscar si ya existe en Stripe (por nombre)
        existing_products = stripe.Product.list(limit=100)
        stripe_product = None
        for p in existing_products.data:
            if p.name.lower() == shoes.name.lower():
                stripe_product = p
                print(f"Producto ya existe en Stripe: {p.id}")
                break

        # 3️⃣ Si no existe en Stripe, crear uno nuevo
        if not stripe_product:
            stripe_product = stripe.Product.create(
                name=shoes.name,
                description=shoes.shoes_description,
                images=[shoes.product_image] if shoes.product_image else [],
                metadata={
                    'category': shoes.shoes_category,
                    'type': shoes.shoes_type
                }
            )
            print(f"Producto creado en Stripe: {stripe_product.id}")

        # 4️⃣ Verificar si ya hay un precio existente en Stripe
        prices = stripe.Price.list(product=stripe_product.id)
        if prices.data:
            stripe_price = prices.data[0]
            print(f"Precio existente reutilizado: {stripe_price.id}")
        else:
            stripe_price = stripe.Price.create(
                product=stripe_product.id,
                unit_amount=int(shoes.price * 100),  # Stripe usa centavos
                currency='cop'
            )
            print(f"Nuevo precio creado en Stripe: {stripe_price.id}")

        # 5️⃣ Registrar en base de datos
        new_shoes = product_models.Shoes(
            **shoes.dict(),
            stripe_product_id=stripe_product.id,
            stripe_price_id=stripe_price.id
        )
        db.add(new_shoes)
        db.commit()
        db.refresh(new_shoes)

        if origin_matches_frontend(origin):
            await client_signal()

        return new_shoes

    except StripeError as e:
        print(f"Error creando producto en Stripe: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error con Stripe: {str(e)}"
        )

# UPDATE A PRODUCT MOUNTS BY ID
#@router.put("/updateshoes/{id}")
@router.put("/api/admin/products/{id}", tags=["Auth - Admin"])
async def update_product_mount_by_id(id:int,post:schemas.ShoesUpdate,db: Session = Depends(get_db),current_user:int=Depends(oauth2.is_admin_middleware),origin: str = Header(None)):
    shoes_query=db.query(product_models.Shoes).filter(product_models.Shoes.id==id)
    cart_query=db.query(cart_models.Cart).filter(cart_models.Cart.product_id==id)
    shoes = shoes_query.first()
    if shoes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con id: {id} no encontrado"
        )
    
    try:
        print("\n=== Actualizando producto en Stripe ===")
        # Si el precio ha cambiado, crear un nuevo precio en Stripe
        if hasattr(post, 'price') and shoes.price != post.price:
            print(f"Precio actualizado de ${shoes.price} a ${post.price}")
            # Crear nuevo precio en Stripe
            new_stripe_price = stripe.Price.create(
                product=shoes.stripe_product_id,
                unit_amount=int(post.price * 100),
                currency='cop'
            )
            # Actualizar el ID del precio en nuestro modelo
            post.stripe_price_id = new_stripe_price.id
            print(f"Nuevo precio creado en Stripe: {new_stripe_price.id}")
        
        # Actualizar el producto en Stripe
        stripe.Product.modify(
            shoes.stripe_product_id,
            name=post.name if hasattr(post, 'name') else shoes.name,
            description=post.shoes_description if hasattr(post, 'shoes_description') else shoes.shoes_description,
            images=[post.product_image] if hasattr(post, 'product_image') and post.product_image else None,
            metadata={
                'category': post.shoes_category if hasattr(post, 'shoes_category') else shoes.shoes_category,
                'type': post.shoes_type if hasattr(post, 'shoes_type') else shoes.shoes_type
            }
        )
        print(f"Producto actualizado en Stripe: {shoes.stripe_product_id}")
        
        # Actualizar el carrito si es necesario
        if cart_query.first()!=None:
            cart_query.update({"product_name":post.name},synchronize_session=False)
        
        # Actualizar el producto en nuestra base de datos
        shoes_query.update(post.dict(),synchronize_session=False)
        db.commit()
        
        if origin_matches_frontend(origin):
            await client_signal()
        
        return {"data":"success"}
        
    except StripeError as e:
        print(f"Error actualizando producto en Stripe: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error con Stripe: {str(e)}"
        )

# DELETE A PRODUCT MOUNTS BY ID
#@router.get("/delete_shoes/{id}")
@router.delete("/api/admin/products/{id}", tags=["Auth - Admin"])
async def delete_product_mount_by_id(id:int,db: Session = Depends(get_db),current_user:int=Depends(oauth2.is_admin_middleware),origin: str = Header(None)):
    
    product_query = db.query(product_models.Shoes).filter(product_models.Shoes.id == id)
    product = product_query.first()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto con id {id} no encontrado"
        )
    
    product_query.delete(synchronize_session=False)
    db.commit()

    if origin_matches_frontend(origin):
        # Iterate over connected WebSocket clients and send a message
        await client_signal()
    return {"message":"Producto eliminado exitosamente"}