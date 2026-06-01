import os
from dotenv import load_dotenv
from flask import Flask
from flask_restful import Api
from extensions import db, migrate, jwt, limiter
from flask_cors import CORS


from flask import Flask, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt
from services.report_service import get_daily_report_data, get_recipient_emails
from services.email_service  import send_daily_report

from config import Config
from resources.products import ProductListResource, ProductResource ,ProductCSVUploadResource
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
    api.add_resource(ProductCSVUploadResource, '/products/upload-csv')

@app.route("/")
def index():
    return {"Message": "Welcome to POS backend API"}, 200

#mannual eamil trigger
@app.route("/admin/send-report", methods=["POST"])
@jwt_required()
def trigger_daily_report():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Admin access required."}), 403

    try:
        recipients = get_recipient_emails()
        if not recipients:
            return jsonify({
                "success": False,
                "message": "No users with emails found."
            }), 400

        data   = get_daily_report_data()
        result = send_daily_report(data, recipients)

        return jsonify({
            "success":    True,
            "date":       data["date"],
            "recipients": len(recipients),
            "sent":       result["sent"],
            "failed":     result["failed"],
        }), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    
# ── Cron-only trigger — protected by static secret, called by cron-job.org at 22:00 EAT ──
@app.route("/admin/send-report-cron", methods=["POST"])
def trigger_daily_report_cron():
    expected_secret = os.environ.get("CRON_SECRET")
    if not expected_secret:
        return jsonify({"success": False, "message": "CRON_SECRET not configured."}), 500

    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {expected_secret}":
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    try:
        recipients = get_recipient_emails()
        if not recipients:
            return jsonify({"success": False, "message": "No recipients."}), 400

        data   = get_daily_report_data()
        result = send_daily_report(data, recipients)
        return jsonify({
            "success":    True,
            "date":       data["date"],
            "recipients": len(recipients),
            "sent":       result["sent"],
            "failed":     result["failed"],
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    
if __name__ == "__main__":
    app.run(host="localhost", debug=True, port=5555)