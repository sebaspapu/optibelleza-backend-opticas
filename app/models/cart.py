from app.db.session import Base
from sqlalchemy import Column, Integer, String, Boolean,ForeignKey,Text,LargeBinary
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy import text
from sqlalchemy.orm import relationship

class Cart(Base):
    __tablename__ = "cart"
    order_id = Column(Integer, primary_key=True, nullable=False)
    product_id = Column(Integer, ForeignKey("shoes.id", ondelete="CASCADE"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner_email = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    price = Column(Integer, nullable=False)
    # size = Column(Integer, nullable=False, server_default=text("9"))
    product_image = Column(Text, nullable=False)
    shoes_category = Column(String, nullable=False)
    product_quantity = Column(Integer, nullable=False, server_default=text("1"))