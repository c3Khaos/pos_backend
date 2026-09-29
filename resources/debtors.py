from decimal import Decimal
from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required
from models import Sale, DebtPayment
from extensions import db
from utils.tenant import get_tenant_id, current_user_and_tenant, is_admin


class DebtorListResource(Resource):
    """GET /debtors — list unpaid/partial sales (admin only)"""

    @jwt_required()
    def get(self):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        status = request.args.get('status')
        query  = Sale.query.filter_by(tenant_id=tenant_id)

        if status and status != 'all':
            query = query.filter(Sale.payment_status == status)
        else:
            query = query.filter(Sale.payment_status.in_(['unpaid', 'partial']))

        debtors = query.order_by(Sale.sale_date.desc()).all()
        return [self._enrich(sale, tenant_id) for sale in debtors], 200

    def _enrich(self, sale, tenant_id):
        data       = sale.to_dict()
        total_paid = sum(
            p.amount for p in DebtPayment.query.filter_by(
                tenant_id=tenant_id, sale_id=sale.id
            )
        )
        data['total_paid']  = float(total_paid)
        data['amount_owed'] = float(sale.total_amount - total_paid)
        return data


class DebtorDetailResource(Resource):
    """GET /debtors/<sale_id> — one debt with full payment history"""

    @jwt_required()
    def get(self, sale_id):
        tenant_id = get_tenant_id()
        if not is_admin():
            return {"message": "Admin access required."}, 403

        # ── SECURITY: scope the sale lookup to tenant (IDOR guard) ────────
        sale = Sale.query.filter_by(id=sale_id, tenant_id=tenant_id).first()
        if not sale:
            return {"message": "Sale not found."}, 404

        payments = DebtPayment.query.filter_by(
            tenant_id=tenant_id, sale_id=sale_id
        ).order_by(DebtPayment.paid_at.desc()).all()
        total_paid  = sum(p.amount for p in payments)
        amount_owed = sale.total_amount - total_paid

        return {
            'sale':        sale.to_dict(),
            'payments':    [p.to_dict() for p in payments],
            'total_paid':  float(total_paid),
            'amount_owed': float(amount_owed),
        }, 200


class DebtorPaymentResource(Resource):
    """POST /debtors/<sale_id>/pay — record a payment"""

    @jwt_required()
    def post(self, sale_id):
        user, tenant_id = current_user_and_tenant()
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        # ── SECURITY: sale must belong to this tenant ─────────────────────
        sale = Sale.query.filter_by(id=sale_id, tenant_id=tenant_id).first()
        if not sale:
            return {"message": "Sale not found."}, 404

        data   = request.get_json() or {}
        amount = data.get('amount')
        method = data.get('method', 'cash')

        if amount is None:
            return {"message": "Amount is required."}, 400

        try:
            amount = Decimal(str(amount))
        except (TypeError, ValueError):
            return {"message": "Invalid amount format."}, 400

        if amount <= 0:
            return {"message": "Amount must be greater than 0."}, 400

        if sale.payment_status == 'paid':
            return {"message": "This debt is already fully paid."}, 400

        total_paid_before = sum(
            p.amount for p in DebtPayment.query.filter_by(
                tenant_id=tenant_id, sale_id=sale.id
            )
        )
        amount_owed = sale.total_amount - total_paid_before

        if amount > amount_owed:
            return {"message": f"Payment exceeds amount owed (KSh {amount_owed:.2f})."}, 400

        try:
            payment = DebtPayment(
                tenant_id   = tenant_id,
                sale_id     = sale.id,
                amount      = amount,
                method      = method,
                received_by = user.id,
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
                "total_paid":  float(total_paid_after),
                "amount_owed": float(sale.total_amount - total_paid_after),
            }, 201

        except Exception as e:
            db.session.rollback()
            return {"message": "An error occurred while recording the payment."}, 500