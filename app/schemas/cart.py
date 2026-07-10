from pydantic import BaseModel, EmailStr
from datetime import datetime
from fastapi import UploadFile,File,Form
from typing import Optional,List

class CartBase(BaseModel):
    product_image:str
    product_name:str
    price:int
    product_quantity:int
    # size:int

class CartOut(BaseModel):
    product_name:str
    product_quantity:int
    price:int
    # size:int
    product_image:str
    shoes_category:str
    class Config:
        from_attributes=True

class OutOfStockMessage(BaseModel):
    status: str
    class Config:
        from_attributes=True

class CartIncresase(BaseModel):
    
    product_name:str

class CartAdd(BaseModel):
    id: int
    product_quantity:int
    # size:int