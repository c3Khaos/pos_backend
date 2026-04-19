import os
import base64
import requests
import json
import time
from datetime import datetime
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

# Module-level token cache — shared across all Mpesa instances
_token_cache = {"token": None, "expires_at": 0}

class Mpesa:
    def __init__(self):
        self.consumer_key = os.environ.get("CONSUMER_KEY")
        self.consumer_secret = os.environ.get("CONSUMER_SECRET")
        self.business_short_code = os.environ.get("BUSINESS_SHORT_CODE")
        self.pass_key = os.environ.get("SAF_PASS_KEY")
        self.timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.callback_url = os.environ.get("CALLBACK_URL")

        mpesa_env = os.environ.get("MPESA_ENV", "sandbox")
        self.base_url = "https://api.kopokopo.co.ke" if mpesa_env == "production" else "https://sandbox.kopokopo.co.ke"

    def get_access_token(self):
        now = time.time()
        # Return cached token if still valid
        if _token_cache["token"] and now < _token_cache["expires_at"]:
            print("✅ Using cached token")
            return _token_cache["token"]

        try:
            url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
            res = requests.get(url, auth=HTTPBasicAuth(self.consumer_key, self.consumer_secret))
            res.raise_for_status()
            token = res.json().get("access_token")
            # Cache token for 58 minutes (expires in 60)
            _token_cache["token"] = token
            _token_cache["expires_at"] = now + 3480
            print("🔑 Fresh Access Token fetched")
            return token
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching access token: {e}")
            return None

    def generate_password(self):
        password_str = str(self.business_short_code) + str(self.pass_key) + str(self.timestamp)
        return base64.b64encode(password_str.encode()).decode("utf-8")

    def make_stk_push(self, data):
        token = self.get_access_token()
        if not token:
            return {"error": "Failed to get access token."}

        amount = int(data.get("amount", 0))
        phone = str(data.get("phone", "")).strip()

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
            "AccountReference": "Joycestores",
            "TransactionDesc": data.get("description", "")[:20]
        }

        print("Sending STK push:", json.dumps(body, indent=4))

        try:
            response = requests.post(
                f"{self.base_url}/mpesa/stkpush/v1/processrequest",
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }
            )
            print("Raw API Response:", response.text)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def check_transaction(self, checkout_request_id):
        token = self.get_access_token()
        if not token:
            return {"error": "Failed to get access token."}

        data = {
            "BusinessShortCode": self.business_short_code,
            "Password": self.generate_password(),
            "Timestamp": self.timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        try:
            response = requests.post(
                f"{self.base_url}/mpesa/stkpushquery/v1/query",
                json=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}"
                }
            )
            if not response.text.strip():
                return {"error": "Empty response from Safaricom"}
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"check_transaction error: {e}")
            return {"error": str(e)}