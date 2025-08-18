import requests
from flask_restful import Resource

from mpesa import Mpesa

class PaymentResource(Resource):
    def post(self):
        mpesa_instance = Mpesa()
        mpesa_instance.get_access_token()

        data = {
            "phone":"254716310186",
            "amount":1,
            "description":"Suppliments payment"
        }
         
        mpesa_response = mpesa_instance.make_stk_push(data)

        return {"message":"OK","data":mpesa_response}
        

class PaymentCallbackResource(Resource):
    def post(self):
        data = requests.json()
        print(data)
        return {"message":"On track"}           