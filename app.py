import os
from flask import Flask
from flask_restful import Api
from extensions import db, migrate,jwt
from flask_cors import CORS
from dotenv import load_dotenv



from config import Config
from resources.products import ProductListResource
from resources.sales import SaleListResource
from auth import LoginResource, RegisterResource
from resources.checkStatus import UsersExist 
from resources.graphs import SalesTrend
from resources.dashboardStatus import DashboardInfo
from resources.payment import PaymentResource,PaymentCallbackResource,CheckPaymentStatusResource

# Load environment variables (your secret keys!)
load_dotenv()

CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://localhost:5173")

app = Flask(__name__)
app.config.from_object(Config)
CORS(app,supports_credentials=True,origins=[CORS_ORIGIN])

db.init_app(app)
migrate.init_app(app, db)
jwt.init_app(app) # Initialize JWT tool for ID cards

with app.app_context():
#import and register resources
    api = Api(app)
    api.add_resource(ProductListResource,"/products")
    api.add_resource(SaleListResource, "/sales")
    api.add_resource(RegisterResource, "/register")
    api.add_resource(LoginResource, "/login")
    api.add_resource(UsersExist, "/users/exists")
    api.add_resource(PaymentResource, "/payments")
    api.add_resource(SalesTrend,"/salestrend")
    api.add_resource(DashboardInfo, '/dashboard-stats')
    api.add_resource(PaymentCallbackResource, "/payments/callback")
    api.add_resource(CheckPaymentStatusResource,"/payments/check/<string:checkout_request_id>")

@app.route("/")
def index():
    return{"Message":"Welcome to POS backend APi"},200

if __name__=="__main__":
    app.run(host="localhost",debug=True,port = 5555)