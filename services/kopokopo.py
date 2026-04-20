# services/kopokopo.py

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
import hmac      # For webhook signature verification (HMAC algorithm)
import hashlib   # Provides SHA-256 — the hashing algorithm Kopo Kopo uses
import requests  # HTTP library — used to talk to Kopo Kopo's servers
import time      # Used for token expiry timestamps (how we know when to refresh)
from flask import current_app   # Gives us access to Flask's config (env variables)


# ─────────────────────────────────────────────────────────────────────────────
# THE SERVICE CLASS
# ─────────────────────────────────────────────────────────────────────────────
# Why a class? It groups all Kopo Kopo logic in one place.
# Why classmethods? Because we want shared state (cached token) across all calls
# without needing to create instances every time.
# ─────────────────────────────────────────────────────────────────────────────

class KopoKopoService:
    """
    Clean, isolated Kopo Kopo integration.
    Swap sandbox ↔ production by changing KOPOKOPO_ENV in .env
    """

    # ──────────────────────────────────────────────────────────────────────────
    # CLASS-LEVEL CACHE VARIABLES
    # ──────────────────────────────────────────────────────────────────────────
    # These are shared across ALL uses of the class — like global variables
    # scoped to this class. Every time someone calls get_token(), we check
    # these first before hitting the Kopo Kopo API.
    # ──────────────────────────────────────────────────────────────────────────
    _token        = None   # Will hold the OAuth token once we fetch it
    _token_expiry = 0      # Unix timestamp — when the token becomes invalid


    # ──────────────────────────────────────────────────────────────────────────
    # METHOD 1 — DECIDE WHICH BASE URL TO USE
    # ──────────────────────────────────────────────────────────────────────────
    # Kopo Kopo has two completely separate servers:
    #   SANDBOX    → for testing (fake money, no real charges)
    #   PRODUCTION → for real customers (real money moves)
    #
    # This method reads KOPOKOPO_ENV from config and picks the right URL.
    # This is the MAGIC that lets us switch environments with one env var.
    # ──────────────────────────────────────────────────────────────────────────
    @classmethod
    def _base_url(cls):
        # current_app.config reads from your config.py which reads from .env
        env = current_app.config.get('KOPOKOPO_ENV', 'sandbox')  # default sandbox for safety

        if env == 'production':
            return 'https://api.kopokopo.com'       # real money!
        return 'https://sandbox.kopokopo.com'       # testing environment


    # ──────────────────────────────────────────────────────────────────────────
    # METHOD 2 — BUILD HEADERS FOR KOPO KOPO REQUESTS
    # ──────────────────────────────────────────────────────────────────────────
    # Every API call to Kopo Kopo needs these HTTP headers:
    #   Content-Type  → tells them we're sending JSON
    #   Accept        → tells them we want JSON back
    #   Authorization → our Bearer token (proves we're authenticated)
    #   User-Agent    → identifies our app (Kopo Kopo logs this)
    # ──────────────────────────────────────────────────────────────────────────
    @classmethod
    def _headers(cls):
        return {
            'Content-Type':  'application/json',
            'Accept':        'application/json',

            # get_token() returns a valid token (from cache or fresh)
            # We prefix with "Bearer " — standard OAuth2 format
            'Authorization': f'Bearer {cls.get_token()}',

            'User-Agent':    'StockEdgePOS/1.0 KopoKopoIntegration',
        }


    # ──────────────────────────────────────────────────────────────────────────
    # METHOD 3 — GET OR REFRESH THE ACCESS TOKEN
    # ──────────────────────────────────────────────────────────────────────────
    # Kopo Kopo uses OAuth2 — every request needs a fresh-ish token.
    # Tokens last 3600 seconds (1 hour) before expiring.
    #
    # Naive approach: fetch a new token on every API call
    #   → SLOW (extra HTTP round-trip)
    #   → WASTEFUL (unnecessary Kopo Kopo API calls)
    #
    # Smart approach (what we do): CACHE the token until it's about to expire
    #   → We keep it in memory for 3300 seconds (55 mins)
    #   → Only fetch a new one when it's close to expiring
    # ──────────────────────────────────────────────────────────────────────────
    @classmethod
    def get_token(cls):
        """
        Get OAuth2 access token.
        Cached for 55 minutes (token expires in 60).
        """
        # Current timestamp in seconds (float) — used for expiry comparison
        now = time.time()

        # CHECK: do we have a token AND is it still valid?
        # If yes, return the cached one (no API call needed)
        if cls._token and now < cls._token_expiry:
            return cls._token

        # CACHE MISS — we need to fetch a fresh token from Kopo Kopo
        url = f'{cls._base_url()}/oauth/token'

        # This is the OAuth2 "client_credentials" flow:
        # We prove who we are with a client_id and client_secret,
        # and Kopo Kopo gives us a token in return.
        payload = {
            'client_id':     current_app.config['KOPOKOPO_CLIENT_ID'],
            'client_secret': current_app.config['KOPOKOPO_CLIENT_SECRET'],
            'grant_type':    'client_credentials',
        }

        # Note: this endpoint expects x-www-form-urlencoded (NOT json!)
        # That's why we use `data=payload` in the request (not `json=payload`)
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent':   'StockEdgePOS/1.0 KopoKopoIntegration',
        }

        # Make the HTTP POST to get the token
        response = requests.post(url, data=payload, headers=headers, timeout=30)

        # If status code is 4xx or 5xx, this raises an exception
        # (Our caller will handle it via try/except)
        response.raise_for_status()

        # Parse the JSON response — looks like:
        # { "access_token": "abc123...", "token_type": "Bearer", "expires_in": 3600, ... }
        data = response.json()

        # Save to cache
        cls._token        = data['access_token']
        cls._token_expiry = now + 3300  # 55 mins — refresh 5 mins early for safety

        return cls._token


    # ──────────────────────────────────────────────────────────────────────────
    # METHOD 4 — INITIATE STK PUSH (the main event!)
    # ──────────────────────────────────────────────────────────────────────────
    # STK Push = "Sim Toolkit Push" — the prompt that pops up on the customer's
    # M-Pesa phone asking them to enter their PIN to approve the payment.
    #
    # FLOW:
    #   1. We POST to Kopo Kopo with customer phone + amount
    #   2. Kopo Kopo tells Safaricom to push the prompt to the phone
    #   3. Customer enters PIN on their phone
    #   4. Kopo Kopo calls our callback URL with the result (success/fail)
    #
    # This method only does step 1 — the callback is handled elsewhere.
    # ──────────────────────────────────────────────────────────────────────────
    @classmethod
    def initiate_stk_push(cls, phone_number, amount, transaction_id):
        """
        Initiate M-Pesa STK Push to customer phone.
        Returns the payment location URL from Kopo Kopo.
        """
        # The endpoint for incoming payments (STK push)
        url = f'{cls._base_url()}/api/v1/incoming_payments'

        # Build the payload exactly as Kopo Kopo expects it
        data = {
            # Tells KK this is an STK push (not a card/paybill payment)
            'payment_channel': 'M-PESA STK Push',

            # Your till number — from Kopo Kopo dashboard
            'till_number': current_app.config['KOPOKOPO_TILL_NUMBER'],

            # Who's paying — we normalize the phone first
            'subscriber': {
                'phone_number': cls._format_phone(phone_number),
            },

            # How much they're paying (must be integer — no decimals for KES)
            'amount': {
                'currency': 'KES',
                'value':    int(amount),
            },

            # METADATA is KEY — this is how we link the payment back to OUR sale.
            # Kopo Kopo will echo this back in the callback, so we know which
            # sale to update when the payment succeeds.
            'metadata': {
                'transaction_id': transaction_id,
            },

            # Where Kopo Kopo should notify us when the payment is done
            '_links': {
                'callback_url': current_app.config['KOPOKOPO_CALLBACK_URL'],
            }
        }

        # Send the request — note we use cls._headers() which auto-adds the token
        response = requests.post(url, json=data, headers=cls._headers(), timeout=30)

        # SUCCESS CASE — Kopo Kopo returns HTTP 201 (Created)
        # The payment_id is in the "Location" header, not the body!
        # Example Location: https://sandbox.kopokopo.com/api/v1/incoming_payments/abc-123
        if response.status_code == 201:
            location   = response.headers.get('Location', '')
            # Split by "/" and grab the last part — that's our payment_id
            payment_id = location.split('/')[-1]

            return {
                'success':    True,
                'payment_id': payment_id,   # We'll use this to check status later
                'location':   location,
            }

        # FAILURE CASE — try to extract a useful error message
        try:
            error   = response.json()
            message = error.get('error_message', 'STK Push failed')
        except Exception:
            # If response isn't valid JSON, use a generic message with status code
            message = f'STK Push failed with status {response.status_code}'

        return {'success': False, 'message': message}


    # ──────────────────────────────────────────────────────────────────────────
    # METHOD 5 — CHECK PAYMENT STATUS (polling)
    # ──────────────────────────────────────────────────────────────────────────
    # Sometimes we want to manually check the status of a payment — e.g. when
    # the frontend asks "did the customer pay yet?" before the callback arrives.
    #
    # Status values:
    #   Pending  → customer hasn't entered PIN yet (or still processing)
    #   Success  → payment completed successfully
    #   Failed   → customer cancelled, wrong PIN, insufficient funds, etc
    # ──────────────────────────────────────────────────────────────────────────
    @classmethod
    def check_payment_status(cls, payment_id):
        """
        Poll the status of a payment from Kopo Kopo.
        Status: Pending | Success | Failed
        """
        # Build the URL — we include the payment_id from initiate_stk_push
        url      = f'{cls._base_url()}/api/v1/incoming_payments/{payment_id}'
        response = requests.get(url, headers=cls._headers(), timeout=30)

        # response.ok is True for any 2xx status code
        if not response.ok:
            return {'status': 'error', 'message': 'Could not check payment status'}

        # Dig into the nested JSON structure Kopo Kopo returns
        data       = response.json()
        attributes = data.get('data', {}).get('attributes', {})  # safe nested access
        status     = attributes.get('status', 'Pending')
        event      = attributes.get('event', {})

        # Resource may be null when payment is still pending — handle that
        resource   = event.get('resource') or {}

        # Return only the fields we care about (keep it simple for frontend)
        return {
            'status':    status,
            'reference': resource.get('reference'),            # M-Pesa code e.g. OJM6Q1W84K
            'amount':    resource.get('amount'),
            'phone':     resource.get('sender_phone_number'),
            'errors':    event.get('errors'),                  # error message if failed
        }


    # ──────────────────────────────────────────────────────────────────────────
    # METHOD 6 — VERIFY WEBHOOK SIGNATURE (SECURITY!)
    # ──────────────────────────────────────────────────────────────────────────
    # When Kopo Kopo calls our callback URL, we MUST verify it actually came
    # from Kopo Kopo — otherwise a hacker could fake callbacks saying "payment
    # was successful!" and get free products.
    #
    # HOW IT WORKS:
    #   1. Kopo Kopo takes the raw request body
    #   2. They compute HMAC-SHA256(body, our_api_key) → produces a signature
    #   3. They send this signature in the X-KopoKopo-Signature header
    #   4. We recompute the signature ourselves using the same API key
    #   5. If they match → request is genuine
    #   6. If they don't match → reject it (possible attacker!)
    # ──────────────────────────────────────────────────────────────────────────
    @classmethod
    def verify_webhook(cls, payload_bytes, signature):
        """
        Verify that the webhook came from Kopo Kopo.
        Uses HMAC-SHA256 with your API key.
        """
        api_key = current_app.config.get('KOPOKOPO_API_KEY', '')

        # Compute what the signature SHOULD be if Kopo Kopo sent this
        expected = hmac.new(
            api_key.encode('utf-8'),   # Our secret key
            payload_bytes,              # The exact raw body they sent
            hashlib.sha256              # The algorithm (must match theirs)
        ).hexdigest()                   # Convert to hex string

        # Compare — but NOT with == operator!
        # compare_digest is a special comparison that prevents "timing attacks"
        # (where an attacker measures response time to guess the signature).
        # Always use this for comparing cryptographic signatures.
        return hmac.compare_digest(expected, signature)


    # ──────────────────────────────────────────────────────────────────────────
    # METHOD 7 — PHONE NUMBER NORMALIZER
    # ──────────────────────────────────────────────────────────────────────────
    # Kenyan phone numbers come in many formats:
    #   0712345678     (local)
    #   +254712345678  (international)
    #   254712345678   (international, no +)
    #   712345678      (just the subscriber part)
    #
    # Kopo Kopo expects the +254 format. This method handles all variations
    # so the cashier can enter whatever format and it just works.
    # ──────────────────────────────────────────────────────────────────────────
    @staticmethod  # static = no class/instance needed, pure utility function
    def _format_phone(phone):
        """
        Normalize phone number to +254 format.
        Handles: 07xx, 7xx, 254xx, +254xx
        """
        # Clean up whitespace and convert to string (in case it's a number)
        phone = str(phone).strip().replace(' ', '')

        # Already correct format — return as-is
        if phone.startswith('+254'):
            return phone

        # International without + — add the +
        if phone.startswith('254'):
            return f'+{phone}'

        # Local format (starts with 0) — replace 0 with +254
        if phone.startswith('0'):
            return f'+254{phone[1:]}'   # [1:] strips the leading 0

        # Subscriber part only (starts with 7 or 1 for Safaricom/Airtel)
        if phone.startswith('7') or phone.startswith('1'):
            return f'+254{phone}'

        # Fallback — return as-is and let Kopo Kopo reject if invalid
        return phone
    
    @classmethod
    def subscribe_webhook(cls, event_type, scope, scope_reference):
        """
        Create a webhook subscription.
        Call this ONCE after deployment to register for events.
        """
        url = f'{cls._base_url()}/api/v1/webhook_subscriptions'
        data = {
            'event_type':      event_type,   # e.g. "buygoods_transaction_received"
            'url':             f"{current_app.config['KOPOKOPO_CALLBACK_URL'].replace('/callback', '')}/webhook",
            'scope':           scope,         # "till" or "company"
            'scope_reference': scope_reference,  # till number if scope=till
        }
        
        response = requests.post(url, json=data, headers=cls._headers(), timeout=30)
        return response.status_code == 201, response.text