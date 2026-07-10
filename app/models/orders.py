from app.db.session import Base
from sqlalchemy import Column, Integer, String, Boolean,ForeignKey,Text,LargeBinary
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy import text
from sqlalchemy.orm import relationship


class Orders(Base):
    __tablename__ = "orders"
    order_id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    product_id = Column(Integer, ForeignKey("shoes.id", ondelete="SET NULL"), nullable=True)
    owner_name = Column(String, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner_email = Column(String, nullable=False)
    user_address = Column(String, nullable=False, server_default=text("'None'"))
    product_name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    product_image = Column(Text, nullable=False)
    shoes_category = Column(String, nullable=False)
    # size = Column(Integer, nullable=False, server_default=text("9"))
    product_quantity = Column(Integer, nullable=False, server_default=text("1"))
    order_status = Column(String, nullable=False, server_default=text("'processing'"))
    payment = Column(String, nullable=False)
    shipping_method = Column(String, nullable=False, server_default=text("'processing'"))
    ordered_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text('CURRENT_TIMESTAMP'))
    # Stripe integration fields
    stripe_session_id = Column(String, nullable=True, unique=False)
    payment_intent_id = Column(String, nullable=True)
    # paid_amount in cents (integer) to record the amount actually charged by Stripe per order line
    paid_amount = Column(Integer, nullable=True)
    # Indica si el stock ya fue decrementado para esta orden (evitar doble decremento)
    # Use boolean literal for server_default so Postgres accepts it, and default
    # at ORM level to ensure sensible Python-side defaults.
    stock_decremented = Column(Boolean, nullable=False, default=False, server_default=text('false'))