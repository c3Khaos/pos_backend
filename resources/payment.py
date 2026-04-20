# resources/payment.py
from flask import request, current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Sale, MpesaTransaction, User
from extensions import db
from services.kopokopo import KopoKopoService


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1 — INITIATE STK PUSH
# ─────────────────────────────────────────────────────────────────────────────
class PaymentResource(Resource):
    """POST /payments — initiate STK Push"""

    @jwt_required()
    def post(self):
        data           = request.get_json()
        phone_number   = data.get('phone_number')
        amount         = data.get('amount')
        transaction_id = data.get('transaction_id')

        if not phone_number or not amount or not transaction_id:
            return {"message": "phone_number, amount and transaction_id are required."}, 400

        try:
            amount = float(amount)
            if amount <= 0:
                return {"message": "Amount must be greater than 0."}, 400
        except (TypeError, ValueError):
            return {"message": "Invalid amount format."}, 400

        try:
            result = KopoKopoService.initiate_stk_push(
                phone_number   = phone_number,
                amount         = amount,
                transaction_id = transaction_id,
            )
        except Exception as e:
            current_app.logger.error(f"STK Push error: {e}")
            return {"message": "Failed to initiate payment. Try again."}, 500

        if not result['success']:
            return {"message": result['message']}, 400

        return {
            "message":    "STK Push sent. Waiting for customer to confirm.",
            "payment_id": result['payment_id'],
        }, 200


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2 — PAYMENT CALLBACK
# ─────────────────────────────────────────────────────────────────────────────
class PaymentCallbackResource(Resource):
    """POST /payments/callback — receives result from Kopo Kopo"""

    def post(self):
        # ── STEP 1: VERIFY SIGNATURE ──────────────────────────────────────────
        signature = request.headers.get('X-KopoKopo-Signature', '')
        if not KopoKopoService.verify_webhook(request.get_data(), signature):
            current_app.logger.warning("Invalid Kopo Kopo webhook signature")
            return {"message": "Invalid signature"}, 401

        data       = request.get_json()
        attributes = data.get('data', {}).get('attributes', {})
        status     = attributes.get('status')
        event      = attributes.get('event', {})
        resource   = event.get('resource') or {}
        metadata   = attributes.get('metadata', {})

        kopokopo_id    = data.get('data', {}).get('id')
        transaction_id = metadata.get('transaction_id')
        reference      = resource.get('reference')
        amount         = resource.get('amount')
        phone          = resource.get('sender_phone_number')

        first_name  = resource.get('sender_first_name')
        middle_name = resource.get('sender_middle_name')
        last_name   = resource.get('sender_last_name')

        # ── STEP 2: IDEMPOTENCY CHECK ─────────────────────────────────────────
        if kopokopo_id:
            existing = MpesaTransaction.query.filter_by(
                checkout_request_id=kopokopo_id
            ).first()
            if existing:
                current_app.logger.info(
                    f"Duplicate callback for {kopokopo_id} — already processed"
                )
                return {"message": "Already processed"}, 200

        try:
            # ── STEP 3: LOG THE TRANSACTION ───────────────────────────────────
            mpesa_txn = MpesaTransaction(
                checkout_request_id  = kopokopo_id,
                result_code          = 0 if status == 'Success' else 1,
                result_desc          = status,
                amount               = float(amount) if amount else None,
                mpesa_receipt_number = reference,
                phone_number         = phone,
                sender_first_name    = first_name,
                sender_middle_name   = middle_name,
                sender_last_name     = last_name,
            )
            db.session.add(mpesa_txn)

            # ── STEP 4: UPDATE SALE (with AMOUNT VERIFICATION) ────────────────
            if status == 'Success' and transaction_id:
                sale = Sale.query.filter_by(transaction_id=transaction_id).first()

                if not sale:
                    # 👇 CHANGED — this is EXPECTED, not an error
                    # In M-Pesa flow, callback often arrives before frontend creates sale.
                    # Sale creation happens after frontend polls and sees Success.
                    # The MpesaTransaction record is still logged above for audit.
                    current_app.logger.info(
                        f"Payment confirmed, awaiting sale sync: "
                        f"reference={reference} amount={amount}"
                    )
                else:
                    paid_amount = float(amount) if amount else 0

                    # AMOUNT VERIFICATION — critical safety check
                    if abs(paid_amount - sale.total_amount) > 0.01:
                        current_app.logger.error(
                            f"AMOUNT MISMATCH on sale {sale.id}: "
                            f"expected={sale.total_amount} received={paid_amount}"
                        )
                        sale.payment_status = 'amount_mismatch'
                    else:
                        sale.payment_status = 'paid'
                        sale.amount_paid    = paid_amount

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Callback processing error: {e}")
            return {"message": "Callback received with errors"}, 200

        return {"message": "Callback received"}, 200


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3 — FRONTEND POLLING
# ─────────────────────────────────────────────────────────────────────────────
class CheckPaymentStatusResource(Resource):
    """GET /payments/check/<payment_id> — frontend polls this"""

    @jwt_required()
    def get(self, checkout_payment_id):
        try:
            result = KopoKopoService.check_payment_status(checkout_payment_id)
            return result, 200
        except Exception as e:
            current_app.logger.error(f"Payment status check error: {e}")
            return {"message": "Could not check payment status"}, 500


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 4 — ADMIN M-PESA LOGS
# ─────────────────────────────────────────────────────────────────────────────
class MpesaTransactionListResource(Resource):
    """GET /mpesa-transactions — list all M-Pesa transactions (admin only)"""

    @jwt_required()
    def get(self):
        user_id = get_jwt_identity()
        user    = User.query.get(user_id)
        if not user or user.role != "admin":
            return {"message": "Admin access required."}, 403

        transactions = MpesaTransaction.query.order_by(
            MpesaTransaction.created_at.desc()
        ).all()
        return [t.to_dict() for t in transactions], 200