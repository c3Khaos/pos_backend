# resources/payment.py
from decimal import Decimal
from flask import request, current_app
from flask_restful import Resource
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Sale, MpesaTransaction, User
from extensions import db
from services.kopokopo import KopoKopoService


def _expected_mpesa_amount(sale):
    """
    Returns the amount we expect M-Pesa to confirm for this sale.

    - Split payment (cash + mpesa): compare against mpesa_amount only
    - Pure M-Pesa:                  compare against total_amount
    - Fallback:                     compare against total_amount

    This is the fix for the AMOUNT MISMATCH bug on split payments.
    Previously the callback always compared paid_amount against
    total_amount, so a KSh 5 M-Pesa payment on a KSh 350 sale
    (with KSh 345 cash) always triggered 'amount_mismatch'.
    """
    if sale.mpesa_amount is not None:
        return sale.mpesa_amount
    return sale.total_amount


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
            amount = Decimal(str(amount))
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
            current_app.logger.error(f"STK push error: {e}")
            return {"message": "Failed to initiate payment. Try again."}, 500

        if not result['success']:
            return {"message": result['message']}, 400

        return {
            "message":    "STK Push sent. Waiting for customer to confirm.",
            "payment_id": result['payment_id'],
        }, 200


class PaymentCallbackResource(Resource):
    """POST /payments/callback — receives STK push results from Kopo Kopo"""
    def post(self):
        signature = request.headers.get('X-KopoKopo-Signature', '')
        if not KopoKopoService.verify_webhook(request.get_data(), signature):
            current_app.logger.warning("Invalid Kopo Kopo webhook signature")
            return {"message": "Invalid signature"}, 401

        data       = request.get_json()
        current_app.logger.info(f"STK CALLBACK PAYLOAD: {data}")

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
        first_name     = resource.get('sender_first_name')
        middle_name    = resource.get('sender_middle_name')
        last_name      = resource.get('sender_last_name')

        if kopokopo_id:
            existing = MpesaTransaction.query.filter_by(
                checkout_request_id=kopokopo_id
            ).first()
            if existing:
                current_app.logger.info("Duplicate callback — already processed")
                return {"message": "Already processed"}, 200

        try:
            mpesa_txn = MpesaTransaction(
                checkout_request_id  = kopokopo_id,
                result_code          = 0 if status == 'Success' else 1,
                result_desc          = status,
                amount               = Decimal(str(amount)) if amount else None,
                mpesa_receipt_number = reference,
                phone_number         = phone,
                sender_first_name    = first_name,
                sender_middle_name   = middle_name,
                sender_last_name     = last_name,
            )
            db.session.add(mpesa_txn)

            if status == 'Success' and transaction_id:
                sale = Sale.query.filter_by(transaction_id=transaction_id).first()
                if sale:
                    paid_amount = Decimal(str(amount)) if amount else Decimal('0')
                    # ── FIX: compare against mpesa_amount for split payments ──
                    expected = _expected_mpesa_amount(sale)
                    if abs(paid_amount - expected) > Decimal('0.01'):
                        current_app.logger.error(
                            f"AMOUNT MISMATCH: expected={expected} "
                            f"got={paid_amount} "
                            f"(total={sale.total_amount}, "
                            f"cash={sale.cash_amount}, "
                            f"mpesa={sale.mpesa_amount})"
                        )
                        sale.payment_status = 'amount_mismatch'
                    else:
                        sale.payment_status = 'paid'
                        sale.amount_paid    = paid_amount
                else:
                    current_app.logger.info(
                        f"Payment confirmed, awaiting sale sync: "
                        f"reference={reference} amount={amount}"
                    )

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Callback processing error: {e}")
            return {"message": "Callback received with errors"}, 200

        return {"message": "Callback received"}, 200


class MpesaWebhookResource(Resource):
    """
    POST /payments/webhook — unified endpoint for ALL Kopo Kopo webhook events
    Handles buygoods_transaction_received AND incoming_payment results
    """
    def post(self):
        signature = request.headers.get('X-KopoKopo-Signature', '')
        if not KopoKopoService.verify_webhook(request.get_data(), signature):
            current_app.logger.warning("Invalid webhook signature")
            return {"message": "Invalid signature"}, 401

        data = request.get_json()
        current_app.logger.info(f"WEBHOOK RECEIVED: {data}")

        if 'topic' in data:
            return self._handle_buygoods(data)
        elif data.get('data', {}).get('type') == 'incoming_payment':
            return self._handle_stk_result(data)
        else:
            current_app.logger.warning("Unknown webhook format received")
            return {"message": "Unknown webhook type"}, 200

    def _handle_buygoods(self, data):
        """Handles till payments — manually initiated by customer"""
        topic      = data.get('topic')
        event      = data.get('event', {})
        resource   = event.get('resource') or {}
        webhook_id = data.get('id')

        if topic == 'buygoods_transaction_reversed':
            current_app.logger.info(f"Transaction reversed: {resource.get('reference')}")
            return {"message": "Reversal noted"}, 200

        if webhook_id:
            existing = MpesaTransaction.query.filter_by(
                checkout_request_id=webhook_id
            ).first()
            if existing:
                return {"message": "Already processed"}, 200

        try:
            mpesa_txn = MpesaTransaction(
                checkout_request_id  = webhook_id,
                result_code          = 0,
                result_desc          = resource.get('status', 'Received'),
                amount               = Decimal(str(resource.get('amount', '0'))),
                mpesa_receipt_number = resource.get('reference'),
                phone_number         = resource.get('sender_phone_number'),
                sender_first_name    = resource.get('sender_first_name'),
                sender_middle_name   = resource.get('sender_middle_name'),
                sender_last_name     = resource.get('sender_last_name'),
            )
            db.session.add(mpesa_txn)
            db.session.commit()
            current_app.logger.info(
                f"Till payment logged: {resource.get('reference')} "
                f"KSh {resource.get('amount')} from {resource.get('sender_phone_number')}"
            )
            return {"message": "Till transaction logged"}, 200
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Buygoods webhook error: {e}")
            return {"message": "Error logged"}, 200

    def _handle_stk_result(self, data):
        """Handles callbacks from STK push we initiated"""
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
        first_name     = resource.get('sender_first_name')
        middle_name    = resource.get('sender_middle_name')
        last_name      = resource.get('sender_last_name')

        if kopokopo_id:
            existing = MpesaTransaction.query.filter_by(
                checkout_request_id=kopokopo_id
            ).first()
            if existing:
                return {"message": "Already processed"}, 200

        try:
            paid_amount = Decimal(str(amount)) if amount else None
            mpesa_txn = MpesaTransaction(
                checkout_request_id  = kopokopo_id,
                result_code          = 0 if status == 'Success' else 1,
                result_desc          = status,
                amount               = paid_amount,
                mpesa_receipt_number = reference,
                phone_number         = phone,
                sender_first_name    = first_name,
                sender_middle_name   = middle_name,
                sender_last_name     = last_name,
            )
            db.session.add(mpesa_txn)

            if status == 'Success' and transaction_id:
                sale = Sale.query.filter_by(transaction_id=transaction_id).first()
                if sale:
                    # ── FIX: compare against mpesa_amount for split payments ──
                    expected = _expected_mpesa_amount(sale)
                    if paid_amount is not None and abs(paid_amount - expected) > Decimal('0.01'):
                        current_app.logger.error(
                            f"AMOUNT MISMATCH: expected={expected} "
                            f"got={paid_amount} "
                            f"(total={sale.total_amount}, "
                            f"cash={sale.cash_amount}, "
                            f"mpesa={sale.mpesa_amount})"
                        )
                        sale.payment_status = 'amount_mismatch'
                    else:
                        sale.payment_status = 'paid'
                        sale.amount_paid    = paid_amount
                else:
                    current_app.logger.info(
                        f"Payment confirmed, awaiting sale sync: "
                        f"reference={reference} amount={amount}"
                    )

            db.session.commit()
            return {"message": "STK result processed"}, 200
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"STK result error: {e}")
            return {"message": "Error logged"}, 200


class CheckPaymentStatusResource(Resource):
    """GET /payments/check/<payment_id> — frontend polls STK status"""
    @jwt_required()
    def get(self, payment_id):
        try:
            result = KopoKopoService.check_payment_status(payment_id)
            return result, 200
        except Exception as e:
            current_app.logger.error(f"Payment status check error: {e}")
            return {"message": "Could not check payment status"}, 500


class MpesaTransactionListResource(Resource):
    """
    GET /mpesa-transactions
    Admin: full log. Cashier: last 50 only.
    """
    @jwt_required()
    def get(self):
        user_id = int(get_jwt_identity())
        user    = User.query.get(user_id)

        query = MpesaTransaction.query.order_by(
            MpesaTransaction.created_at.desc()
        )

        if user and user.role == "admin":
            transactions = query.all()
        else:
            transactions = query.limit(50).all()

        return [t.to_dict() for t in transactions], 200