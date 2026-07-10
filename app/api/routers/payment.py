
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
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
import stripe
from app.core.config import settings, origin_matches_frontend
from typing import List
from stripe.error import SignatureVerificationError
from app.infra.email import send_order_notification

logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=['Payments'])

# Configurar Stripe con tu clave secreta
# CRITERIO: SDK oficial de Stripe integrado y configurado (clave API)
stripe.api_key = settings.stripe_secret_key
logger.info(f"🔐 Stripe API key configurada: {stripe.api_key[:8]}********")


# URL base para redirecciones después del pago
YOUR_DOMAIN = settings.frontend_base_url

@router.post("/api/checkout/create-session")
async def create_checkout_session(
    db: Session = Depends(get_db),
    current_user: dict = Depends(oauth2.get_current_user)
):
    try:
        logger.info("=== Iniciando proceso de checkout ===")
        # CRITERIO: Endpoint que genera la sesión de checkout usando los items del carrito en BD
        # Obtener el ID del usuario del token
        user_id = dict(current_user["token_data"])["id"]
        logger.info(f"📱 Usuario ID: {user_id}")
        
        # Obtener los items del carrito del usuario
        cart_items = db.query(models_cart.Cart).filter(models_cart.Cart.owner_id == user_id).all()
        logger.info(f"🛒 Items en carrito encontrados: {len(cart_items)}")

        if not cart_items:
            logger.warning("❌ Error: Carrito vacío")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No hay items en el carrito"
            )

        # Verificar que el usuario exista (fuente de verdad antes de usar user.email)
        user = db.query(models_user.User).filter(models_user.User.id == user_id).first()
        if not user:
            logger.warning(f"❌ Usuario no encontrado user_id={user_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Transformar items del carrito al formato que Stripe necesita
        # CRITERIO: Se construyen los `line_items` desde la BD (precio tomado de `Shoes`) y se agrupan por producto
        logger.info("🔄 Transformando items para Stripe:")

        # Agrupar items por product_id para evitar line_items duplicados y tomar precio desde la tabla Shoes
        agg = {}
        for it in cart_items:
            pid = it.product_id
            if pid not in agg:
                agg[pid] = {"qty": 0, "row": it}
            agg[pid]["qty"] += it.product_quantity

        line_items = []
        for pid, info in agg.items():
            row = info["row"]
            total_qty = info["qty"]

            # Validar existencia del producto y obtener precio actual desde la tabla Shoes
            product = db.query(product_models.Shoes).filter(product_models.Shoes.id == pid).first()
            if not product:
                # CRITERIO: Manejo de flujo de negocio — producto inexistente devuelve 404
                logger.warning(f"❌ Producto no encontrado en BD product_id={pid}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product {pid} not found")

            # Verificar stock mínimo
            try:
                stock = int(product.shoes_stock or 0)
            except Exception:
                stock = 0
            if stock < total_qty:
                # CRITERIO: Manejo de flujo de negocio — stock insuficiente devuelve 400
                logger.warning(f"❌ Stock insuficiente product_id={pid} stock={stock} requested={total_qty}")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Insufficient stock for product {product.name}")

            logger.info(f"  📦 Producto: {product.name}")
            logger.info(f"     - Cantidad total: {total_qty}")
            logger.info(f"     - Precio tomado de BD: ${product.price} USD")

            line_items.append({
                'price_data': {
                    'currency': 'cop',
                    'product_data': {
                        'name': product.name,
                        'images': [product.product_image] if product.product_image else [],
                        # Guardamos el product_id en metadata para poder mapearlo desde el webhook
                        'metadata': {
                            'product_id': str(product.id)
                        }
                    },
                    'unit_amount': int(product.price * 100),  # Stripe necesita el precio en centavos
                },
                'quantity': total_qty,
            })

        # CRITERIO: `line_items` ya están consolidados y validados para enviar a Stripe
        logger.info(f"🔢 Line items finales para Stripe: {len(line_items)}")

        logger.info("🔐 Configurando sesión de Stripe:")
        logger.info(f"  💳 API Key configurada: {stripe.api_key[:10]}...")
        logger.info(f"  🌐 Domain configurado: {YOUR_DOMAIN}")
        
        try:
            # Obtener el usuario
            user = db.query(models_user.User).filter(models_user.User.id == user_id).first()
            
            # Buscar o crear un cliente de Stripe para este usuario
            customers = stripe.Customer.list(email=user.email, limit=1)
            if customers.data:
                customer = customers.data[0]
                logger.info(f"📋 Cliente existente encontrado: {customer.id}")
            else:
                # Crear nuevo cliente en Stripe
                customer = stripe.Customer.create(
                    email=user.email,
                    name=user.user_name,
                    metadata={
                        'user_id': str(user_id)
                    }
                )
                logger.info(f"✨ Nuevo cliente creado: {customer.id}")
            
            # CRITERIO: success_url y cancel_url están configurados en la creación de la sesión de Stripe
            # Crear la sesión de checkout en Stripe
            checkout_session = stripe.checkout.Session.create(
                customer=customer.id,  # Usar el ID del cliente en lugar de solo el email
                line_items=line_items,
                mode='payment',
                payment_method_types=['card'],
                payment_intent_data={
                    'setup_future_usage': 'off_session'  # Esto guardará la tarjeta para uso futuro
                },
                success_url=f"{YOUR_DOMAIN}/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{YOUR_DOMAIN}/checkout/cancel",
                metadata={
                    'user_id': str(user_id)
                }
            )
            
            logger.info("✅ Sesión de Stripe creada exitosamente")
            logger.info(f"🔗 URL de checkout: {checkout_session.url}")
            # CRITERIO: El endpoint devuelve la URL de la sesión de pago al cliente
            return {"url": checkout_session.url}
            
        except stripe.StripeError as e:
            # CRITERIO: Manejo de errores de la API de Stripe — se captura y se devuelve 500
            logger.error(f"❌ Error de Stripe: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error de Stripe: {str(e)}"
            )

    except HTTPException:
        logger.warning("HTTPException lanzada en checkout: será propagada")
        raise
    except Exception as e:
        logger.error(f"Error inesperado en checkout: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/api/webhooks/stripe")
#@router.post("/webhook")  # Cambiada la ruta a /webhook para simplicidad
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    # HU: checkout.session.completed -> see handling below
    # A: event handling, B: extract details, C: persist orders
    logger.info("=== Webhook de Stripe recibido ===")
    # Obtener el payload raw para verificar la firma
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    logger.info("📨 Recibida notificación de Stripe")
    
    if not sig_header:
        logger.warning("❌ Error: No se encontró la firma de Stripe")
        raise HTTPException(status_code=400, detail="No Stripe signature found")
    
    try:
        # Verify Stripe signature and construct event
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
        logger.info(f"✅ Firma verificada correctamente")
        logger.info(f"📝 Tipo de evento: {event['type']}")
        
        # Handle checkout.session.completed
        if event['type'] == 'checkout.session.completed':
            # session object from Stripe
            session = event['data']['object']

            # Usar la sesión `db` inyectada por Depends; no crear una nueva
            # Evitar `next(get_db())` porque genera una sesión distinta y puede provocar transacciones anidadas
            try:
                logger.info("=== Verificando sesión de pago ===")

                # Retrieve session and details (metadata, payment_intent, line_items)
                checkout_session = stripe.checkout.Session.retrieve(
                    session.id,
                    expand=['payment_intent', 'line_items']
                )
                logger.info(f"💳 ID de sesión: {checkout_session.id}")
                logger.info(f"💰 Estado del pago: {checkout_session.payment_status}")

                # Obtener el user_id de los metadatos (manejo robusto)
                user_id_raw = None
                try:
                    meta = getattr(checkout_session, 'metadata', None)
                    if meta:
                        # metadata puede ser dict-like o StripeObject
                        try:
                            user_id_raw = meta.get('user_id')
                        except Exception:
                            user_id_raw = getattr(meta, 'get', lambda k: None)('user_id') if hasattr(meta, 'get') else None
                except Exception as me:
                    logger.warning(f"No se pudo leer metadata de checkout_session: {me}")

                # Fallback: intentar obtener user_id desde el customer metadata
                if not user_id_raw:
                    try:
                        customer_ref = None
                        try:
                            customer_ref = checkout_session.get('customer') if isinstance(checkout_session, dict) else getattr(checkout_session, 'customer', None)
                        except Exception:
                            customer_ref = getattr(checkout_session, 'customer', None)

                        if customer_ref:
                            cust = stripe.Customer.retrieve(customer_ref)
                            cm = getattr(cust, 'metadata', {}) or {}
                            user_id_raw = cm.get('user_id')
                            logger.info(f"Obtenido user_id desde customer metadata: {user_id_raw}")
                    except Exception as ce:
                        logger.warning(f"No se pudo obtener user_id desde customer: {ce}")

                if not user_id_raw:
                    logger.error("No se encontró user_id en checkout_session.metadata ni en customer.metadata")
                    raise HTTPException(status_code=400, detail="Missing user_id in checkout session metadata")

                try:
                    user_id = int(user_id_raw)
                except Exception as e:
                    logger.error(f"user_id inválido en metadata: {user_id_raw} error: {e}")
                    raise HTTPException(status_code=400, detail="Invalid user_id in checkout session metadata")
                logger.info(f"👤 Usuario ID: {user_id}")

                # Obtener los items del carrito
                cart_items = db.query(models_cart.Cart).filter(models_cart.Cart.owner_id == user_id).all()
                if not cart_items:
                    logger.info("⚠️ Advertencia: No se encontraron items en el carrito")

                # Crear la orden
                logger.info("=== Procesando pago completado ===")
                user = db.query(models_user.User).filter(models_user.User.id == user_id).first()
                if not user:
                    logger.warning("❌ Error: Usuario no encontrado")
                    raise HTTPException(status_code=404, detail="User not found")

                # Debug: mostrar elementos del carrito antes de procesar
                logger.info(f"🛒 Cart items to process: {len(cart_items)}")
                for it in cart_items:
                    logger.info(f"   - cart item product_id={it.product_id} name={it.product_name} qty={it.product_quantity} price={it.price}")

                    # Procesar la creación de órdenes y actualización de stock en una transacción
                    try:
                        # Idempotencia: si ya existe una orden asociada a esta sesión, no procesar de nuevo
                        existing = db.query(models_orders.Orders).filter(models_orders.Orders.stripe_session_id == checkout_session.id).first()
                        if existing:
                            logger.info(f"♻️ Webhook idempotente: sesión {checkout_session.id} ya procesada. Skipping.")
                            return {"status": "already_processed"}

                        # Obtener los line_items reales desde Stripe (contienen cantidad y precio unitario)
                        line_items_resp = stripe.checkout.Session.list_line_items(checkout_session.id, limit=100)

                        # Si la sesión ya tiene una transacción activa, usamos begin_nested()
                        # para crear un SAVEPOINT y evitar el error de "A transaction is already begun"
                        if getattr(db, 'in_transaction', None) and db.in_transaction():
                            tx = db.begin_nested()
                        else:
                            tx = db.begin()
                        with tx:
                            # Recuperar payment_intent del checkout session si existe
                            # Extraer siempre el ID del payment_intent (puede venir como objeto expandido o como string)
                            payment_intent_id = None
                            try:
                                pi_raw = checkout_session.payment_intent
                            except Exception:
                                try:
                                    pi_raw = checkout_session.get('payment_intent') if isinstance(checkout_session, dict) else None
                                except Exception:
                                    pi_raw = None

                            # Normalizar a string id
                            if pi_raw is None:
                                payment_intent_id = None
                            else:
                                # si es objeto Stripe (PaymentIntent), extraer .id
                                if hasattr(pi_raw, 'id'):
                                    payment_intent_id = pi_raw.id
                                elif isinstance(pi_raw, dict) and pi_raw.get('id'):
                                    payment_intent_id = pi_raw.get('id')
                                else:
                                    # fallback a string
                                    payment_intent_id = str(pi_raw)

                            logger.info(f"🔎 payment_intent_id resuelto: {payment_intent_id}")

                            # Persist order lines in DB (create Orders)
                            # Note: currently creates one DB row per line_item
                            for li in line_items_resp.data:
                                # Obtener precio unitario en centavos y cantidad
                                unit_amount = getattr(li.price, 'unit_amount', None) or li.price.get('unit_amount')
                                qty = li.quantity

                                # Intentar obtener product_id que guardamos en product metadata cuando creamos la sesión
                                product_id = None
                                try:
                                    stripe_product_id = getattr(li.price, 'product', None) or li.price.get('product')
                                    if stripe_product_id:
                                        stripe_product = stripe.Product.retrieve(str(stripe_product_id))
                                        prod_meta = stripe_product.metadata or {}
                                        if prod_meta.get('product_id'):
                                            product_id = int(prod_meta.get('product_id'))
                                except Exception as e:
                                    logger.warning(f"No se pudo leer metadata del producto en Stripe: {e}")

                                # Fallback: intentar mapear por nombre/qty desde cart_items
                                if product_id is None:
                                    matched = None
                                    for c in cart_items:
                                        if c.product_quantity == qty and not matched:
                                            matched = c
                                    if matched:
                                        product_id = matched.product_id

                                if product_id is None:
                                    logger.error(f"❌ No se pudo determinar product_id para line_item: {li}")
                                    raise Exception("No se pudo mapear line_item a product_id")

                                # Crear la orden usando el precio tomado de Stripe (unit_amount en centavos)
                                paid_total = (unit_amount or 0) * (qty or 1)
                                unit_price_dollars = int((unit_amount or 0) / 100)

                                new_order = models_orders.Orders(
                                    product_id=product_id,
                                    owner_id=user_id,
                                    owner_name=user.user_name,
                                    owner_email=user.email if user and hasattr(user, 'email') else '',
                                    user_address=user.user_address if user and hasattr(user, 'user_address') else '',
                                    product_name=getattr(li, 'description', f'Product {product_id}'),
                                    product_quantity=qty,
                                    price=unit_price_dollars,
                                    paid_amount=paid_total,
                                    product_image="",
                                    # size=0,
                                    shoes_category="",
                                    order_status="paid",
                                    payment="stripe",
                                    shipping_method="standard",
                                    stripe_session_id=checkout_session.id,
                                    payment_intent_id=payment_intent_id
                                )
                                db.add(new_order)
                                logger.info(f"✅ Orden creada (Stripe price) para product_id={product_id} qty={qty} paid={paid_total}cents")

                                # Nota: el decremento de stock se difiere hasta el flujo de fulfillment
                                # (se validará y decrementará al marcar la orden como 'shipped' en order.py)

                            # Eliminar todos los items del carrito del usuario en una sola operación
                            deleted = db.query(models_cart.Cart).filter(models_cart.Cart.owner_id == user_id).delete(synchronize_session=False)
                            logger.info(f"🗑️  Carrito limpiado, rows deleted: {deleted}")

                        # Al salir del context la transacción se comitea automáticamente si no hubo excepciones
                        logger.info("✅ Transaction committed: orders created and cart cleared")

                        # Enviar notificación por correo a la propietaria
                        created_orders = db.query(models_orders.Orders)\
                            .filter(models_orders.Orders.stripe_session_id == checkout_session.id)\
                            .all()

                        send_order_notification(created_orders)
                    except Exception as te:
                        # Si ocurre cualquier error dentro de la transacción, se hace rollback automáticamente al salir del context
                        logger.error(f"❌ Error durante transacción de ordenes: {te}")
                        raise

            except Exception as e:
                # Si algo falló, aseguramos rollback de la sesión inyectada
                try:
                    db.rollback()
                except Exception:
                    pass
                logger.error(f"Error procesando la orden: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error procesando la orden: {str(e)}"
                )
            
        return {"status": "success"}
        
    except SignatureVerificationError as e:
        logger.warning(f"Firma inválida: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Firma inválida: {str(e)}")
    except Exception as e:
        logger.error(f"Error inesperado en webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )