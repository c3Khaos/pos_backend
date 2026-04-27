import os
from flask import Flask
from flask_restful import Api
from extensions import db, migrate, jwt, limiter
from flask_cors import CORS
from dotenv import load_dotenv

from config import Config
from resources.products import ProductListResource, ProductResource
from resources.sales import SaleListResource
from resources.userActions import UserListResource, UserResource
from auth import LoginResource, RegisterResource
from resources.graphs import SalesTrend
from resources.dashboardStatus import DashboardInfo
from resources.payment import (
    PaymentResource,
    PaymentCallbackResource,
    CheckPaymentStatusResource,
    MpesaWebhookResource,
    MpesaTransactionListResource,
)
from resources.hardware import (
    HardwareDashboardResource,
    HardwareSalesTrendResource,
    HardwareSalesResource,
    HardwareLowStockResource,
)
from resources.advances import (
    CashAdvanceListResource,
    CashAdvanceReturnResource,
    CashAdvanceSummaryResource,
)
from resources.suppliers import SupplierListResource, SupplierResource
from resources.expenses import ExpenseListResource, ExpenseResource
from resources.debtors import DebtorListResource, DebtorDetailResource, DebtorPaymentResource

load_dotenv()

CORS_ORIGIN = os.environ.get("CORS_ORIGIN")

if not CORS_ORIGIN:
    raise RuntimeError("CORS_ORIGIN is not set")

app = Flask(__name__)
app.config.from_object(Config)
CORS(app, supports_credentials=True, origins=[CORS_ORIGIN])

limiter.init_app(app)

db.init_app(app)
migrate.init_app(app, db)
jwt.init_app(app)

with app.app_context():
    api = Api(app)
    api.add_resource(ProductListResource,          "/products")
    api.add_resource(ProductResource,              "/products/<int:product_id>")
    api.add_resource(SaleListResource,             "/sales")
    api.add_resource(RegisterResource,             "/register")
    api.add_resource(UserListResource,             "/users")
    api.add_resource(UserResource,                 "/users/<int:user_id>")
    api.add_resource(LoginResource,                "/login")
    api.add_resource(PaymentResource,              "/payments")
    api.add_resource(PaymentCallbackResource,      "/payments/callback")
    api.add_resource(CheckPaymentStatusResource,   "/payments/check/<string:payment_id>")
    api.add_resource(MpesaWebhookResource,         "/payments/webhook")
    api.add_resource(MpesaTransactionListResource, "/mpesa-transactions")
    api.add_resource(SalesTrend,                   "/salestrend")
    api.add_resource(DashboardInfo,                "/dashboard-stats")
    api.add_resource(SupplierListResource,         "/suppliers")
    api.add_resource(SupplierResource,             "/suppliers/<int:supplier_id>")
    api.add_resource(ExpenseListResource,          "/expenses")
    api.add_resource(ExpenseResource,              "/expenses/<int:expense_id>")
    api.add_resource(DebtorListResource,           "/debtors")
    api.add_resource(DebtorDetailResource,         "/debtors/<int:sale_id>")
    api.add_resource(DebtorPaymentResource,        "/debtors/<int:sale_id>/pay")
    api.add_resource(HardwareDashboardResource,  "/hardware/dashboard-stats")
    api.add_resource(HardwareSalesTrendResource, "/hardware/sales-trend")
    api.add_resource(HardwareSalesResource,      "/hardware/sales")
    api.add_resource(HardwareLowStockResource,   "/hardware/low-stock")
    api.add_resource(CashAdvanceListResource,    '/advances')
    api.add_resource(CashAdvanceReturnResource,  '/advances/<int:advance_id>/return')
    api.add_resource(CashAdvanceSummaryResource, '/advances/summary')

@app.route("/")
def index():
    return {"Message": "Welcome to POS backend API"}, 200

@app.route("/setup/seed-admin")
def seed_admin_route():
    from models import User
    from extensions import db

    existing = User.query.filter_by(username="joyce").first()
    if existing:
        return {"message": "Admin already exists"}, 200

    admin = User(
        username = "joyce",
        email    = "joycewanjiku494@gmail.com",
        role     = "admin",
        active   = True
    )
    admin.set_password("@joyce")  
    db.session.add(admin)
    db.session.commit()
    return {"message": "Admin seeded successfully!"}, 200

if __name__ == "__main__":
    app.run(host="localhost", debug=True, port=5555)