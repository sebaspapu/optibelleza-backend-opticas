from fastapi import FastAPI,Depends,HTTPException,APIRouter,status,Header
from sqlalchemy.orm import Session
from app.db.session import get_db

#modelos
from app.models import product as product_models
from app.models import user as models
from app.models import cart as models_cart

#schemas
from app.schemas import cart
from app.schemas import user as schemas
from app.schemas import product as schemas_product

from app.core import oauth2
from sqlalchemy.exc import IntegrityError
from app.infra.websocket import websocket_connections,websocket_connections_admin
from typing import List, Optional,Union

from app.core.config import settings, origin_matches_frontend

router=APIRouter()
async def admin_signal():
       for client in websocket_connections_admin:
                            try:
                                
                                    await client.send_text("user login")
                                    
                            except Exception as e:
                    # Handle disconnected clients if needed
                                            print("Error",e)
                                            pass
       return

async def client_signal():
       for client in websocket_connections:
                            try:
                                
                                    await client.send_text("user login")
                                    
                            except Exception as e:
                    # Handle disconnected clients if needed
                                            print("Error",e)
                                            pass
       return

# añadir productos al carro
@router.post("/api/cart/add_item_cart",response_model=Union[cart.CartOut, cart.OutOfStockMessage], tags=["Shopping Cart"])
async def add_item_cart(shoes_id:cart.CartAdd,db: Session = Depends(get_db),current_user:int=Depends(oauth2.get_current_user),origin: str = Header(None)):
        print("\n=== Agregando producto al carrito ===")
        id=dict(current_user["token_data"])["id"]
        print(current_user["token_data"])
        print(f"👤 Usuario ID: {id}")
        
        user_email=db.query(models.User).filter(models.User.id==id).first()
        if not user_email:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id {id} not found")
        
        shoes=db.query(product_models.Shoes).filter(product_models.Shoes.id==shoes_id.id).first()
        if not shoes:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product with id {shoes_id.id} not found")
        
        print(f"📦 Producto ID: {shoes.id}")
        print(f"👞 Nombre del producto: {shoes.name}")
        print(f"💰 Precio: ${shoes.price}")
        print(f"📧 Email del usuario: {user_email.email}")
        
        cart_all=db.query(models_cart.Cart).filter(models_cart.Cart.owner_email==user_email.email).all()
        # new_item=models_cart.Cart(product_id=shoes.id,size=shoes_id.size,product_quantity=shoes_id.product_quantity,owner_email=user_email.email,owner_id=id,product_image=shoes.product_image,price=shoes.price,product_name=shoes.name, shoes_category=shoes.shoes_category)
        new_item=models_cart.Cart(product_id=shoes.id,product_quantity=shoes_id.product_quantity,owner_email=user_email.email,owner_id=id,product_image=shoes.product_image,price=shoes.price,product_name=shoes.name, shoes_category=shoes.shoes_category)
        shoes_stock = int(shoes.shoes_stock or 0)
        try:
                # Validar que la cantidad solicitada no exceda el stock disponible
                requested_qty = int(shoes_id.product_quantity or 1)
                if requested_qty <= 0:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid requested quantity")
                if shoes_stock >= requested_qty:
                        db.add(new_item)
                        db.commit()
                        db.refresh(new_item)
                        #if str(origin)=="http://localhost:3000":
                        if origin_matches_frontend(origin):
                                # Iterate over connected WebSocket clients and send a message
                                await client_signal()
                        return new_item
                else:
                        return {"status":"out of stock"}
        except IntegrityError as e:
                db.rollback()
                raise HTTPException(status_code=400, detail="Unique constraint violation: Item already exists")
    

# obtener todos los items del carrito
@router.get("/api/cart/all_cart_items",response_model=List[cart.CartOut], tags=["Shopping Cart"])
def get_all_item_cart(db: Session = Depends(get_db),current_user:int=Depends(oauth2.get_current_user),origin: str = Header(None)):
    id=dict(current_user["token_data"])["id"]
    print(current_user["token_data"])
    user_email=db.query(models.User).filter(models.User.id==id).first()
    cart_all=db.query(models_cart.Cart).filter(models_cart.Cart.owner_email==user_email.email).all()

    return cart_all

# Aumentar cantidad de un producto
@router.put("/api/cart/increase_cart_item", tags=["Shopping Cart"])
async def increase_item_cart(cart_increase:cart.CartIncresase,db: Session = Depends(get_db),current_user:int=Depends(oauth2.get_current_user),origin: str = Header(None)):
        id=dict(current_user["token_data"])["id"] 
        user_email=db.query(models.User).filter(models.User.id==id).first()
        cart_all=db.query(models_cart.Cart).filter(models_cart.Cart.owner_email==user_email.email, models_cart.Cart.product_name==cart_increase.product_name)
        shoes_stock=db.query(product_models.Shoes).filter(product_models.Shoes.name==cart_increase.product_name).first().shoes_stock
      
        if cart_all.first()==None:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with id:{id} not found")
        cart_value=cart_all.first().product_quantity
        if shoes_stock<=cart_value:
             return {"status":"not in stock"}
             

        cart_all.update({"product_quantity":cart_value+1},synchronize_session=False)
        db.commit()
        #if str(origin)=="http://localhost:3000":
        if origin_matches_frontend(origin):
         # Iterate over connected WebSocket clients and send a message
         await client_signal()
        return {"status":"ok"}

# disminuir cantidad de un producto
@router.put("/api/cart/decrease_cart_item", tags=["Shopping Cart"])
async def decrease_item_cart(cart_increase:cart.CartIncresase,db: Session = Depends(get_db),current_user:int=Depends(oauth2.get_current_user),origin: str = Header(None)):
        id=dict(current_user["token_data"])["id"] 
        user_email=db.query(models.User).filter(models.User.id==id).first()
        cart_all=db.query(models_cart.Cart).filter(models_cart.Cart.owner_email==user_email.email, models_cart.Cart.product_name==cart_increase.product_name)
        if cart_all.first()==None:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with id:{id} not found")
        cart_value=cart_all.first().product_quantity
        # Si la cantidad sería menor o igual a 0 tras la resta, eliminar el item
        if cart_value <= 1:
            cart_all.delete(synchronize_session=False)
            db.commit()
            #if str(origin)=="http://localhost:3000":
            if origin_matches_frontend(origin):
                # Notify frontend
                await client_signal()
            return {"status":"deleted"}

        cart_all.update({"product_quantity":cart_value-1},synchronize_session=False)
        db.commit()
        #if str(origin)=="http://localhost:3000":
        if origin_matches_frontend(origin):
            # Iterate over connected WebSocket clients and send a message
            await client_signal()
        return {"status":"ok"}

# eliminar item del carrito
@router.get("/api/cart/delete_cart_item/{name}", tags=["Shopping Cart"])
async def delete_item_cart(name:str,db: Session = Depends(get_db),current_user:int=Depends(oauth2.get_current_user),origin: str = Header(None)):
        id=dict(current_user["token_data"])["id"] 
        user_email=db.query(models.User).filter(models.User.id==id).first()
        cart_all=db.query(models_cart.Cart).filter(models_cart.Cart.owner_email==user_email.email, models_cart.Cart.product_name==name)
        if cart_all.first()==None:
           raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"cart item with name:{name} not found")
        cart_all.delete(synchronize_session=False)
        db.commit()
        #if str(origin)=="http://localhost:3000":
        if origin_matches_frontend(origin):
         # Iterate over connected WebSocket clients and send a message
         await client_signal()
        return {"message":"deleted"}

# actualizar talla de la montura
## queda pendiente cambiar el tipo de string 
# @router.put("/api/cart/set_item_size", tags=["Shopping Cart"])
# async def update_size_mount_in_cart(size:schemas_product.ProductSize,db: Session = Depends(get_db),current_user:int=Depends(oauth2.get_current_user),origin: str = Header(None)):  
#        id=dict(current_user["token_data"])["id"] 
#        user_email=db.query(models.User).filter(models.User.id==id).first()
#        cart_all=db.query(models_cart.Cart).filter(models_cart.Cart.owner_email==user_email.email, models_cart.Cart.product_name==size.product_name)
#        if cart_all.first()==None:
#           raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with id:{id} not found")
#        cart_all.update({"size":size.size},synchronize_session=False)
#        db.commit()
#        #if str(origin)=="http://localhost:3001":
#        if origin_matches_frontend(origin):
#          # Iterate over connected WebSocket clients and send a message
#          await client_signal()
#        return {"message":"size set"}
