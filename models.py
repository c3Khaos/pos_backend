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
    active = db.Column(db.Boolean, default=True, nullable=False)


    sales = db.relationship("Sale", back_populates="seller")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "username": self.username,"email":self.email,"role":self.role,"active":self.active}
    
class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)

    transaction_id = db.Column(db.String(100), unique=True, nullable=True, index=True)

    total_amount = db.Column(db.Float, nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    change_given = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    sale_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    seller = db.relationship("User", back_populates="sales")
    items = db.relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")

    customer_name  = db.Column(db.String(100), nullable=True)
    customer_phone = db.Column(db.String(20),  nullable=True)
    payment_status = db.Column(db.String(20),  default='paid')

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
            "customer_name":  self.customer_name,
            "customer_phone": self.customer_phone,
            "payment_status": self.payment_status,
            "items": [item.to_dict() for item in self.items]

        }
    
class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False) 
    product_id = db.Column(db.Integer, nullable=False) 
    name = db.Column(db.String(120), nullable=False) 
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False) 
    profit = db.Column(db.Float,nullable=False)

    sale = db.relationship("Sale", back_populates="items") # Link back to the Sale model

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "name": self.name,
            "quantity": self.quantity,
            "price": self.price,
            "profit":self.profit
        }

    
class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float , nullable = False)
    stock = db.Column(db.Integer, nullable=False)
    barcode = db.Column(db.String,nullable=True, unique=True, index=True)
    sold_loose = db.Column(db.Boolean, default=False, nullable=False)


    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "unit_price": self.unit_price,
            "stock": self.stock,
            "barcode":self.barcode,
            "sold_loose": self.sold_loose,
       }

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "created_at": self.created_at.isoformat()
        }
    
class Expense(db.Model):
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(80), nullable=False)  # rent, electricity, staff, etc
    expense_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "description": self.description,
            "amount": self.amount,
            "category": self.category,
            "expense_date": self.expense_date.isoformat(),
            "recorded_by": self.recorded_by,
            "created_at": self.created_at.isoformat()
        }
    
class MpesaTransaction(db.Model):
    __tablename__ = 'mpesa_transactions'

    id = db.Column(db.Integer, primary_key=True)
    merchant_request_id = db.Column(db.String(100), nullable=True)
    checkout_request_id = db.Column(db.String(100), nullable=True, index=True)
    result_code = db.Column(db.Integer, nullable=True)
    result_desc = db.Column(db.String(255), nullable=True)
    amount = db.Column(db.Float, nullable=True)
    mpesa_receipt_number = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    transaction_date = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "checkout_request_id": self.checkout_request_id,
            "result_code": self.result_code,
            "result_desc": self.result_desc,
            "amount": self.amount,
            "mpesa_receipt_number": self.mpesa_receipt_number,
            "phone_number": self.phone_number,
            "transaction_date": self.transaction_date,
            "created_at": self.created_at.isoformat(),
            "status": "success" if self.result_code == 0 else "failed"
        }

class DebtPayment(db.Model):
    __tablename__ = 'debt_payments'

    id          = db.Column(db.Integer, primary_key=True)
    sale_id     = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    method      = db.Column(db.String(20))  # cash, mpesa, card
    paid_at     = db.Column(db.DateTime, default=db.func.now())
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            "id":          self.id,
            "sale_id":     self.sale_id,
            "amount":      self.amount,
            "method":      self.method,
            "paid_at":     self.paid_at.isoformat() if self.paid_at else None,
            "received_by": self.received_by,
        }