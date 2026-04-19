# resources/debtors.py
from flask import request
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Sale, DebtPayment
from extensions import db


class DebtorListResource(Resource):
    """GET /debtors — list all sales that are unpaid or partially paid"""

    @jwt_required()
    def get(self):
        status = request.args.get('status')  # optional filter: unpaid, partial, paid

        if status:
            query = Sale.query.filter(Sale.payment_status == status)
        else:
            # default: only show debts (unpaid or partial)
            query = Sale.query.filter(Sale.payment_status.in_(['unpaid', 'partial']))

        debtors = query.order_by(Sale.sale_date.desc()).all()
        return [self._enrich(sale) for sale in debtors], 200

    def _enrich(self, sale):
        """Add calculated debt fields to the sale dict"""
        data = sale.to_dict()
        total_paid = sum(p.amount for p in DebtPayment.query.filter_by(sale_id=sale.id))
        data['total_paid']  = total_paid
        data['amount_owed'] = sale.total_amount - total_paid
        return data


class DebtorDetailResource(Resource):
    """GET /debtors/<sale_id> — get one debt with full payment history"""

    @jwt_required()
    def get(self, sale_id):
        sale     = Sale.query.get_or_404(sale_id)
        payments = DebtPayment.query.filter_by(sale_id=sale_id).order_by(DebtPayment.paid_at.desc()).all()

        total_paid  = sum(p.amount for p in payments)
        amount_owed = sale.total_amount - total_paid

        return {
            'sale':        sale.to_dict(),
            'payments':    [p.to_dict() for p in payments],
            'total_paid':  total_paid,
            'amount_owed': amount_owed,
        }, 200


class DebtorPaymentResource(Resource):
    """POST /debtors/<sale_id>/pay — record a payment on a debt"""

    @jwt_required()
    def post(self, sale_id):
        sale    = Sale.query.get_or_404(sale_id)
        data    = request.get_json()
        user_id = get_jwt_identity()

        amount = data.get('amount')
        method = data.get('method', 'cash')

        # --- validation ---
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

        # --- calculate current debt ---
        total_paid_before = sum(p.amount for p in DebtPayment.query.filter_by(sale_id=sale.id))
        amount_owed       = sale.total_amount - total_paid_before

        if amount > amount_owed:
            return {"message": f"Payment exceeds amount owed (KSh {amount_owed:.2f})."}, 400

        try:
            # --- record payment ---
            payment = DebtPayment(
                sale_id     = sale.id,
                amount      = amount,
                method      = method,
                received_by = user_id,
            )
            db.session.add(payment)

            # --- update sale status ---
            total_paid_after = total_paid_before + amount
            sale.amount_paid = total_paid_after

            if total_paid_after >= sale.total_amount:
                sale.payment_status = 'paid'
            else:
                sale.payment_status = 'partial'

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
            print(f"Error recording debt payment: {e}")
            return {"message": "An error occurred while recording the payment."}, 500