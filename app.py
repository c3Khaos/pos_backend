import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_restful import Api
from flask_cors import CORS
from flask_jwt_extended import jwt_required, get_jwt
from extensions import db, migrate, jwt, limiter
from config import Config

from resources.products  import ProductListResource, ProductResource, ProductCSVUploadResource
from resources.sales     import SaleListResource
from resources.returns   import ReturnListResource, ReturnResource
from resources.restock   import RestockListResource, RestockResource
from resources.reconciliation import ReconciliationResource
from resources.reports   import ReportsResource
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
from resources.advances import (
    CashAdvanceListResource,
    CashAdvanceReturnResource,
    CashAdvanceSummaryResource,
)
from resources.settings import SettingsResource, ChangePasswordResource
from resources.suppliers import SupplierListResource, SupplierResource
from resources.expenses  import ExpenseListResource, ExpenseResource
from resources.debtors   import DebtorListResource, DebtorDetailResource, DebtorPaymentResource
from services.report_service import get_daily_report_data, get_recipient_emails
from services.email_service  import send_daily_report

load_dotenv()

# ── CORS_ORIGIN: warn locally, hard-fail in production ───────────────────────
# Moved out of module-level raise so flask db commands can run without it.
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://localhost:5173")

app = Flask(__name__)
app.config.from_object(Config)

CORS(app, supports_credentials=True, origins=[CORS_ORIGIN])

limiter.init_app(app)
db.init_app(app)
migrate.init_app(app, db)
jwt.init_app(app)

with app.app_context():
    api = Api(app)
    CORS(api.blueprint, origins=[CORS_ORIGIN], supports_credentials=True)

    # ── Products ──────────────────────────────────────────────────────────
    api.add_resource(ProductListResource,          "/products")
    api.add_resource(ProductResource,              "/products/<int:product_id>")
    api.add_resource(ProductCSVUploadResource,     "/products/upload-csv")

    # ── Sales ─────────────────────────────────────────────────────────────
    api.add_resource(SaleListResource,             "/sales")

    # ── Returns ───────────────────────────────────────────────────────────
    api.add_resource(ReturnListResource,           "/returns")
    api.add_resource(ReturnResource,               "/returns/<int:return_id>")

    # ── Restock ───────────────────────────────────────────────────────────
    api.add_resource(RestockListResource,          "/restock")
    api.add_resource(RestockResource,              "/restock/<int:restock_id>")

    # ── Reconciliation ────────────────────────────────────────────────────
    api.add_resource(ReconciliationResource,       "/reconciliation")

    # ── Reports ───────────────────────────────────────────────────────────
    api.add_resource(ReportsResource,              "/reports")

    # ── Auth + Users ──────────────────────────────────────────────────────
    api.add_resource(RegisterResource,             "/register")
    api.add_resource(LoginResource,                "/login")
    api.add_resource(UserListResource,             "/users")
    api.add_resource(UserResource,                 "/users/<int:user_id>")

    # ── Payments ──────────────────────────────────────────────────────────
    api.add_resource(PaymentResource,              "/payments")
    api.add_resource(PaymentCallbackResource,      "/payments/callback")
    api.add_resource(CheckPaymentStatusResource,   "/payments/check/<string:payment_id>")
    api.add_resource(MpesaWebhookResource,         "/payments/webhook")
    api.add_resource(MpesaTransactionListResource, "/mpesa-transactions")

    # ── Dashboard + Graphs ────────────────────────────────────────────────
    api.add_resource(DashboardInfo,                "/dashboard-stats")
    api.add_resource(SalesTrend,                   "/salestrend")

    # ── Suppliers ─────────────────────────────────────────────────────────
    api.add_resource(SupplierListResource,         "/suppliers")
    api.add_resource(SupplierResource,             "/suppliers/<int:supplier_id>")

    # ── Expenses ──────────────────────────────────────────────────────────
    api.add_resource(ExpenseListResource,          "/expenses")
    api.add_resource(ExpenseResource,              "/expenses/<int:expense_id>")

    # ── Debtors ───────────────────────────────────────────────────────────
    api.add_resource(DebtorListResource,           "/debtors")
    api.add_resource(DebtorDetailResource,         "/debtors/<int:sale_id>")
    api.add_resource(DebtorPaymentResource,        "/debtors/<int:sale_id>/pay")

    # ── Cash Advances ─────────────────────────────────────────────────────
    api.add_resource(CashAdvanceListResource,      "/advances")
    api.add_resource(CashAdvanceReturnResource,    "/advances/<int:advance_id>/return")
    api.add_resource(CashAdvanceSummaryResource,   "/advances/summary")
    # ── Settings ──────────────────────────────────────────────────────────────
    api.add_resource(SettingsResource,        "/settings")
    api.add_resource(ChangePasswordResource,  "/settings/change-password")

# ── Health check + cron keepalive ─────────────────────────────────────────────
@app.route("/")
def index():
    return {"message": "StockEdge POS API"}, 200


# ── Manual email report trigger ───────────────────────────────────────────────
@app.route("/admin/send-report", methods=["POST"])
@jwt_required()
def trigger_daily_report():
    claims = get_jwt()
    if claims.get("role") != "admin":
        return jsonify({"success": False, "message": "Admin access required."}), 403
    try:
        recipients = get_recipient_emails()
        if not recipients:
            return jsonify({"success": False, "message": "No recipients found."}), 400
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


# ── Cron trigger — called by cron-job.org at 22:00 EAT ───────────────────────
@app.route("/admin/send-report-cron", methods=["POST"])
def trigger_daily_report_cron():
    expected = os.environ.get("CRON_SECRET")
    if not expected:
        return jsonify({"success": False, "message": "CRON_SECRET not configured."}), 500
    if request.headers.get("Authorization", "") != f"Bearer {expected}":
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
@jwt.expired_token_loader
def handle_expired_token_callback(jwt_header, jwt_payload):
    """
    Safely intercepts expired JWT tokens, preventing a 500 server crash 
    and allowing CORS headers to wrap the response naturally.
    """
    response = jsonify({
        "status": 401,
        "error": "token_expired",
        "message": "Your login session has expired. Please log in again."
    })
    return response, 401

if __name__ == "__main__":
    app.run(host="localhost", debug=True, port=5555)