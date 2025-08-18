import os
import requests
from requests.auth import HTTPBasicAuth

from dotenv import load_dotenv

load_dotenv()

class Mpesa:
    consumer_key = None
    consumer_secret = None

    def __init__(self):
        self.consumer_key = os.environ.get("consumer_key")
        self.consumer_secret = os.environ.get("consumer_secret")

    """
    -> generate access token that will be used in subsequent requests
    -> it gat a timestap that expires

    """
    def get_access_token(self):
        res = requests.get(
            "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials",
            auth=HTTPBasicAuth(self.consumer_key,self.consumer_secret)
        )

        data = res.json()
        return data["access_token"]