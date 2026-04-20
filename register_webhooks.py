# register_webhooks.py
from app import app
from services.kopokopo import KopoKopoService

with app.app_context():
    till_number = app.config['KOPOKOPO_TILL_NUMBER']

    events_to_subscribe = [
        'buygoods_transaction_received',
        'buygoods_transaction_reversed',
    ]
    
    for event_type in events_to_subscribe:
        success, response = KopoKopoService.subscribe_webhook(
            event_type=event_type,
            scope='till',
            scope_reference=till_number,
        )
        
        if success:
            print(f"✅ Subscribed to {event_type}")
        else:
            print(f"❌ Failed {event_type}: {response}")