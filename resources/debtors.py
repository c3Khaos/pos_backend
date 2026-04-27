from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Sale, SaleItem, Product, DebtPayment, User
from extensions import db

HARDWARE_CATEGORY = 'Hardware & Utilities'


def hardware_sale_ids():
    """Returns list of sale IDs that contain hardware products."""
    rows = db.session.query(SaleItem.sale_id).join(
        Product, SaleItem.product_id == Product.id
    ).filter(
        Product.category == HARDWARE_CATEGORY
    ).distinct().all()
    return [row[0] for row in rows]


class DebtorListResource(Resource):
    """GET /debtors?department=shop|hardware — list unpaid/partial sales (admin only)"""

    @jwt_required()
    def get(self):
        user_id = get_jwt_identity()
        user    = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        status     = request.args.get('status')
        department = request.args.get('department', 'shop')  # default to shop

        hw_ids = hardware_sale_ids()

        # ── Filter by department ──────────────────────────────────────────
        if department == 'hardware':
            # Hardware debtors ONLY — sales that contain hardware products
            if hw_ids:
                base = Sale.query.filter(Sale.id.in_(hw_ids))
            else:
                # No hardware sales exist yet — return empty
                base = Sale.query.filter(False)
        else:
            # Shop debtors — EXCLUDE hardware sales
            if hw_ids:
                base = Sale.query.filter(~Sale.id.in_(hw_ids))
            else:
                base = Sale.query

        # ── Filter by payment status ──────────────────────────────────────
        if status and status != 'all':
            query = base.filter(Sale.payment_status == status)
        else:
            query = base.filter(Sale.payment_status.in_(['unpaid', 'partial']))

        debtors = query.order_by(Sale.sale_date.desc()).all()
        return [self._enrich(sale) for sale in debtors], 200

    def _enrich(self, sale):
        """Add calculated debt fields to the sale dict."""
        data       = sale.to_dict()
        total_paid = sum(
            p.amount for p in DebtPayment.query.filter_by(sale_id=sale.id)
        )
        data['total_paid']  = total_paid
        data['amount_owed'] = sale.total_amount - total_paid
        return data


class DebtorDetailResource(Resource):
    """GET /debtors/<sale_id> — one debt with full payment history (admin only)"""

    @jwt_required()
    def get(self, sale_id):
        user_id = get_jwt_identity()
        user    = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        sale     = Sale.query.get_or_404(sale_id)
        payments = DebtPayment.query.filter_by(sale_id=sale_id)\
                              .order_by(DebtPayment.paid_at.desc()).all()

        total_paid  = sum(p.amount for p in payments)
        amount_owed = sale.total_amount - total_paid

        return {
            'sale':        sale.to_dict(),
            'payments':    [p.to_dict() for p in payments],
            'total_paid':  total_paid,
            'amount_owed': amount_owed,
        }, 200


class DebtorPaymentResource(Resource):
    """POST /debtors/<sale_id>/pay — record a payment (admin only)"""

    @jwt_required()
    def post(self, sale_id):
        user_id = get_jwt_identity()
        user    = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        sale = Sale.query.get_or_404(sale_id)
        data = request.get_json()

        amount = data.get('amount')
        method = data.get('method', 'cash')

        if amount is None:
            return {"message": "Amount is required."}, 400

        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"message": "Invalid amount format."}, 400

        if amount <= 0:
            return {"message": "Amount must be greater than 0."}, 400

        if sale.payment_status == 'paid':
            return {"message": "This debt is already fully paid."}, 400

        total_paid_before = sum(
            p.amount for p in DebtPayment.query.filter_by(sale_id=sale.id)
        )
        amount_owed = sale.total_amount - total_paid_before

        if amount > amount_owed:
            return {"message": f"Payment exceeds amount owed (KSh {amount_owed:.2f})."}, 400

        try:
            payment = DebtPayment(
                sale_id     = sale.id,
                amount      = amount,
                method      = method,
                received_by = user_id,
            )
            db.session.add(payment)

            total_paid_after    = total_paid_before + amount
            sale.amount_paid    = total_paid_after
            sale.payment_status = 'paid' if total_paid_after >= sale.total_amount else 'partial'

            db.session.commit()

            return {
                "message":     "Payment recorded successfully.",
                "payment":     payment.to_dict(),
                "new_status":  sale.payment_status,
                "total_paid":  total_paid_after,
                "amount_owed": sale.total_amount - total_paid_after,
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": "An error occurred while recording the payment."}, 500