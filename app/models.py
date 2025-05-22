import ulid

from datetime                       import datetime, timezone
from dotenv                         import load_dotenv
from flask_login                    import UserMixin
from os                             import getenv
from sqlalchemy.dialects.postgresql import JSON, BIGINT

from werkzeug.security              import generate_password_hash, check_password_hash

from app.extensions                 import db



load_dotenv()

class User(UserMixin, db.Model):
    id                      = db.Column(db.Integer, primary_key=True) # Primary ID, not used for anything outside the db
    public_reference_id     = db.Column(db.String(26), unique=True, nullable=False) # Used for the Lemon Squeezy customer_id and all other future integrations

    first_name              = db.Column(db.String(60), nullable=True) # Not realy used for anything. Only there so I may be able to send custom Email in the future
    last_name               = db.Column(db.String(60), nullable=True) # Not realy used for anything. Only there so I may be able to send custom Email in the future 
    email                   = db.Column(db.String(150), unique=True, nullable=False, index=True) # Secondary ID. Used for all Auth

    timezone                = db.Column(db.String(50), default='UTC') # Used for 
    created_at              = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)) # Just nice to have
    first_login_completed   = db.Column(db.Boolean, default=False) # Only used to differanciate accounts that have a verified email and logged in from those that have not, also to allot trail tokens
    role                    = db.Column(db.String(10), default='user') #user, tester, unlimited 

    account_active          = db.Column(db.Boolean, default=False) # TODO Change default # Used to block the login for Users

    token_balance           = db.Column(BIGINT, nullable=False, default=0)
    
    requests                = db.relationship('Request', back_populates='user', cascade='all, delete-orphan')
    token_transactions      = db.relationship('TokenTransaction', back_populates='user', cascade='all, delete-orphan')


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class TokenTransaction(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount              = db.Column(BIGINT, nullable=False)  # Amount added (or subtracted, if negative)
    transaction_date    = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    description         = db.Column(db.String(255), nullable=True)  # E.g., "Top-up", "Adjustment", etc.
    
    user                = db.relationship('User', back_populates='token_transactions') 


class Request(db.Model):    
    id                      = db.Column(db.String(26), primary_key=True, default=lambda: str(ulid.new())) # Primary key of the Request
    user_id                 = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # User that the request belongs to 

    tokens_used_total       = db.Column(BIGINT, nullable=True) # General Info
    tokens_used_prompts     = db.Column(BIGINT, nullable=True) # General Info
    tokens_used_responses   = db.Column(BIGINT, nullable=True) # General Info
    prompt_amount           = db.Column(db.Integer, nullable=True) # General Info

    display_text            = db.Column(db.String, nullable=True) # Description the user is shown to know what the data is about
    created_at              = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)) # Date the DB Entry is made (rougly equals date of completion of the Request and treatet as such)
    data                    = db.Column(JSON, nullable=False) #Actual Results Data of the request # {'type': 'variable_sent', 'version': '0', 'data':{...}}

    user                    = db.relationship('User', back_populates='requests')



"""
Request.data V1:

Request.data V2...
"""
