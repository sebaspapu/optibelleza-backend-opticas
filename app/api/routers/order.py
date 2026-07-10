from fastapi import FastAPI,Depends,HTTPException,APIRouter,status,Header
import stripe
from sqlalchemy.orm import Session
from app.db.session import get_db

#modelos
from app.models import orders as models_orders
from app.models import product as product_models
from app.models import user as models_user
from app.models import cart as models_cart

#schemas
from app.schemas import order as schemas_order
from app.schemas import product as schemas_product
from app.schemas import user as schemas_user
from app.schemas import cart as schemas_cart


from app.core import oauth2
from app.infra.websocket import websocket_connections, websocket_connections_admin
from app.core.config import settings, origin_matches_frontend
from app.infra.email import send_order_notification

router=APIRouter()

stripe.api_key = settings.stripe_secret_key

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

# obtener todas las órdenes del sistema
@router.get("/api/order/all_order", tags=["Order Management"])
def get_all_orders(db: Session = Depends(get_db),current_user:dict=Depends(oauth2.get_current_user)):
    orders=db.query(models_orders.Orders).all()
    return orders

#Obtener todas las órdenes del usuario actual
@router.get("/api/order/current_user_all_order", tags=["Order Management"])
def get_current_user_orders(db: Session = Depends(get_db),current_user:dict=Depends(oauth2.get_current_user)):
    id=dict(current_user["token_data"])["id"]
    orders=db.query(models_orders.Orders).filter(models_orders.Orders.owner_id==id).all()
    return orders

# crear una nueva orden
@router.post("/api/order/add_order", tags=["Order Management"])
async def create_order(order:schemas_order.OrderAdd,db: Session = Depends(get_db),current_user:dict=Depends(oauth2.get_current_user),origin: str = Header(None)):
    id=dict(current_user["token_data"])["id"]
    user_email=db.query(models_user.User).filter(models_user.User.id==id).first()
    cart_items=db.query(models_cart.Cart).filter(models_cart.Cart.owner_id==id).all()
    products=db.query(product_models.Shoes).all()
    
    line_items = []

    for cart_item in cart_items:
        # Create an order item with data from the cart item
        order_item = models_orders.Orders()
        for column in models_orders.Orders.__table__.columns:
            if column.name == "order_id":
                continue  # No copiar el ID

            if hasattr(cart_item, column.name):
                setattr(order_item, column.name, getattr(cart_item, column.name))
        
        # Manually set additional attributes for the order item
        # NOTE: No decrementar stock aquí — se hará cuando el admin marque la orden como 'shipped'
        order_item.user_address = order.user_address
        order_item.payment = order.payment 
        order_item.shipping_method = order.shipping_method
        order_item.owner_id=id
        order_item.owner_name=user_email.user_name
        order_item.owner_email = user_email.email   # Set additional attribute
        # Estado inicial: pendiente de fulfillment (no hemos decrementado stock aún)
        order_item.order_status = "pending"
        order_item.stock_decremented = False

        item_total = cart_item.price * cart_item.product_quantity
        order_item.paid_amount = item_total * 100
        order_item.total_price = item_total
        
        db.add(order_item)

        # Add to stripe line items
        line_items.append({
            'price_data': {
                'currency': 'cop',
                'product_data': {
                    'name': cart_item.product_name,
                },
                'unit_amount': int(cart_item.price * 100),
            },
            'quantity': cart_item.product_quantity,
        })

    db.query(models_cart.Cart).filter(models_cart.Cart.owner_id==id).delete(synchronize_session=False)
    
   
   
    db.commit()
    # Enviar notificación por correo a la propietaria después del commit
    created_orders = (
    db.query(models_orders.Orders)
    .filter(models_orders.Orders.owner_id == id)
    .order_by(models_orders.Orders.ordered_at.desc())
    .limit(len(cart_items))
    .all()
    )

    send_order_notification(created_orders)

    if not origin_matches_frontend(origin):
        await admin_signal()

    # Create Stripe Checkout Session (ensure customer + metadata so webhook can find user_id)
    try:
        # Buscar o crear cliente en Stripe con metadata user_id
        try:
            customers = stripe.Customer.list(email=user_email.email, limit=1)
            if customers.data:
                customer = customers.data[0]
            else:
                customer = stripe.Customer.create(
                    email=user_email.email,
                    name=user_email.user_name,
                    metadata={"user_id": str(id)}
                )
        except Exception as sc_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creando/obteniendo customer en Stripe: {sc_err}")

        try:
            checkout_session = stripe.checkout.Session.create(
                customer=customer.id,
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url=f"{settings.frontend_base_url}/orders?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{settings.frontend_base_url}/checkout",
                metadata={"user_id": str(id)}
            )
            return {"checkout_url": checkout_session.url}
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creando sesión de Stripe: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# eliminar una orden
@router.get("/api/order/delete_order/{id}", tags=["Order Management"])
def delete_order_by_id(id:int,db: Session = Depends(get_db),current_user:dict=Depends(oauth2.get_current_user)):
     order_query=db.query(models_orders.Orders).filter(models_orders.Orders.order_id==id)
     order=order_query.first()
     if order==None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with id:{id} not found")
    
     order_query.delete(synchronize_session=False)
     db.commit()
     return {"message":"deleted"}

# actualizar estado de una orden
@router.put("/api/order/update_status/{id}", tags=["Order Management"])
async def update_order_status_by_id(id:int,order_status:schemas_order.status_update,db: Session = Depends(get_db),current_user:dict=Depends(oauth2.get_current_user),origin: str = Header(None)):
    order_query=db.query(models_orders.Orders).filter(models_orders.Orders.order_id==id)
    order=order_query.first()
    if order==None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with id:{id} not found")
    # Obtener el nuevo estado que se quiere aplicar
    new_status = order_status.order_status

    # Si el nuevo estado es uno que implica envío/finalización, decrementamos stock
    should_decrement_on_status = new_status.lower() in ["shipped", "enviado", "sent"]

    try:
        if should_decrement_on_status and not getattr(order, 'stock_decremented', False):
            # Validar stock actual antes de decrementar (fulfillment)
            shoes_row = db.query(product_models.Shoes).filter(product_models.Shoes.id == order.product_id).first()
            if not shoes_row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {order.product_id} not found")
            current_stock = int(shoes_row.shoes_stock or 0)
            if current_stock < order.product_quantity:
                # No hay stock suficiente para enviar la orden
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Insufficient stock to ship order {id}: available={current_stock} required={order.product_quantity}")

            # Decrementar stock sólo si no se ha hecho antes para esta orden (idempotente)
            db.query(product_models.Shoes).filter(product_models.Shoes.id==order.product_id).update({
                "shoes_stock": product_models.Shoes.shoes_stock - order.product_quantity
            }, synchronize_session=False)
            # Marcar que el stock fue decrementado
            update_payload = order_status.dict()
            update_payload.update({"stock_decremented": True})
            order_query.update(update_payload, synchronize_session=False)
        else:
            # Simplemente actualizar el estado
            order_query.update(order_status.dict(),synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    if origin_matches_frontend(origin):
        # Iterate over connected WebSocket clients and send a message
        await client_signal()
    return {"data":"sucess"}