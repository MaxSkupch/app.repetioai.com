import ulid

from datetime                       import datetime, timezone
from dotenv                         import load_dotenv
from flask_login                    import UserMixin
from os                             import getenv
from sqlalchemy.dialects.postgresql import JSON
from werkzeug.security              import generate_password_hash, check_password_hash

from app.extensions                 import db



load_dotenv()
free_trail_token_allowance = int(getenv('CONFIG_DB_FREE_TRAIL_TOKEN_ALLOWANCE', 100))


class User(UserMixin, db.Model):
    id                  = db.Column(db.Integer, primary_key=True) # Primary ID, not used for anything outside the db
    public_reference_id = db.Column(db.String(26), unique=True, nullable=False) # Used for the Lemon Squeezy customer_id and all other future integrations

    first_name          = db.Column(db.String(60), nullable=True) # Not realy used for anything. Only there so I may be able to send custom Email in the future
    last_name           = db.Column(db.String(60), nullable=True) # Not realy used for anything. Only there so I may be able to send custom Email in the future 
    email               = db.Column(db.String(150), unique=True, nullable=False, index=True) # Secondary ID. Used for all Auth

    timezone            = db.Column(db.String(50), default='UTC') # Used for 
    created_at          = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)) # Just nice to have
    is_new              = db.Column(db.Boolean, default=True) # Only used to differanciate accounts that have a verified email and logged in from those that have not
    role                = db.Column(db.String(10), default='user') #user, tester, unlimited 

    account_active      = db.Column(db.Boolean, default=False) # TODO Change default # Used to block the login for Users

    token_balance       = db.Column(db.Integer, nullable=False, default=free_trail_token_allowance) # TODO Maybe redo this?
    last_balance_reset  = db.Column(db.DateTime(timezone=True), nullable=True)
    subscription        = db.relationship('UserSubscription', back_populates='user', cascade='all, delete-orphan')
    requests            = db.relationship('Request', back_populates='user', cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Subscription(db.Model):
    id                      = db.Column(db.Integer, primary_key=True) #  Primary ID, not used for anything outside the db
    public_reference_id     = db.Column(db.Integer, nullable=True) # Used for the Lemon Squeezy variant_id and all other future integrations
    display_name            = db.Column(db.String(50), nullable=False) # Name of the Subscription show to the User
    monthly_cost            = db.Column(db.Integer, nullable=False) # Monthly cost of the Subscription in USD cent
    included_tokens         = db.Column(db.Integer, nullable=False) # Amount of tokens the Subscriptions includes per month

    user_subscriptions = db.relationship('UserSubscription', back_populates='subscription', cascade='all, delete-orphan')

class UserSubscription(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)  # Primary ID of the User Subscription. User can have multiple ones but only one active
    user_id             = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # User the Subscription belongs to
    subscription_id     = db.Column(db.Integer, db.ForeignKey('subscription.id'), nullable=False) # Subscription the User made

    start_time          = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)) # Just nice to have
    end_time            = db.Column(db.DateTime(timezone=True), nullable=True) # Filled in once the subscription ended or is planed on on ending, otherwise null
    active              = db.Column(db.Boolean, default=True) # One user can have one active subscription

    status              = db.Column(db.String(10), nullable=False)
    last_payment_time   = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    next_reset_time     = db.Column(db.DateTime(timezone=True), nullable=True)

    user                = db.relationship('User', back_populates='subscription')
    subscription        = db.relationship('Subscription', back_populates='user_subscriptions')


class Request(db.Model):    
    id                      = db.Column(db.String(26), primary_key=True, default=lambda: str(ulid.new())) # Primary key of the Request
    user_id                 = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # User that the request belongs to 

    tokens_used_total       = db.Column(db.Integer, nullable=True) # General Info
    tokens_used_prompts     = db.Column(db.Integer, nullable=True) # General Info
    tokens_used_responses   = db.Column(db.Integer, nullable=True) # General Info
    prompt_amount           = db.Column(db.Integer, nullable=True) # General Info

    display_text            = db.Column(db.String, nullable=True) # Description the user is shown to know what the data is about
    created_at              = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)) # Date the DB Entry is made (rougly equals date of completion of the Request and treatet as such)
    data                    = db.Column(JSON, nullable=False) #Actual Results Data of the request # {'type': 'variable_sent', 'version': '0', 'data':{...}}

    user                    = db.relationship('User', back_populates='requests')

