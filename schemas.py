"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- Order -> "order" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user"
    """
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="Password hash (server-side)")
    address: Optional[str] = Field(None, description="Primary shipping address")
    role: str = Field("customer", description="Role: customer | admin")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product"
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    stock: int = Field(0, ge=0, description="Units in stock")
    rating: float = Field(0, ge=0, le=5, description="Average rating 0-5")

class OrderItem(BaseModel):
    product_id: str = Field(..., description="Product ObjectId as string")
    title: str
    price: float
    quantity: int = Field(..., ge=1)
    image: Optional[str] = None

class ShippingInfo(BaseModel):
    full_name: str
    address: str
    city: str
    postal_code: str
    country: str

class Order(BaseModel):
    """
    Orders collection schema
    Collection name: "order"
    """
    user_id: str = Field(..., description="User ObjectId as string")
    items: List[OrderItem]
    subtotal: float = Field(..., ge=0)
    shipping: float = Field(0, ge=0)
    total: float = Field(..., ge=0)
    status: str = Field("pending", description="pending | paid | shipped | delivered | cancelled")
    payment_id: Optional[str] = Field(None, description="External payment reference")
    shipping_info: ShippingInfo
