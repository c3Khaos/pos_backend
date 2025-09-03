from flask import request
from flask_restful import Resource
from mpesa import Mpesa   


class PaymentResource(Resource):
    def post(self):
        mpesa_instance = Mpesa()

        #  Read JSON payload from the request (phone, amount, description)
        data = request.get_json(silent=True) or {}
        payload = {
            "phone": data.get("phone", "254716310186"),   # Default sandbox number if not provided
            "amount": data.get("amount", 1),              # Default Ksh 1 if not provided
            "description": data.get("description", "Supplements payment")
        }

        print("🚀 Initiating STK Push with:", payload)

        try:
            #  Call make_stk_push() from Mpesa class with the payload
            mpesa_response = mpesa_instance.make_stk_push(payload)

            # Check response → Safaricom sends ResponseCode "0" if request was successful
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
            #If anything crashes, catch it and return 500 error
            print(f" Error during STK push: {e}")
            return {"message": "Internal server error during STK push"}, 500


class PaymentCallbackResource(Resource):
    def post(self):
        try:
            #  Receive JSON payload from Safaricom (callback data after STK push)
            data = request.get_json(silent=True)
            if data is None:
                return {"message": "Invalid JSON"}, 400

            print("Received M-Pesa callback. Processing data...")
            print(data)

            # (Optional) Save the transaction details into DB for record keeping

            # Respond to Safaricom that callback was received successfully
            return {"message": "Callback received successfully"}, 200
        except Exception as e:
            print(f" Error processing callback: {e}")
            return {"message": "Internal server error"}, 500
        


class CheckPaymentStatusResource(Resource):
    def get(self,checkout_request_id):
        mpesa_instance = Mpesa()

        res = mpesa_instance.check_transaction(checkout_request_id)

        return  {"message":"Ok", "data":res}
