# services/email_service.py
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText


def _build_html(data: dict) -> str:
    """Build the HTML email body from report data."""

    summary       = data["summary"]
    top_products  = data["top_products"]
    low_stock     = data["low_stock"]
    out_of_stock  = data["out_of_stock"]
    report_date   = data["date"]

    net_color = "#34d399" if summary["net_profit"] >= 0 else "#f87171"

    # ── Top products rows ──
    product_rows = ""
    for i, p in enumerate(top_products, start=1):
        product_rows += f"""
        <tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:10px 8px;color:#9ca3af;font-size:13px;">{i}</td>
          <td style="padding:10px 8px;color:#f3f4f6;font-size:13px;">{p['name']}</td>
          <td style="padding:10px 8px;color:#9ca3af;font-size:12px;">{p['category']}</td>
          <td style="padding:10px 8px;color:#f3f4f6;font-size:13px;text-align:right;">{p['qty_sold']}</td>
          <td style="padding:10px 8px;color:#34d399;font-size:13px;text-align:right;">
            KSh {p['revenue']:,.0f}
          </td>
        </tr>"""

    # ── Low stock rows ──
    low_stock_rows = ""
    for p in low_stock:
        low_stock_rows += f"""
        <tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:8px;color:#f3f4f6;font-size:13px;">{p['name']}</td>
          <td style="padding:8px;color:#9ca3af;font-size:12px;">{p['category']}</td>
          <td style="padding:8px;text-align:right;">
            <span style="background:#78350f;color:#fbbf24;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;">
              {p['stock']} left
            </span>
          </td>
        </tr>"""

    # ── Out of stock rows ──
    out_of_stock_rows = ""
    for p in out_of_stock:
        out_of_stock_rows += f"""
        <tr style="border-bottom:1px solid #1f2937;">
          <td style="padding:8px;color:#f3f4f6;font-size:13px;">{p['name']}</td>
          <td style="padding:8px;color:#9ca3af;font-size:12px;">{p['category']}</td>
          <td style="padding:8px;text-align:right;">
            <span style="background:#450a0a;color:#f87171;padding:2px 8px;border-radius:9999px;font-size:11px;font-weight:600;">
              OUT OF STOCK
            </span>
          </td>
        </tr>"""

    low_block = f"""
    <h3 style="color:#fbbf24;font-size:14px;margin:0 0 8px;">
      ⚠️ Low Stock ({len(low_stock)} products)
    </h3>
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
    <h3 style="color:#f87171;font-size:14px;margin:0 0 8px;">
      🚫 Out of Stock ({len(out_of_stock)} products)
    </h3>
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

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
    <body style="margin:0;padding:0;background:#030712;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
      <div style="max-width:600px;margin:0 auto;padding:24px 16px;">

        <!-- Header -->
        <div style="text-align:center;margin-bottom:32px;">
          <p style="color:#6b7280;font-size:12px;margin:0 0 4px;text-transform:uppercase;letter-spacing:2px;">
            Daily Report
          </p>
          <h1 style="color:#f9fafb;font-size:22px;font-weight:700;margin:0;">{report_date}</h1>
        </div>

        <!-- Summary cards -->
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
          This report was automatically generated at 10:00 PM EAT.
        </p>
      </div>
    </body>
    </html>
    """


def send_daily_report(data: dict, recipients: list[str]) -> dict:
    """
    Send the daily report to a list of recipient emails.
    Returns a summary of how many succeeded and failed.

    Usage:
        emails = get_recipient_emails()
        send_daily_report(data, emails)
    """
    smtp_host     = os.environ.get("MAIL_SERVER",   "smtp.gmail.com")
    smtp_port     = int(os.environ.get("MAIL_PORT", 587))
    smtp_user     = os.environ.get("MAIL_USERNAME")
    smtp_password = os.environ.get("MAIL_PASSWORD")

    if not all([smtp_user, smtp_password]):
        print("[report] Missing MAIL_USERNAME or MAIL_PASSWORD — report not sent.")
        return {"sent": 0, "failed": len(recipients)}

    if not recipients:
        print("[report] No recipients found — nobody to send to.")
        return {"sent": 0, "failed": 0}

    subject   = f"Daily Report — {data['date']}"
    html_body = _build_html(data)
    plain_body = (
        f"Daily Report: {data['date']}\n\n"
        f"Revenue:      KSh {data['summary']['revenue']:,.0f}\n"
        f"Gross Profit: KSh {data['summary']['gross_profit']:,.0f}\n"
        f"Expenses:     KSh {data['summary']['expenses']:,.0f}\n"
        f"Net Profit:   KSh {data['summary']['net_profit']:,.0f}\n"
        f"Transactions: {data['summary']['transactions']}\n\n"
        f"Low stock:    {len(data['low_stock'])} products\n"
        f"Out of stock: {len(data['out_of_stock'])} products\n"
    )

    sent   = 0
    failed = 0

    # Open ONE SMTP connection and send all emails through it
    # This is significantly faster than opening a new connection per recipient
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)

            for email in recipients:
                try:
                    msg = MIMEMultipart("alternative")
                    msg["Subject"] = subject
                    msg["From"]    = smtp_user
                    msg["To"]      = email

                    msg.attach(MIMEText(plain_body, "plain"))
                    msg.attach(MIMEText(html_body,  "html"))

                    server.sendmail(smtp_user, email, msg.as_string())
                    print(f"[report] ✓ Sent to {email}")
                    sent += 1

                except Exception as e:
                    print(f"[report] ✗ Failed for {email}: {e}")
                    failed += 1

    except Exception as e:
        print(f"[report] SMTP connection failed: {e}")
        return {"sent": 0, "failed": len(recipients)}

    print(f"[report] Done — {sent} sent, {failed} failed out of {len(recipients)} recipients")
    return {"sent": sent, "failed": failed}