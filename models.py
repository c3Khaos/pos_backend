from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime



class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), default='user', nullable=False)


    sales = db.relationship("Sale", back_populates="seller")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "username": self.username,"email":self.email,"role":self.role}
    
class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)

    total_amount = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    change_given = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    sale_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    seller = db.relationship("User", back_populates="sales")

    items = db.relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")

    def to_dict(self):
        change = self.amount_paid-self.total_amount
        return {
            "id " : self.id,
            "sale_number":f"SALE-{self.id}",
            "total_amount":self.total_amount,
            "amount_paid": self.amount_paid,
            "change": change,
            "payment_method":self.payment_method,
            "sale_date":self.sale_date.isoformat(),
            "user":self.seller.username if self.seller else None,
            "items": [item.to_dict() for item in self.items]

        }
    
class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False) 
    product_id = db.Column(db.Integer, nullable=False) 
    name = db.Column(db.String(120), nullable=False) 
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False) 

    sale = db.relationship("Sale", back_populates="items") # Link back to the Sale model

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "name": self.name,
            "quantity": self.quantity,
            "price": self.price
        }

    
class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)


    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "stock": self.stock,
        }
