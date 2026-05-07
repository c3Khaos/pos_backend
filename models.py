from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone


class User(db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role          = db.Column(db.String(50), default='user', nullable=False)
    active        = db.Column(db.Boolean, default=True, nullable=False)

    # Sale has 3 FKs to users now (seller, entered_by, approved_by) — disambiguate.
    sales = db.relationship("Sale", back_populates="seller", foreign_keys="Sale.user_id")

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

    id             = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    total_amount   = db.Column(db.Float, nullable=False)
    amount_paid    = db.Column(db.Float, nullable=False)
    change_given   = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)

    # When the sale supposedly happened. Server-set for normal sales,
    # client-supplied (with audit) for backdated sales.
    sale_date      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # When the row was actually inserted. Server-set, NEVER client-controllable.
    # For normal sales: created_at ≈ sale_date. For backdated sales: created_at > sale_date.
    # This is the column auditors and KRA care about.
    created_at     = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    # Backdating metadata. is_backdated=True means sale_date is historical.
    is_backdated       = db.Column(db.Boolean, nullable=False, default=False,
                                   server_default=db.text('false'))
    backdate_reason    = db.Column(db.String(255), nullable=True)
    backdate_reference = db.Column(db.String(100), nullable=True)

    # Who keyed in the row (== seller for normal sales, may differ for backdated).
    entered_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # Who authorised the backdate. NULL for normal sales.
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    user_id        = db.Column(db.Integer, db.ForeignKey('users.id'))
    customer_name  = db.Column(db.String(100), nullable=True)
    customer_phone = db.Column(db.String(20),  nullable=True)
    payment_status = db.Column(db.String(20),  default='paid')

    # Relationships — foreign_keys is required because we have multiple FKs to users.
    seller      = db.relationship("User", back_populates="sales", foreign_keys=[user_id])
    entered_by  = db.relationship("User", foreign_keys=[entered_by_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    items       = db.relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")

    def to_dict(self):
        change = self.amount_paid - self.total_amount
        return {
            "id":                 self.id,
            "sale_number":        f"SALE-{self.id}",
            "total_amount":       self.total_amount,
            "amount_paid":        self.amount_paid,
            "change":             change,
            "payment_method":     self.payment_method,
            "sale_date":          self.sale_date.isoformat() + "Z",
            "created_at":         self.created_at.isoformat() + "Z" if self.created_at else None,
            "is_backdated":       self.is_backdated,
            "backdate_reason":    self.backdate_reason,
            "backdate_reference": self.backdate_reference,
            "entered_by":         self.entered_by.username  if self.entered_by  else None,
            "approved_by":        self.approved_by.username if self.approved_by else None,
            "user":               self.seller.username if self.seller else None,
            "customer_name":      self.customer_name,
            "customer_phone":     self.customer_phone,
            "payment_status":     self.payment_status,
            "items":              [item.to_dict() for item in self.items],
        }


class SaleItem(db.Model):
    __tablename__ = "sale_items"

    id         = db.Column(db.Integer, primary_key=True)
    sale_id    = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, nullable=False)
    name       = db.Column(db.String(120), nullable=False)
    quantity   = db.Column(db.Float, nullable=False)
    price      = db.Column(db.Float, nullable=False)
    profit     = db.Column(db.Float, nullable=False)

    sale = db.relationship("Sale", back_populates="items")

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "name":       self.name,
            "quantity":   self.quantity,
            "price":      self.price,
            "profit":     self.profit,
        }


class Product(db.Model):
    __tablename__ = "products"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(80), nullable=False)
    category   = db.Column(db.String(80), nullable=False)
    price      = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    stock      = db.Column(db.Float, nullable=False)
    barcode    = db.Column(db.String, nullable=True, unique=True, index=True)
    sold_loose = db.Column(db.Boolean, default=False, nullable=False)

    def to_dict(self):
        return {
            "id":         self.id,
            "name":       self.name,
            "category":   self.category,
            "price":      self.price,
            "unit_price": self.unit_price,
            "stock":      self.stock,
            "barcode":    self.barcode,
            "sold_loose": self.sold_loose,
        }


class Supplier(db.Model):
    __tablename__ = 'suppliers'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    phone      = db.Column(db.String(20), nullable=False)
    email      = db.Column(db.String(120), nullable=True)
    address    = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":         self.id,
            "name":       self.name,
            "phone":      self.phone,
            "email":      self.email,
            "address":    self.address,
            "created_at": self.created_at.isoformat() + "Z",
        }


class Expense(db.Model):
    __tablename__ = 'expenses'

    id           = db.Column(db.Integer,     primary_key=True)
    description  = db.Column(db.String(200), nullable=False)
    amount       = db.Column(db.Float,       nullable=False)
    category     = db.Column(db.String(80),  nullable=False)
    department   = db.Column(db.String(20),  nullable=False, default='shop')
    expense_date = db.Column(db.DateTime,    nullable=False, default=datetime.utcnow)
    recorded_by  = db.Column(db.Integer,     db.ForeignKey('users.id'), nullable=True)
    created_at   = db.Column(db.DateTime,    default=datetime.utcnow)

    def to_dict(self):
        return {
            "id":           self.id,
            "description":  self.description,
            "amount":       self.amount,
            "category":     self.category,
            "department":   self.department,
            "expense_date": self.expense_date.isoformat() + "Z",
            "recorded_by":  self.recorded_by,
            "created_at":   self.created_at.isoformat() + "Z",
        }


class MpesaTransaction(db.Model):
    __tablename__ = 'mpesa_transactions'

    id                    = db.Column(db.Integer, primary_key=True)
    merchant_request_id   = db.Column(db.String(100), nullable=True)
    checkout_request_id   = db.Column(db.String(100), nullable=True, index=True)
    result_code           = db.Column(db.Integer, nullable=True)
    result_desc           = db.Column(db.String(255), nullable=True)
    amount                = db.Column(db.Float, nullable=True)
    mpesa_receipt_number  = db.Column(db.String(100), nullable=True)
    phone_number          = db.Column(db.String(20), nullable=True)
    transaction_date      = db.Column(db.String(50), nullable=True)
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)
    sender_first_name     = db.Column(db.String(100), nullable=True)
    sender_middle_name    = db.Column(db.String(100), nullable=True)
    sender_last_name      = db.Column(db.String(100), nullable=True)
    linked_transaction_id = db.Column(db.String(100), nullable=True, index=True)

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
            "amount":                self.amount,
            "mpesa_receipt_number":  self.mpesa_receipt_number,
            "phone_number":          self.phone_number,
            "transaction_date":      self.transaction_date,
            "created_at":            self.created_at.isoformat(),
            "status":                "success" if self.result_code == 0 else "failed",
            "sender_first_name":     self.sender_first_name,
            "sender_middle_name":    self.sender_middle_name,
            "sender_last_name":      self.sender_last_name,
            "sender_full_name":      self.sender_full_name,
            "linked_transaction_id": self.linked_transaction_id,
        }


class DebtPayment(db.Model):
    __tablename__ = 'debt_payments'

    id          = db.Column(db.Integer, primary_key=True)
    sale_id     = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    method      = db.Column(db.String(20))
    paid_at     = db.Column(db.DateTime, default=db.func.now())
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            "id":          self.id,
            "sale_id":     self.sale_id,
            "amount":      self.amount,
            "method":      self.method,
            "paid_at":     self.paid_at.isoformat() + "Z" if self.paid_at else None,
            "received_by": self.received_by,
        }


class CashAdvance(db.Model):
    __tablename__ = 'cash_advances'

    id              = db.Column(db.Integer,     primary_key=True)
    person_name     = db.Column(db.String(100), nullable=False)
    amount          = db.Column(db.Float,       nullable=False)
    reason          = db.Column(db.String(255), nullable=True)
    amount_returned = db.Column(db.Float,       default=0)
    status          = db.Column(db.String(20),  default='pending')
    department      = db.Column(db.String(20),  default='shop')
    taken_at        = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))
    returned_at     = db.Column(db.DateTime,    nullable=True)
    recorded_by     = db.Column(db.Integer,     db.ForeignKey('users.id'), nullable=True)

    def to_dict(self):
        return {
            'id':              self.id,
            'person_name':     self.person_name,
            'amount':          self.amount,
            'reason':          self.reason,
            'amount_returned': self.amount_returned or 0,
            'amount_owed':     self.amount - (self.amount_returned or 0),
            'status':          self.status,
            'department':      self.department,
            'taken_at':        self.taken_at.isoformat()    if self.taken_at    else None,
            'returned_at':     self.returned_at.isoformat() if self.returned_at else None,
            'recorded_by':     self.recorded_by,
        }


class SaleAuditLog(db.Model):
    """
    Append-only audit trail for sensitive sale operations. Cashiers should NOT
    have read access to this table at the API layer — only owners/managers.
    """
    __tablename__ = 'sale_audit_log'

    id           = db.Column(db.Integer, primary_key=True)
    sale_id      = db.Column(db.Integer, db.ForeignKey('sales.id', ondelete='SET NULL'), nullable=True)
    action       = db.Column(db.String(50),  nullable=False)
    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    performed_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    details      = db.Column(db.JSON, nullable=True)
    ip_address   = db.Column(db.String(45), nullable=True)  # IPv6 max

    def to_dict(self):
        return {
            "id":           self.id,
            "sale_id":      self.sale_id,
            "action":       self.action,
            "performed_by": self.performed_by,
            "performed_at": self.performed_at.isoformat() + "Z" if self.performed_at else None,
            "details":      self.details,
            "ip_address":   self.ip_address,
        }