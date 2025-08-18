import os
import base64

import requests

from datetime import datetime
from requests.auth import HTTPBasicAuth

from dotenv import load_dotenv

load_dotenv()

class Mpesa:
    consumer_key = None
    consumer_secret = None
    business_short_code = "self."
    timestamp = None

    def __init__(self):
        self.consumer_key = os.environ.get("CONSUMER_KEY")
        self.consumer_secret = os.environ.get("CONSUMER_SECRET")
        self.timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    """
    -> generate access token that will be used in subsequent requests
    -> it gat a timestap that expires

    """
    def get_access_token(self):

        #retrieve token from storage and if stii active we use it else we get a new one from saf
        #stored_data = MpesaAcessToken


        res = requests.get(
            "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
            auth=HTTPBasicAuth(self.consumer_key,self.consumer_secret)
        )

        data = res.json()
        #save the access token somewhere  
        return data["access_token"]
    
    def generate_password(self):
        """
        -> generated paswword by combining shortcode,passkey&current timestamp
        """

        password_str = self.business_short_code + os.environ.get("SAF_PASS_KEY") + self.timestamp

        return base64.b64encode(password_str.encode()).decode("utf-8")
    
    def make_stk_push(self,data):
        amount = data["amount"]
        phone = data["phone"]
        desc = data["description"]

        body = {    
            "BusinessShortCode": self.business_short_code,    
            "Password":self.generate_password(),    
            "Timestamp":self.timestamp,    
            "TransactionType": "CustomerPayBillOnline",    
            "Amount": amount,    
            "PartyA":phone,    
            "PartyB":self.business_short_code,    
            "PhoneNumber":phone,    
            "CallBackURL": "https://mydomain.com/pat",    
            "AccountReference":"Joyce Food Stores & Animal Feeds",    
            "TransactionDesc":desc
        }

        token = self.get_access_token()

        response = requests.post(
           " https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
           json = body,
           headers={
               "content-Type": "application/json",
               "Authorization": f"Bearer {token}"
           }
        )

        response_data = response.json()
        print (response_data)


        