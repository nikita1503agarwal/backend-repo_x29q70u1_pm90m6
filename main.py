import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
from jose import jwt, JWTError
from passlib.context import CryptContext

from database import db, create_document, get_documents
from schemas import User as UserSchema, Product as ProductSchema, Order as OrderSchema

# Environment
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALG = "HS256"
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="E-commerce API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------- Utility ---------------------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_token(data: dict, expires_minutes: int = 60 * 24) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALG)


class AuthUser(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str = "customer"


def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[AuthUser]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid auth scheme")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return AuthUser(**{
            "id": payload.get("id"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "role": payload.get("role", "customer"),
        })
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[AuthUser]:
    if not authorization or authorization.strip().lower() == "bearer guest-token":
        return None
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return AuthUser(**{
            "id": payload.get("id"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "role": payload.get("role", "customer"),
        })
    except Exception:
        return None

# --------------------- Models ---------------------

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProductCreate(ProductSchema):
    pass


class ProductOut(ProductSchema):
    id: str


class OrderCreate(OrderSchema):
    pass


class PaymentIntentRequest(BaseModel):
    amount: int
    currency: str = "usd"


# --------------------- Routes ---------------------

@app.get("/")
def root():
    return {"message": "E-commerce API is running"}


@app.get("/schema")
def get_schema():
    # Minimal schema surface for viewer
    from schemas import User, Product, Order
    return {
        "user": User.model_json_schema(),
        "product": Product.model_json_schema(),
        "order": Order.model_json_schema(),
    }


# Auth
@app.post("/api/auth/register")
def register(req: RegisterRequest):
    existing = db["user"].find_one({"email": req.email}) if db else None
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = UserSchema(
        name=req.name,
        email=req.email,
        password_hash=hash_password(req.password),
        address=None,
        role="customer",
        is_active=True,
    )
    user_id = create_document("user", user_doc)
    token = create_token({"id": user_id, "email": req.email, "name": req.name, "role": "customer"})
    return {"token": token, "user": {"id": user_id, "email": req.email, "name": req.name, "role": "customer"}}


@app.post("/api/auth/login")
def login(req: LoginRequest):
    user = db["user"].find_one({"email": req.email}) if db else None
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_token({"id": str(user.get("_id")), "email": user["email"], "name": user["name"], "role": user.get("role", "customer")})
    return {"token": token, "user": {"id": str(user.get("_id")), "email": user["email"], "name": user["name"], "role": user.get("role", "customer")}}


# Products
@app.get("/api/products")
def list_products(q: Optional[str] = None, category: Optional[str] = None, limit: int = 20):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    query: Dict[str, Any] = {}
    if q:
        query["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category"] = category

    # Seed a few demo products if empty
    if db["product"].count_documents({}) == 0:
        samples = [
            {
                "title": "T-shirt Bio Confort",
                "description": "Coton bio ultra doux, coupe moderne",
                "price": 24.9,
                "category": "Vêtements",
                "images": ["https://images.unsplash.com/photo-1520975682031-a6c2b9d8b5f4?w=1200&q=80"],
                "stock": 120,
                "rating": 4.6,
            },
            {
                "title": "Casque Sans Fil Pro",
                "description": "Réduction de bruit active, 30h d'autonomie",
                "price": 129.0,
                "category": "Electronique",
                "images": ["https://images.unsplash.com/photo-1518443206315-4e1dff4a1f0f?w=1200&q=80"],
                "stock": 42,
                "rating": 4.7,
            },
            {
                "title": "Gourde Isotherme 1L",
                "description": "Inox double paroi, garde au frais 24h",
                "price": 19.9,
                "category": "Sport",
                "images": ["https://images.unsplash.com/photo-1563371351-e53ebb744a1f?w=1200&q=80"],
                "stock": 300,
                "rating": 4.5,
            },
        ]
        for s in samples:
            create_document("product", ProductSchema(**s))

    docs = get_documents("product", query, limit)
    out = []
    for d in docs:
        d["id"] = str(d.pop("_id", ""))
        out.append(d)
    return out


@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    from bson import ObjectId
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    try:
        doc = db["product"].find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product id")
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    doc["id"] = str(doc.pop("_id"))
    return doc


# Basic admin create product (for demo). Protect by role.
@app.post("/api/admin/products")
def create_product(body: ProductCreate, user: AuthUser = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    product_id = create_document("product", body)
    return {"id": product_id}


# Orders
@app.post("/api/orders")
def create_order(body: OrderCreate, user: Optional[AuthUser] = Depends(get_optional_user)):
    # attach guest user if none
    if user is None:
        body.user_id = body.user_id or "guest"
    else:
        body.user_id = user.id
    if len(body.items) == 0 or body.total < 0:
        raise HTTPException(status_code=400, detail="Invalid order")
    order_id = create_document("order", body)
    return {"id": order_id, "status": "created"}


@app.get("/api/orders/mine")
def my_orders(user: AuthUser = Depends(get_current_user)):
    orders = get_documents("order", {"user_id": user.id}, limit=50)
    for o in orders:
        o["id"] = str(o.pop("_id", ""))
    return orders


# Payments (Stripe or mock)
@app.post("/api/checkout/create-payment-intent")
def create_payment_intent(req: PaymentIntentRequest):
    if STRIPE_SECRET_KEY:
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET_KEY
            intent = stripe.PaymentIntent.create(amount=req.amount, currency=req.currency, payment_method_types=["card"]) 
            return {"clientSecret": intent.client_secret}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Stripe error: {str(e)[:100]}")
    # Mock if Stripe not configured
    return {"clientSecret": "mock_client_secret"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            import os as _os
            response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
