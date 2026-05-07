from flask import request
from flask_restful import Resource
from models import Sale, SaleItem, Product, User, SaleAuditLog
from extensions import db
from datetime import datetime, timezone, timedelta
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError

HARDWARE_CATEGORY      = 'Hardware & Utilities'
BACKDATE_WINDOW        = timedelta(hours=48)
ALLOWED_BACKDATE_ROLES = {'admin', 'manager', 'owner'}


def get_hardware_sale_ids():
    """Returns list of sale IDs that contain hardware products."""
    rows = db.session.query(SaleItem.sale_id).join(
        Product, SaleItem.product_id == Product.id
    ).filter(
        Product.category == HARDWARE_CATEGORY
    ).distinct().all()
    return [row[0] for row in rows]


def _current_user():
    """Return the User row for the JWT identity, or None."""
    identity = get_jwt_identity()
    if identity is None:
        return None
    try:
        return db.session.get(User, int(identity))
    except (TypeError, ValueError):
        return None


def _build_sale(*, data, user, sale_date,
                is_backdated=False, backdate_reason=None,
                backdate_reference=None, approved_by_id=None):
    """
    Shared sale-construction logic. Returns (Sale, http_status).
    Raises ValueError on validation failure. Caller commits and audit-logs.
    """
    transaction_id = data.get('transaction_id')
    items_data     = data.get('items')
    total_amount   = data.get('total_amount')
    amount_paid    = data.get('amount_paid')
    payment_method = data.get('payment_method', 'cash')
    customer_name  = data.get('customer_name')
    customer_phone = data.get('customer_phone')

    if not transaction_id:
        raise ValueError("Missing transaction_id")
    if not items_data or not isinstance(items_data, list) or total_amount is None:
        raise ValueError("Invalid sale data. Missing items or amounts.")

    if payment_method == 'credit':
        if not customer_name or not customer_phone:
            raise ValueError("Customer name and phone are required for credit sales.")
        payment_status = 'unpaid'
        amount_paid    = 0
        change_given   = 0
    else:
        if amount_paid is None:
            raise ValueError("Amount paid is required.")
        change_given   = amount_paid - total_amount
        payment_status = 'paid'
        if change_given < 0:
            raise ValueError("Amount paid is insufficient.")

    # Idempotency — a retried request with same transaction_id returns existing sale.
    existing = Sale.query.filter_by(transaction_id=transaction_id).first()
    if existing:
        return existing, 200

    validated_items = []
    for item_data in items_data:
        product_id          = item_data.get('product_id')
        product_name        = item_data.get('name')
        quantity            = item_data.get('quantity')
        price_from_frontend = item_data.get('price')

        if not product_id or not product_name or not quantity or price_from_frontend is None:
            raise ValueError("Invalid item data within sale.")

        # Lock the product row to prevent concurrent oversells of the last unit.
        product = (
            db.session.query(Product)
            .filter_by(id=product_id)
            .with_for_update()
            .first()
        )
        if not product:
            raise ValueError(f"Product {product_id} not found")
        if product.stock < quantity:
            raise ValueError(f"Not enough stock for {product.name}. Available: {product.stock}")

        validated_items.append({
            "product":  product,
            "quantity": quantity,
            "price":    price_from_frontend,
            "profit":   (price_from_frontend - product.unit_price) * quantity,
        })

    new_sale = Sale(
        transaction_id     = transaction_id,
        total_amount       = total_amount,
        amount_paid        = amount_paid,
        change_given       = change_given,
        payment_method     = payment_method,
        sale_date          = sale_date,
        user_id            = user.id,
        entered_by_id      = user.id,
        approved_by_id     = approved_by_id,
        is_backdated       = is_backdated,
        backdate_reason    = backdate_reason,
        backdate_reference = backdate_reference,
        customer_name      = customer_name,
        customer_phone     = customer_phone,
        payment_status     = payment_status,
    )

    db.session.add(new_sale)
    db.session.flush()

    for item in validated_items:
        product  = item["product"]
        quantity = item["quantity"]
        product.stock -= quantity

        db.session.add(SaleItem(
            sale_id    = new_sale.id,
            product_id = product.id,
            name       = product.name,
            quantity   = quantity,
            price      = item["price"],
            profit     = item["profit"],
        ))

    return new_sale, 201


class SaleListResource(Resource):

    @jwt_required()
    def get(self):
        current_user_id = int(get_jwt_identity())
        hw_ids = get_hardware_sale_ids()

        query = Sale.query.filter_by(user_id=current_user_id)
        if hw_ids:
            query = query.filter(~Sale.id.in_(hw_ids))

        sales = query.order_by(Sale.sale_date.desc()).all()
        return [sale.to_dict() for sale in sales], 200

    @jwt_required()
    def post(self):
        user = _current_user()
        if not user:
            return {"error": "Unauthorized. Please log in."}, 401

        data = request.get_json() or {}

        # SECURITY: sale_date is ALWAYS server-set on this endpoint. Any
        # sale_date the client sends is silently ignored. Backdating goes
        # through /sales/backdated, which has role checks and audit.
        sale_date = datetime.now(timezone.utc)

        try:
            sale, status = _build_sale(
                data=data, user=user, sale_date=sale_date, is_backdated=False,
            )
            db.session.commit()
            return sale.to_dict(), status

        except IntegrityError:
            db.session.rollback()
            existing = Sale.query.filter_by(transaction_id=data.get('transaction_id')).first()
            if existing:
                return existing.to_dict(), 200
            return {"message": "Database integrity error"}, 500

        except ValueError as e:
            db.session.rollback()
            return {"message": str(e)}, 400

        except Exception:
            db.session.rollback()
            return {"message": "An unexpected error occurred during sale processing."}, 500


class BackdatedSaleResource(Resource):
    """
    Manager/admin/owner only. Records a sale that actually happened in the past
    (paper receipt, machine outage, etc.). Heavily audited.
    """

    @jwt_required()
    def post(self):
        user = _current_user()
        if not user:
            return {"error": "Unauthorized."}, 401

        if user.role not in ALLOWED_BACKDATE_ROLES:
            # Audit the rejected attempt — useful signal if a cashier is probing.
            db.session.add(SaleAuditLog(
                action       = 'backdate_denied_role',
                performed_by = user.id,
                ip_address   = request.headers.get('X-Forwarded-For', request.remote_addr),
                details      = {"role": user.role},
            ))
            db.session.commit()
            return {"message": "Forbidden. Backdating requires manager or admin role."}, 403

        data = request.get_json() or {}

        sale_date_str      = data.get('sale_date')
        backdate_reason    = (data.get('backdate_reason') or '').strip()
        backdate_reference = (data.get('backdate_reference') or '').strip()

        # Hard-required fields — these are the audit trail.
        if not sale_date_str:
            return {"message": "sale_date is required for backdated sales."}, 400
        if len(backdate_reason) < 5:
            return {"message": "A reason of at least 5 characters is required."}, 400
        if not backdate_reference:
            return {"message": "A reference (paper receipt #, photo URL, etc.) is required."}, 400

        try:
            sale_date = datetime.fromisoformat(sale_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return {"message": "Invalid sale_date format. Use ISO 8601."}, 400

        if sale_date.tzinfo is None:
            sale_date = sale_date.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)

        # No future sales. 5-min skew tolerance for client clocks.
        if sale_date > now + timedelta(minutes=5):
            return {"message": "Backdated sales cannot be in the future."}, 400

        # Hard window — beyond this, you do it on paper and reconcile manually.
        if now - sale_date > BACKDATE_WINDOW:
            hours = int(BACKDATE_WINDOW.total_seconds() // 3600)
            return {"message": f"Backdating is only permitted within the last {hours} hours."}, 400

        try:
            sale, status = _build_sale(
                data               = data,
                user               = user,
                sale_date          = sale_date,
                is_backdated       = True,
                backdate_reason    = backdate_reason,
                backdate_reference = backdate_reference,
                approved_by_id     = user.id,  # for now, entering manager == approver
            )

            # Only audit on a NEW sale, not idempotent replays.
            if status == 201:
                db.session.add(SaleAuditLog(
                    sale_id      = sale.id,
                    action       = 'backdated_sale_created',
                    performed_by = user.id,
                    ip_address   = request.headers.get('X-Forwarded-For', request.remote_addr),
                    details      = {
                        "claimed_sale_date": sale_date.isoformat(),
                        "actual_entry_time": now.isoformat(),
                        "reason":            backdate_reason,
                        "reference":         backdate_reference,
                        "transaction_id":    data.get('transaction_id'),
                        "total_amount":      data.get('total_amount'),
                        "item_count":        len(data.get('items') or []),
                    },
                ))

            db.session.commit()
            return sale.to_dict(), status

        except IntegrityError:
            db.session.rollback()
            existing = Sale.query.filter_by(transaction_id=data.get('transaction_id')).first()
            if existing:
                return existing.to_dict(), 200
            return {"message": "Database integrity error"}, 500

        except ValueError as e:
            db.session.rollback()
            return {"message": str(e)}, 400

        except Exception:
            db.session.rollback()
            return {"message": "An unexpected error occurred during sale processing."}, 500