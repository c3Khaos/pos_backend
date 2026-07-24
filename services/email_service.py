# services/email_service.py
"""
Sends the daily business report via Resend (HTTPS API).

Required env vars:
    RESEND_API_KEY   - Resend API key (starts with re_...)
    MAIL_FROM_EMAIL  - sender address. Use 'onboarding@resend.dev' until you verify a domain
    MAIL_FROM_NAME   - display name shown to recipients (e.g. "StockEdge Daily Report")
"""

import os
import logging
import resend
from models import User

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HTML Template
# ─────────────────────────────────────────────────────────────────────────────
def _build_html(data: dict) -> str:
    """Build the HTML email body from the compiled report data."""

    summary      = data["summary"]
    top_products = data["top_products"]
    low_stock    = data["low_stock"]
    out_of_stock = data["out_of_stock"]
    report_date  = data["date"]

    net_color = "#34d399" if summary["net_profit"] >= 0 else "#f87171"

    product_rows = "".join(
        f"""
        <tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:10px 8px;color:#9ca3af;font-size:13px;">{i}</td>
          <td style="padding:10px 8px;color:#f3f4f6;font-size:13px;">{p['name']}</td>
          <td style="padding:10px 8px;color:#9ca3af;font-size:12px;">{p['category']}</td>
          <td style="padding:10px 8px;color:#f3f4f6;font-size:13px;text-align:right;">{p['qty_sold']:g}</td>
          <td style="padding:10px 8px;color:#34d399;font-size:13px;text-align:right;">
            KSh {p['revenue']:,.0f}
          </td>
        </tr>"""
        for i, p in enumerate(top_products, start=1)
    )

    low_stock_rows = "".join(
        f"""
        <tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:8px;color:#f3f4f6;font-size:13px;">{p['name']}</td>
          <td style="padding:8px;color:#9ca3af;font-size:12px;">{p['category']}</td>
          <td style="padding:8px;text-align:right;">
            <span style="background:#78350f;color:#fbbf24;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;">
              {p['stock']:g} left
            </span>
          </td>
        </tr>"""
        for p in low_stock
    )

    out_of_stock_rows = "".join(
        f"""
        <tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:8px;color:#f3f4f6;font-size:13px;">{p['name']}</td>
          <td style="padding:8px;color:#9ca3af;font-size:12px;">{p['category']}</td>
          <td style="padding:8px;text-align:right;">
            <span style="background:#450a0a;color:#f87171;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;">
              OUT OF STOCK
            </span>
          </td>
        </tr>"""
        for p in out_of_stock
    )

    low_block = f"""
    <h3 style="color:#fbbf24;font-size:14px;margin:0 0 8px;">⚠️ Low Stock ({len(low_stock)} products)</h3>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:24px;">
      <thead>
        <tr style="border-bottom:1px solid #374151;">
          <th style="padding:8px;color:#6b7280;font-size:11px;text-align:left;font-weight:600;">PRODUCT</th>
          <th style="padding:8px;color:#6b7280;font-size:11px;text-align:left;font-weight:600;">CATEGORY</th>
          <th style="padding:8px;color:#6b7280;font-size:11px;text-align:right;font-weight:600;">STOCK</th>
        </tr>
      </thead>
      <tbody>{low_stock_rows}</tbody>
    </table>""" if low_stock else ""

    out_block = f"""
    <h3 style="color:#f87171;font-size:14px;margin:0 0 8px;">🚫 Out of Stock ({len(out_of_stock)} products)</h3>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <thead>
        <tr style="border-bottom:1px solid #374151;">
          <th style="padding:8px;color:#6b7280;font-size:11px;text-align:left;font-weight:600;">PRODUCT</th>
          <th style="padding:8px;color:#6b7280;font-size:11px;text-align:left;font-weight:600;">CATEGORY</th>
          <th style="padding:8px;color:#6b7280;font-size:11px;text-align:right;font-weight:600;">STATUS</th>
        </tr>
      </thead>
      <tbody>{out_of_stock_rows}</tbody>
    </table>""" if out_of_stock else ""

    stock_section = f"""
    <div style="background:#111827;border:1px solid #374151;border-radius:12px;padding:20px;margin-bottom:24px;">
      {low_block}
      {out_block}
    </div>""" if (low_stock or out_of_stock) else ""

    top_products_section = f"""
    <div style="background:#111827;border:1px solid #374151;border-radius:12px;padding:20px;margin-bottom:24px;">
      <h3 style="color:#e5e7eb;font-size:14px;margin:0 0 12px;">🏆 Top Selling Products</h3>
      <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
        <thead>
          <tr style="border-bottom:1px solid #374151;">
            <th style="padding:8px;color:#6b7280;font-size:11px;text-align:left;">#</th>
            <th style="padding:8px;color:#6b7280;font-size:11px;text-align:left;">PRODUCT</th>
            <th style="padding:8px;color:#6b7280;font-size:11px;text-align:left;">CATEGORY</th>
            <th style="padding:8px;color:#6b7280;font-size:11px;text-align:right;">QTY</th>
            <th style="padding:8px;color:#6b7280;font-size:11px;text-align:right;">REVENUE</th>
          </tr>
        </thead>
        <tbody>{product_rows}</tbody>
      </table>
    </div>""" if top_products else ""

    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#030712;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <div style="max-width:600px;margin:0 auto;padding:24px 16px;">

    <div style="text-align:center;margin-bottom:32px;">
      <p style="color:#6b7280;font-size:12px;margin:0 0 4px;text-transform:uppercase;letter-spacing:2px;">Daily Report</p>
      <h1 style="color:#f9fafb;font-size:22px;font-weight:700;margin:0;">{report_date}</h1>
    </div>

    <div style="margin-bottom:24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="50%" style="padding:0 6px 12px 0;">
            <div style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:16px;">
              <p style="color:#6b7280;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;">Revenue</p>
              <p style="color:#f9fafb;font-size:20px;font-weight:700;margin:0;">KSh {summary['revenue']:,.0f}</p>
            </div>
          </td>
          <td width="50%" style="padding:0 0 12px 6px;">
            <div style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:16px;">
              <p style="color:#6b7280;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;">Gross Profit</p>
              <p style="color:#34d399;font-size:20px;font-weight:700;margin:0;">KSh {summary['gross_profit']:,.0f}</p>
            </div>
          </td>
        </tr>
        <tr>
          <td width="50%" style="padding:0 6px 0 0;">
            <div style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:16px;">
              <p style="color:#6b7280;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;">Expenses</p>
              <p style="color:#f87171;font-size:20px;font-weight:700;margin:0;">KSh {summary['expenses']:,.0f}</p>
            </div>
          </td>
          <td width="50%" style="padding:0 0 0 6px;">
            <div style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:16px;">
              <p style="color:#6b7280;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:0 0 6px;">Net Profit</p>
              <p style="color:{net_color};font-size:20px;font-weight:700;margin:0;">KSh {summary['net_profit']:,.0f}</p>
            </div>
          </td>
        </tr>
      </table>
      <div style="background:#111827;border:1px solid #1f2937;border-radius:12px;padding:14px;margin-top:12px;text-align:center;">
        <p style="color:#6b7280;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin:0 0 4px;">Transactions</p>
        <p style="color:#f9fafb;font-size:24px;font-weight:700;margin:0;">{summary['transactions']}</p>
      </div>
    </div>

    {top_products_section}
    {stock_section}

    <p style="color:#374151;font-size:11px;text-align:center;margin-top:32px;">
      Automatically generated daily at 10:00 PM EAT.<br>
      Do not reply — this inbox is unmonitored.
    </p>
  </div>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────
def send_daily_report(data: dict) -> dict:
    """
    Send the daily report via Resend HTTPS API.
    Sends one email per recipient with proper error tracking.
    """
    api_key    = os.environ.get("RESEND_API_KEY")
    from_email = os.environ.get("MAIL_FROM_EMAIL", "onboarding@resend.dev")
    from_name  = os.environ.get("MAIL_FROM_NAME",  "POS Daily Report")
    users = (
    User.query
    .filter(User.role == "admin",
            User.active == True)
    .with_entities(User.email)
    .all()
)
    recipients = [
    user.email
    for user in users
    if user.email
]

    if not api_key:
        logger.error("Missing RESEND_API_KEY — report not sent.")
        return {"sent": 0, "failed": len(recipients)}

    if not recipients:
        logger.warning("No recipients provided.")
        return {"sent": 0, "failed": 0}

    resend.api_key = api_key

    subject   = f"Daily Report — {data['date']}"
    html_body = _build_html(data)
    from_addr = f"{from_name} <{from_email}>"

    sent   = 0
    failed = 0

    for email in recipients:
        try:
            response = resend.Emails.send({
                "from":    from_addr,
                "to":      [email],
                "subject": subject,
                "html":    html_body,
            })
            logger.info(f"Report sent to {email} (id={response.get('id')})")
            sent += 1
        except Exception as e:
            logger.error(f"Failed to send to {email}: {e}")
            failed += 1

    logger.info(f"Report job complete — {sent} sent, {failed} failed")
    return {"sent": sent, "failed": failed}