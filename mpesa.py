import os
import base64
import requests
import json
from datetime import datetime
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load environment variables from .env file 
load_dotenv()


class Mpesa:
    def __init__(self):
        #  Initialize class with credentials and config values
        self.consumer_key = os.environ.get("CONSUMER_KEY")
        self.consumer_secret = os.environ.get("CONSUMER_SECRET")
        self.business_short_code = os.environ.get("BUSINESS_SHORT_CODE")
        self.pass_key = os.environ.get("SAF_PASS_KEY")
        self.timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.callback_url = os.environ.get("CALLBACK_URL")

    def get_access_token(self):
        """Fetch OAuth access token from Safaricom API"""
        try:
            url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
            
            res = requests.get(
                url,
                auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret)
            )
            res.raise_for_status()  # Raise error if request fails

            token = res.json().get("access_token")
            print("🔑 Fresh Access Token:", token)  # Debugging

            return token
        except requests.exceptions.RequestException as e:
            print("❌ Error fetching access token:", str(e))
            return None
    
    def generate_password(self):
        """Generate Base64 encoded password for STK push"""
        #  Build password string = BusinessShortCode + PassKey + Timestamp
        password_str = str(self.business_short_code) + str(self.pass_key) + str(self.timestamp)

        # Encode the string into Base64 as required by M-Pesa
        return base64.b64encode(password_str.encode()).decode("utf-8")
    
    def make_stk_push(self, data):
        """Initiate STK push request"""
        # Get access token by calling get_access_token()
        token = self.get_access_token()
        if not token:
            # If no token, return error immediately
            return {"error": "Failed to get access token."}
        
        # Make sure the amount is a valid integer
        amount = int(data.get("amount", 0))

        # Get the phone number from request data
        phone = str(data.get("phone", "")).strip()

        #  Build the STK Push request payload
        body = {    
            "BusinessShortCode": int(self.business_short_code),   
            "Password": self.generate_password(),        
            "Timestamp": self.timestamp,                               
            "TransactionType": "CustomerPayBillOnline",           
            "Amount": amount,                                     
            "PartyA": phone,                                      
            "PartyB": int(self.business_short_code),              
            "PhoneNumber": phone,
            "CallBackURL": self.callback_url,                     
            "AccountReference": "JoyceFeeds",                     
            "TransactionDesc": data.get("description")[:20]       
        }

        # Print payload for debugging before sending
        print("Sending STK push request with payload:", json.dumps(body, indent=4))

        try:
            #Send POST request to Safaricom STK Push API with JSON body + token
            response = requests.post(
               "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest",
               json=body,
               headers={
                   "Content-Type": "application/json",
                   "Authorization": f"Bearer {token}"
               }
            )
            # Print raw response for debugging
            print("Raw API Response:", response.text)

            # If Safaricom returned an error status code, raise exception
            response.raise_for_status()

            # Return response as JSON if all is good
            return response.json()
        except requests.exceptions.RequestException as e:
            # If request totally failed (network, auth, etc.), return error message
            return {"error": str(e)}
        

    def check_transaction(self,checkout_request_id):
        """Checks whetehr an stk push was succesfull or not (status of the transaction)"""
        data = {
            "BusinessShortCode":self.business_short_code,    
            "Password": self.generate_password(),    
            "Timestamp":self.timestamp,    
            "CheckoutRequestID": checkout_request_id,
        }

        token  = self.get_access_token()

        response =  requests.post(
            "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query",
            json=data,
            headers={
                "Content-Type":"application/json",
                "Authorization":f"Bearer {token}"
            }
        )

        return response.json()
        
