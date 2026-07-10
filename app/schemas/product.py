from pydantic import BaseModel, EmailStr
from datetime import datetime
from fastapi import UploadFile,File,Form
from typing import Optional,List

class ShoesCreate(BaseModel):
#class ProductMountsCreate(BaseModel):
    
    name:str
    price:int
    product_image:str
    shoes_category:str
    shoes_type:str
    shoes_stock:int
    shoes_description:str

class ShoesUpdate(BaseModel):
#class ProductMountsUpdate(BaseModel):
    
    name:str
    price:int
    
    shoes_category:str
    shoes_type:str
    shoes_stock:int
    shoes_description:str

class ProductSize(BaseModel):
    product_name:str
    # size:int

class Shoes(BaseModel):
#class ProductMounts(BaseModel):
    name:str
    price:int
    product_image: str
    shoes_type:str
    shoes_category:str
    id:int
    shoes_stock:int
    shoes_description:str
    