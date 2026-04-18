from flask import request
from flask_restful import Resource
from mpesa import Mpesa
from models import MpesaTransaction
from extensions import db
from flask_jwt_extended import jwt_required


class PaymentResource(Resource):
    def post(self):
        mpesa_instance = Mpesa()
        data = request.get_json(silent=True) or {}
        payload = {
            "phone": data.get("phone", "254716310186"),
            "amount": data.get("amount", 1),
            "description": data.get("description", "Supplements payment")
        }
        print("🚀 Initiating STK Push with:", payload)
        try:
            mpesa_response = mpesa_instance.make_stk_push(payload)
            if mpesa_response and mpesa_response.get("ResponseCode") == "0":
                return {
                    "message": "STK push request sent successfully",
                    "data": mpesa_response
                }, 200
            else:
                return {
                    "message": "STK push request failed",
                    "data": mpesa_response
                }, 400
        except Exception as e:
            print(f"Error during STK push: {e}")
            return {"message": "Internal server error during STK push"}, 500


class PaymentCallbackResource(Resource):
    def post(self):
        try:
            data = request.get_json(silent=True)
            if data is None:
                return {"message": "Invalid JSON"}, 400

            print("Received M-Pesa callback:", data)

            # extract callback data
            stk_callback = data.get("Body", {}).get("stkCallback", {})
            merchant_request_id = stk_callback.get("MerchantRequestID")
            checkout_request_id = stk_callback.get("CheckoutRequestID")
            result_code = stk_callback.get("ResultCode")
            result_desc = stk_callback.get("ResultDesc")

            # extract metadata if payment was successful
            amount = None
            receipt_number = None
            phone_number = None
            transaction_date = None

            if result_code == 0:
                items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
                for item in items:
                    name = item.get("Name")
                    value = item.get("Value")
                    if name == "Amount":
                        amount = value
                    elif name == "MpesaReceiptNumber":
                        receipt_number = value
                    elif name == "PhoneNumber":
                        phone_number = str(value)
                    elif name == "TransactionDate":
                        transaction_date = str(value)

            # save to DB
            transaction = MpesaTransaction(
                merchant_request_id=merchant_request_id,
                checkout_request_id=checkout_request_id,
                result_code=result_code,
                result_desc=result_desc,
                amount=amount,
                mpesa_receipt_number=receipt_number,
                phone_number=phone_number,
                transaction_date=transaction_date
            )
            db.session.add(transaction)
            db.session.commit()
            print(f"✅ M-Pesa transaction saved: {receipt_number}")

            return {"message": "Callback received successfully"}, 200
        except Exception as e:
            print(f"Error processing callback: {e}")
            return {"message": "Internal server error"}, 500


class CheckPaymentStatusResource(Resource):
    def get(self, checkout_request_id):
        mpesa_instance = Mpesa()
        res = mpesa_instance.check_transaction(checkout_request_id)
        return {"message": "Ok", "data": res}


class MpesaTransactionListResource(Resource):
    @jwt_required()
    def get(self):
        transactions = MpesaTransaction.query.order_by(
            MpesaTransaction.created_at.desc()
        ).limit(100).all()
        return [t.to_dict() for t in transactions], 200