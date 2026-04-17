import os
from flask import Flask
from flask_restful import Api
from extensions import db, migrate,jwt
from flask_cors import CORS
from dotenv import load_dotenv




from config import Config
from resources.products import ProductListResource,ProductResource
from resources.sales import SaleListResource
from resources.userActions import UserListResource, UserResource
from auth import LoginResource, RegisterResource
from resources.graphs import SalesTrend
from resources.dashboardStatus import DashboardInfo
from resources.payment import PaymentResource,PaymentCallbackResource,CheckPaymentStatusResource
from resources.suppliers import SupplierListResource, SupplierResource
from resources.expenses import ExpenseListResource, ExpenseResource

# Load environment variables (your secret keys!)
load_dotenv()

CORS_ORIGIN = os.environ.get("CORS_ORIGIN")

if not CORS_ORIGIN:
    raise RuntimeError("CORS_ORIGIN is not set")

app = Flask(__name__)
app.config.from_object(Config)
CORS(app,supports_credentials=True,origins=[CORS_ORIGIN])

#cloudinary 




db.init_app(app)
migrate.init_app(app, db)
jwt.init_app(app) # Initialize JWT tool for ID cards

with app.app_context():
#import and register resources
    api = Api(app)
    api.add_resource(ProductListResource,"/products")
    api.add_resource(ProductResource, '/products/<int:product_id>')
    api.add_resource(SaleListResource, "/sales")
    api.add_resource(RegisterResource, "/register")
    api.add_resource(UserListResource, '/users')
    api.add_resource(UserResource, '/users/<int:user_id>')
    api.add_resource(LoginResource, "/login")
    api.add_resource(PaymentResource, "/payments")
    api.add_resource(SalesTrend,"/salestrend")
    api.add_resource(DashboardInfo, '/dashboard-stats')
    api.add_resource(PaymentCallbackResource, "/payments/callback")
    api.add_resource(CheckPaymentStatusResource,"/payments/check/<string:checkout_request_id>")
    api.add_resource(SupplierListResource, '/suppliers')
    api.add_resource(SupplierResource, '/suppliers/<int:supplier_id>')
    api.add_resource(ExpenseListResource, '/expenses')
    api.add_resource(ExpenseResource, '/expenses/<int:expense_id>')


@app.route("/")
def index():
    return{"Message":"Welcome to POS backend APi"},200


@app.route("/run-migrations")
def run_migrations():
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id SERIAL PRIMARY KEY,
                    description VARCHAR(200) NOT NULL,
                    amount FLOAT NOT NULL,
                    category VARCHAR(80) NOT NULL,
                    expense_date TIMESTAMP NOT NULL,
                    recorded_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW()
                );
            """))
            conn.execute(db.text("""
                UPDATE alembic_version SET version_num = '04f3b64dc3e3';
            """))
            conn.commit()
        return {"message": "Done"}, 200
    except Exception as e:
        return {"error": str(e)}, 500

if __name__=="__main__":
    app.run(host="localhost",debug=True,port = 5555)