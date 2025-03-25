import hashlib
import hmac
import re

from datetime       import datetime, timezone
from flask          import abort, request
from flask_login    import current_user
from urllib.parse   import quote

from app            import db
from app.models     import User, UserSubscription
from app.values     import lemonsqueezy_webhook_secret, lemonsqueezy_store_id, LEMONSQUEEZY_STORE_DOMAIN


### Helper Functions

def ls_variant_checkout(user_email, reference_id, variant_id):
    encoded_email = quote(user_email)
    #TODO Probably use Hosted domain
    return f'https://{LEMONSQUEEZY_STORE_DOMAIN}/checkout/buy/{variant_id}?checkout[email]={encoded_email}&checkout[name]={current_user.first_name} {current_user.last_name}&checkout[custom][reference_id]={reference_id}'
    return f"{ls_customer_portal_url}?prefilled_email={encoded_email}"

def is_regex_valid_email(email: str):
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(email_regex, email)


### Main functions   

def register_payments_routes(app):


    @app.route('/integrations/ls-webhook', methods=['POST'])
    def integrations_stripe_webhook():
        event_name = request.headers.get('X-Event-Name')
        signature = request.headers.get('X-Signature')
        payload = request.get_data()
        payload_json = request.get_json()

        if lemonsqueezy_webhook_secret is None:
            print("Error: LEMONSQUEEZY_WEBHOOK_SECRET environment variable is not set")
            abort(500, 'Server configuration error')
        digest = hmac.new(lemonsqueezy_webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(digest, signature):
            print("Invalid signature")
            abort(400, 'Invalid signature.')

        a = payload_json['data']['attributes']
        if a['test_mode'] == True: print(f'Event name: {event_name}\n\nPayload:\n{payload_json}')

        if   event_name == 'subscription_created': # Use for keeping status uptodate
            
            #create new UserSubscription
            status = a['status'] 

            try:
                user = User.query.filter_by(public_client_reference_id=a['customer_id']).first()


                new_subscription = UserSubscription(
                    user_id=user.id,
                    subscription_id='subscription_type',  # Assuming you have a way to get subscription ID
                    status=status,
                        # 'on_trial'    Use with limited amount of tokens
                        # 'active'      Regularly use Tokens
                        # 'paused'      maybe not needed
                        # 'past_due'    Deactivate Option to use
                        # 'cancelled'   Regularly use Tokens (maybe add a small banner saying "subscription ends on")
                        # 'expired'     Deactivate Option to use
                    payment_time=datetime.now(timezone.utc)  # Set the payment time to now
                )
                db.session.add(new_subscription)
                db.session.commit()
                

            except:
                print(f"Error: User with email {a['customer_id']} not found")



            product_id = a['product_id']
            variant_id = a['variant_id'] 


        elif event_name == 'subscription_updated': # Use for keeping status uptodate
            print(' ')


        elif event_name == 'subscription_payment_success': # Use for keeping tokens uptodate
            if not a['store_id'] == lemonsqueezy_store_id: abort(400, 'Wrong store ID')
            subscription_id = a['subscription_id'] 
            customer_id     = a['customer_id']
            billing_reason  = a['billing_reason'] 
            status          = a['status'] 
            'pending'
            'paid'
            'void'
            'refunded'

        else:  abort(400, f'Unhandeled event: {event_name}')

        return '', 200






