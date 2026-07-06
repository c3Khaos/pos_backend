from extensions import db
from sqlalchemy import Numeric
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

# ── Timestamp serialization helper ──────────────────────────────────────────
def iso_utc(dt):
    """Serialize a datetime as ISO 8601 with explicit UTC marker."""
    return dt.isoformat() + "Z" if dt is not None else None

# ── Default factory for timezone-aware datetime columns ─────────────────────
def utc_now():
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer,     primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False)
    email         = db.Column(db.String(80),  unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(50),  default='user', nullable=False)
    active        = db.Column(db.Boolean,     default=True,   nullable=False)

    sales = db.relationship("Sale", back_populates="seller")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id":       self.id,
            "username": self.username,
            "email":    self.email,
            "role":     self.role,
            "active":   self.active,
        }


class Sale(db.Model):
    __tablename__ = "sales"

    id             = db.Column(db.Integer,        primary_key=True)
    transaction_id = db.Column(db.String(100),    unique=True, nullable=True, index=True)
    total_amount   = db.Column(db.Numeric(10, 2), nullable=False)
    amount_paid    = db.Column(db.Numeric(10, 2), nullable=False)
    change_given   = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50),     nullable=False)
    sale_date      = db.Column(db.DateTime,       nullable=False, default=utc_now)
    user_id        = db.Column(db.Integer,        db.ForeignKey('users.id'))
    customer_name  = db.Column(db.String(100),    nullable=True)
    customer_phone = db.Column(db.String(20),     nullable=True)
    payment_status = db.Column(db.String(20),     default='paid')

    # ── Split payment tracking ────────────────────────────────────────────
    # For pure cash:  cash_amount = total_amount, mpesa_amount = null
    # For pure mpesa: cash_amount = null, mpesa_amount = total_amount
    # For split:      both populated, cash_amount + mpesa_amount = total_amount
    cash_amount    = db.Column(db.Numeric(10, 2), nullable=True)
    mpesa_amount   = db.Column(db.Numeric(10, 2), nullable=True)

    seller = db.relationship("User",     back_populates="sales")
    items  = db.relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id":             self.id,
            "sale_number":    f"SALE-{self.id}",
            "total_amount":   float(self.total_amount),
            "amount_paid":    float(self.amount_paid),
            "change_given":   float(self.change_given),
            "payment_method": self.payment_method,
            "sale_date":      iso_utc(self.sale_date),
            "user":           self.seller.username if self.seller else None,
            "customer_name":  self.customer_name,
            "customer_phone": self.customer_phone,
            "payment_status": self.payment_status,
            "cash_amount":    float(self.cash_amount)  if self.cash_amount  else None,
            "mpesa_amount":   float(self.mpesa_amount) if self.mpesa_amount else None,
            "items":          [item.to_dict() for item in self.items],
        }


class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id         = db.Column(db.Integer,        primary_key=True)
    sale_id    = db.Column(db.Integer,        db.ForeignKey('sales.id'),    nullable=False)
    product_id = db.Column(db.Integer,        db.ForeignKey('products.id'), nullable=False)
    name       = db.Column(db.String(120),    nullable=False)
    quantity   = db.Column(db.Numeric(10, 2), nullable=False)
    price      = db.Column(db.Numeric(10, 2), nullable=False)
    profit     = db.Column(db.Numeric(10, 2), nullable=False)

    sale = db.relationship("Sale", back_populates="items")

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "name":       self.name,
            "quantity":   float(self.quantity),
            "price":      float(self.price),
            "profit":     float(self.profit),
        }


class Product(db.Model):
    __tablename__ = "products"

    id              = db.Column(db.Integer,        primary_key=True)
    name            = db.Column(db.String(80),     nullable=False)
    category        = db.Column(db.String(80),     nullable=False)
    price           = db.Column(db.Numeric(10, 2), nullable=False)
    unit_price      = db.Column(db.Numeric(10, 2), nullable=False)
    wholesale_price = db.Column(db.Numeric(10, 2), nullable=True)
    carton_qty      = db.Column(db.Integer,        nullable=True)
    stock           = db.Column(db.Numeric(10, 2), nullable=False)
    barcode         = db.Column(db.String,         nullable=True, unique=True, index=True)
    sold_loose      = db.Column(db.Boolean,        default=False, nullable=True)

    def to_dict(self):
        return {
            "id":              self.id,
            "name":            self.name,
            "category":        self.category,
            "price":           float(self.price),
            "unit_price":      float(self.unit_price),
            "wholesale_price": float(self.wholesale_price) if self.wholesale_price else None,
            "carton_qty":      self.carton_qty,
            "stock":           float(self.stock),
            "barcode":         self.barcode,
            "sold_loose":      self.sold_loose,
        }


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id         = db.Column(db.Integer,     primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    phone      = db.Column(db.String(20),  nullable=False)
    email      = db.Column(db.String(120), nullable=True)
    address    = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime,    default=utc_now)

    def to_dict(self):
        return {
            "id":         self.id,
            "name":       self.name,
            "phone":      self.phone,
            "email":      self.email,
            "address":    self.address,
            "created_at": iso_utc(self.created_at),
        }


class Expense(db.Model):
    __tablename__ = 'expenses'

    id           = db.Column(db.Integer,        primary_key=True)
    description  = db.Column(db.String(200),    nullable=False)
    amount       = db.Column(db.Numeric(10, 2), nullable=False)
    category     = db.Column(db.String(80),     nullable=False)
    department   = db.Column(db.String(20),     nullable=False, default='shop')
    expense_date = db.Column(db.DateTime,       nullable=False, default=utc_now)
    recorded_by  = db.Column(db.Integer,        db.ForeignKey('users.id'), nullable=True)
    created_at   = db.Column(db.DateTime,       default=utc_now)

    def to_dict(self):
        return {
            "id":           self.id,
            "description":  self.description,
            "amount":       float(self.amount),
            "category":     self.category,
            "department":   self.department,
            "expense_date": iso_utc(self.expense_date),
            "recorded_by":  self.recorded_by,
            "created_at":   iso_utc(self.created_at),
        }


class MpesaTransaction(db.Model):
    __tablename__ = 'mpesa_transactions'

    id                    = db.Column(db.Integer,        primary_key=True)
    merchant_request_id   = db.Column(db.String(100),    nullable=True)
    checkout_request_id   = db.Column(db.String(100),    nullable=True, index=True)
    result_code           = db.Column(db.Integer,        nullable=True)
    result_desc           = db.Column(db.String(255),    nullable=True)
    amount                = db.Column(db.Numeric(10, 2), nullable=True)
    mpesa_receipt_number  = db.Column(db.String(100),    nullable=True)
    phone_number          = db.Column(db.String(20),     nullable=True)
    transaction_date      = db.Column(db.String(50),     nullable=True)
    created_at            = db.Column(db.DateTime,       default=utc_now)
    sender_first_name     = db.Column(db.String(100),    nullable=True)
    sender_middle_name    = db.Column(db.String(100),    nullable=True)
    sender_last_name      = db.Column(db.String(100),    nullable=True)
    linked_transaction_id = db.Column(db.String(100),    nullable=True, index=True)

    @property
    def sender_full_name(self):
        parts = [self.sender_first_name, self.sender_middle_name, self.sender_last_name]
        full  = " ".join(p for p in parts if p).strip()
        return full if full else (self.phone_number or "Unknown")

    @property
    def is_claimed(self):
        return self.linked_transaction_id is not None

    def to_dict(self):
        return {
            "id":                    self.id,
            "checkout_request_id":   self.checkout_request_id,
            "result_code":           self.result_code,
            "result_desc":           self.result_desc,
            "amount":                float(self.amount) if self.amount is not None else None,
            "mpesa_receipt_number":  self.mpesa_receipt_number,
            "phone_number":          self.phone_number,
            "transaction_date":      self.transaction_date,
            "created_at":            iso_utc(self.created_at),
            "status":                "success" if self.result_code == 0 else "failed",
            "sender_first_name":     self.sender_first_name,
            "sender_middle_name":    self.sender_middle_name,
            "sender_last_name":      self.sender_last_name,
            "sender_full_name":      self.sender_full_name,
            "linked_transaction_id": self.linked_transaction_id,
        }


class DebtPayment(db.Model):
    __tablename__ = 'debt_payments'

    id          = db.Column(db.Integer,        primary_key=True)
    sale_id     = db.Column(db.Integer,        db.ForeignKey('sales.id'), nullable=False)
    amount      = db.Column(db.Numeric(10, 2), nullable=False)
    method      = db.Column(db.String(20))
    paid_at     = db.Column(db.DateTime,       default=utc_now)
    received_by = db.Column(db.Integer,        db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            "id":          self.id,
            "sale_id":     self.sale_id,
            "amount":      float(self.amount),
            "method":      self.method,
            "paid_at":     iso_utc(self.paid_at),
            "received_by": self.received_by,
        }


class CashAdvance(db.Model):
    __tablename__ = 'cash_advances'

    id              = db.Column(db.Integer,        primary_key=True)
    person_name     = db.Column(db.String(100),    nullable=False)
    amount          = db.Column(db.Numeric(10, 2), nullable=False)
    reason          = db.Column(db.String(255),    nullable=True)
    amount_returned = db.Column(db.Numeric(10, 2), default=0)
    status          = db.Column(db.String(20),     default='pending')
    department      = db.Column(db.String(20),     default='shop')
    taken_at        = db.Column(db.DateTime,       default=utc_now)
    returned_at     = db.Column(db.DateTime,       nullable=True)
    recorded_by     = db.Column(db.Integer,        db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        amount          = float(self.amount)
        amount_returned = float(self.amount_returned) if self.amount_returned else 0.0
        return {
            'id':              self.id,
            'person_name':     self.person_name,
            'amount':          amount,
            'reason':          self.reason,
            'amount_returned': amount_returned,
            'amount_owed':     round(amount - amount_returned, 2),
            'status':          self.status,
            'department':      self.department,
            'taken_at':        iso_utc(self.taken_at),
            'returned_at':     iso_utc(self.returned_at),
            'recorded_by':     self.recorded_by,
        }


class StockReturn(db.Model):
    """Customer returns a product — stock goes back up, refund issued."""
    __tablename__ = 'stock_returns'

    id            = db.Column(db.Integer,        primary_key=True)
    sale_id       = db.Column(db.Integer,        db.ForeignKey('sales.id'), nullable=True)
    product_id    = db.Column(db.Integer,        db.ForeignKey('products.id'), nullable=False)
    product_name  = db.Column(db.String(120),    nullable=False)
    quantity      = db.Column(db.Integer,        nullable=False)
    refund_amount = db.Column(db.Numeric(10, 2), nullable=False)
    reason        = db.Column(db.String(255),    nullable=True)
    refund_method = db.Column(db.String(20),     default='cash')
    returned_at   = db.Column(db.DateTime,       default=utc_now)
    recorded_by   = db.Column(db.Integer,        db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            "id":            self.id,
            "sale_id":       self.sale_id,
            "product_id":    self.product_id,
            "product_name":  self.product_name,
            "quantity":      self.quantity,
            "refund_amount": float(self.refund_amount),
            "reason":        self.reason,
            "refund_method": self.refund_method,
            "returned_at":   iso_utc(self.returned_at),
            "recorded_by":   self.recorded_by,
        }


class Restock(db.Model):
    """New stock arriving from supplier — stock goes up."""
    __tablename__ = 'restocks'

    id            = db.Column(db.Integer,        primary_key=True)
    product_id    = db.Column(db.Integer,        db.ForeignKey('products.id'), nullable=False)
    product_name  = db.Column(db.String(120),    nullable=False)
    quantity      = db.Column(db.Integer,        nullable=False)
    cartons       = db.Column(db.Integer,        nullable=True)
    cost_per_unit = db.Column(db.Numeric(10, 2), nullable=False)
    total_cost    = db.Column(db.Numeric(10, 2), nullable=False)
    supplier_id   = db.Column(db.Integer,        db.ForeignKey('suppliers.id'), nullable=True)
    supplier_name = db.Column(db.String(100),    nullable=True)
    notes         = db.Column(db.String(255),    nullable=True)
    restocked_at  = db.Column(db.DateTime,       default=utc_now)
    recorded_by   = db.Column(db.Integer,        db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            "id":            self.id,
            "product_id":    self.product_id,
            "product_name":  self.product_name,
            "quantity":      self.quantity,
            "cartons":       self.cartons,
            "cost_per_unit": float(self.cost_per_unit),
            "total_cost":    float(self.total_cost),
            "supplier_id":   self.supplier_id,
            "supplier_name": self.supplier_name,
            "notes":         self.notes,
            "restocked_at":  iso_utc(self.restocked_at),
            "recorded_by":   self.recorded_by,
        }


class CashReconciliation(db.Model):
    """End of day cash count vs expected."""
    __tablename__ = 'cash_reconciliations'

    id              = db.Column(db.Integer,        primary_key=True)
    reconciled_date = db.Column(db.Date,           nullable=False, unique=True)
    expected_cash   = db.Column(db.Numeric(10, 2), nullable=False)
    actual_cash     = db.Column(db.Numeric(10, 2), nullable=False)
    difference      = db.Column(db.Numeric(10, 2), nullable=False)
    notes           = db.Column(db.String(500),    nullable=True)
    reconciled_at   = db.Column(db.DateTime,       default=utc_now)
    reconciled_by   = db.Column(db.Integer,        db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            "id":              self.id,
            "reconciled_date": self.reconciled_date.isoformat(),
            "expected_cash":   float(self.expected_cash),
            "actual_cash":     float(self.actual_cash),
            "difference":      float(self.difference),
            "notes":           self.notes,
            "reconciled_at":   iso_utc(self.reconciled_at),
            "reconciled_by":   self.reconciled_by,
        }