from flask import Flask, render_template, request, redirect, url_for, abort, session, stream_with_context, jsonify, Response, flash, render_template_string, send_file, after_this_request
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from flask_mail import Mail, Message

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy import func
from flask_session import Session
import tempfile
import valkey
import redis

import json
import csv
import random
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import requests
import os
import re
import ulid
from itertools import product
from urllib.parse import quote, quote_plus, unquote_plus
from itsdangerous import URLSafeTimedSerializer

import hashlib
import hmac

from dotenv import load_dotenv

import stripe
import tiktoken

import openai
from openai import AsyncOpenAI
import asyncio

from altcha import ChallengeOptions, create_challenge, verify_solution, verify_server_signature, verify_fields_hash


### Configure & Initiate 

## Load Envirement Variables
load_dotenv()




## Flask App

# Initiate Flask
app = Flask(__name__)

# Configure Flask
app.config['SECRET_KEY'] = os.getenv('FLASK_SESSION_KEY')


# Configure DB
app.config['SQLALCHEMY_DATABASE_URI']           = os.getenv('POSTGRES_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']    = False



# Flask-Session configuration to use Valkey / Redis
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_REDIS'] = redis.from_url(os.getenv('VALKEY_URL'))

# Global Valkey / Redis instence
vk = redis.from_url(os.getenv('VALKEY_URL'))

# Configure Flask Mail
app.config['MAIL_SERVER']   = 'smtp.ionos.de'
app.config['MAIL_PORT']     = 465
app.config['MAIL_USE_TLS']  = False
app.config['MAIL_USE_SSL']  = True
app.config['MAIL_USERNAME'] = 'no-reply@repetioai.com'
app.config['MAIL_PASSWORD'] = os.getenv('SMTP_MAIL_SERVER_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('Repetio AI', 'no-reply@repetioai.com')
app.config['MAIL_DEBUG']    = False

# Initiate App Extensions
db = SQLAlchemy(app)
server_session = Session(app)
mail = Mail(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth_login'




## Other 


# Initiate Lemon_Squeezy

lemonsqueezy_webhook_secret = os.getenv('LEMONSQUEEZY_WEBHOOK_SECRET')
lemonsqueezy_store_id       = os.getenv('LEMONSQUEEZY_STORE_ID')
LEMONSQUEEZY_STORE_DOMAIN   = os.getenv('LEMONSQUEEZY_STORE_DOMAIN')

 

# Initiate OpenAI API
openai_model_name                   = os.getenv('OPENAI_MODEL_NAME')
openai_model_limit_context_window   = int(os.getenv('OPENAI_MODEL_LIMIT_CONTEXT_WINDOW'))
openai_model_limit_tpm              = int(os.getenv('OPENAI_MODEL_LIMIT_TPM'))
openai_model_limit_rpm              = int(os.getenv('OPENAI_MODEL_LIMIT_RPM'))
client                              = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Captcha 
altcha_hmac_key = os.getenv('ALTCHA_HMAC_KEY', 'ihbfsofb7676f7s')

# Configure Auth Config
free_trail_token_allowance          = int(os.getenv('CONFIG_DB_FREE_TRAIL_TOKEN_ALLOWANCE', 0))
url_serializer                      = URLSafeTimedSerializer(os.getenv('URL_SERIALIZER_SECRET_KEY', 'dsfafa7v8dsvd8vs8vgs8dg'))








### Define DB Schema / Classes

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
    id              = db.Column(db.Integer, primary_key=True)  # Primary ID of the User Subscription. User can have multiple ones but only one active
    user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # User the Subscription belongs to
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'), nullable=False) # Subscription the User made

    created_at      = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)) # Just nice to have
    ended_at        = db.Column(db.DateTime(timezone=True), nullable=True) # Filled in once the subscription ended, otherwise null
    active          = db.Column(db.Boolean, default=True) # One user can have one active subscription

    status          = db.Column(db.String(10), nullable=False)
    payment_time    = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    reset_time      = db.Column(db.DateTime(timezone=True), nullable=True)

    user            = db.relationship('User', back_populates='subscription')
    subscription    = db.relationship('Subscription', back_populates='user_subscriptions')


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



@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))





with app.app_context():
    db.create_all() # Ensure database schema exists







### Functions


def ls_variant_checkout(user_email, reference_id, variant_id):
    encoded_email = quote(user_email)
    #TODO Probably use Hosted domain
    return f'https://{LEMONSQUEEZY_STORE_DOMAIN}/checkout/buy/{variant_id}?checkout[email]={encoded_email}&checkout[name]={current_user.first_name} {current_user.last_name}&checkout[custom][reference_id]={reference_id}'
    return f"{ls_customer_portal_url}?prefilled_email={encoded_email}"

def is_regex_valid_email(email: str):
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    return re.match(email_regex, email)

def create_altcha_challenge_json():
        try:
            challenge = create_challenge(ChallengeOptions(hmac_key=altcha_hmac_key, max_number=100000))
            return json.dumps(challenge.__dict__)
        except Exception as e:
            return json.dumps({"error": f"Failed to create challenge: {str(e)}"})
        
def altcha_challange_verified(altcha_input):
    verified = False
    if altcha_input:
        try: verified, err = verify_solution(altcha_input, altcha_hmac_key, check_expires=True)
        except Exception as e: 
            print(e)
            verified = False
    return verified

# Manipulate Auto Save Inputs
def get_auto_save_inputs(n: int) -> str:
    if 'auto_save_inputs' in session and n in session['auto_save_inputs']:
        return session['auto_save_inputs'][n]
    return ''

def set_auto_save_inputs(n: int, content: str):
    if not 'auto_save_inputs' in session:
        session['auto_save_inputs'] = {}
    session['auto_save_inputs'][n] = content

def reset_auto_save_inputs():
    session['auto_save_inputs'] = {}

# Manage Openai Tokens
def tiktoken_count_tokens(content: str) -> int:
    encoding = tiktoken.encoding_for_model(openai_model_name)
    token_count = len(encoding.encode(content))
    return token_count

def token_count_to_string(count: int):
    if count < 10_000:      return str(count)
    return re.sub(r"(?<=\d)(?=(\d{3})+$)", ".", str(count))

def token_count_to_short_string(n):
        if n < 0:   negative = True
        else:       negative = False

        n = abs(n)

        if n >= 1_000_000_000:  
            n = n / 1_000_000_000
            suffixes = 'B'
        if n >= 1_000_000:      
            n = n / 1_000_000
            suffixes = 'M'
        if n >= 1_000:          
            n = n / 1_000
            suffixes = 'K'
        if n >= 0:              
            n = n

        n = str(round(n, 2))[0:4]
        if len(n) > 1 and n[-1] == '.': n = n[0:-1]

        return f'{n}{suffixes}'

def time_delta_to_string(time_delta):
    if   time_delta.days > 0:               
        time_string = f'{time_delta.days}'
        unit_string = 'days'
    elif time_delta.seconds >= 3600:
        time_string = f'{time_delta.seconds // 3600}'
        unit_string = 'hours'
    elif time_delta.seconds >= 60:
        time_string = f'{time_delta.seconds // 60}'
        unit_string = 'minutes'
    else:                                   
        time_string = f'<1'
        unit_string = 'minute'
    return time_string, unit_string


## Main Functions for Prompt generation
def process_var_prompt_base_input(input_text: str) -> tuple[list[str], list[str]]:
    pattern = re.compile(r'{{(.*?)}}')
    segments = pattern.split(input_text)

    variable_names = []
    text_segments = []
    
    for i, segment in enumerate(segments):
        if i % 2 == 0: text_segments.append(segment)
        else: variable_names.append(segment.strip())

    for i, variable in enumerate(variable_names):
        if variable == '': variable_names[i] = f'Variable {i+1}'
    
    return text_segments, variable_names # List of each Textsegment between and before Variable places, Variable Name

def create_index_values_prompt_list_from_input(text_segments: list, variable_values: list) -> list:

    if variable_values == []: return [[0,['NO VARIABLES'], text_segments[0]]]

    variable_value_combinations = list(product(*variable_values))

    index_values_prompt_list = []
    i = 0
    for values in variable_value_combinations:
        prompt = ""
        
        for j in range(len(values)): 
            prompt += f'{text_segments[j]}{values[j]}'

        if len(text_segments) > len(values):
            prompt += text_segments[len(values)] 
            
        index_values_prompt_list.append([i, list(values), prompt])
        i += 1

    return index_values_prompt_list


def count_total_tokens_in_prompts_list(prompts_list: list) -> int:
    total = 0
    for prompt in prompts_list:
        total += tiktoken_count_tokens(prompt) 

    return total

async def process_var_prompt(index_values_prompt_list: list):

    async def process_single_prompt(index_values_prompt_list):

        index           = index_values_prompt_list[0]
        values          = index_values_prompt_list[1]
        prompt          = index_values_prompt_list[2]
        prompt_tokens   = tiktoken_count_tokens(prompt)

        if (datetime.now().timestamp() - float(vk.get('global:limits:openai:reset_time').decode('utf-8'))) > 60:
            vk.set('global:limits:openai:tpm', 0)
            vk.set('global:limits:openai:rpm', 0)
            vk.set('global:limits:openai:reset_time', datetime.now().timestamp())

        while True:
            if ((prompt_tokens * 100) + int(vk.get('global:limits:openai:tpm').decode('utf-8')) + 1000 >= openai_model_limit_tpm):
                time_utill_reset = int(datetime.now().timestamp() - float(vk.get('global:limits:openai:reset_time').decode('utf-8')))
                await asyncio.sleep(time_utill_reset)
            elif (int(vk.get('global:limits:openai:rpm').decode('utf-8')) + 3 >= openai_model_limit_rpm):    
                time_utill_reset = int(datetime.now().timestamp() - float(vk.get('global:limits:openai:reset_time').decode('utf-8')))
                await asyncio.sleep(time_utill_reset)
            else: 
                break

        try:
            response = await client.chat.completions.create(
                model= openai_model_name,
                messages=[{"role": "user", "content": prompt}],
            )

            prompt_response = response.choices[0].message.content
            
            # Update user Request Info
            vk.incrby(f'global:user({current_user.id}):request_counts:tokens_used_total',      response.usage.total_tokens)
            vk.incrby(f'global:user({current_user.id}):request_counts:tokens_used_prompts',    response.usage.prompt_tokens)
            vk.incrby(f'global:user({current_user.id}):request_counts:tokens_used_response',   response.usage.completion_tokens)
            vk.incrby(f'global:user({current_user.id}):request_counts:prompts_completed',      1)
            
            # Update shared AI Limits
            vk.incrby('global:limits:openai:tpm', response.usage.total_tokens)
            vk.incrby('global:limits:openai:rpm', 1)

            # Update Tokens used by User
            # TODO update the amount of tokens used by the user in the db (since this is async it wont affect user to much. later cash this or do some other method to reduce db )
            
        except: 
            print('API CALL ERROR')
            prompt_response = 'ERROR'

        return [index, values, prompt, prompt_response]
    

    vk.setnx('global:limits:openai:tpm', 0)
    vk.setnx('global:limits:openai:rpm', 0)
    vk.setnx('global:limits:openai:reset_time', datetime.now().timestamp())

    vk.set(f'global:user({current_user.id}):request_counts:tokens_used_total',      0)
    vk.set(f'global:user({current_user.id}):request_counts:tokens_used_prompts',    0)
    vk.set(f'global:user({current_user.id}):request_counts:tokens_used_response',   0)
    vk.set(f'global:user({current_user.id}):request_counts:prompts_completed',      0)
    vk.set(f'global:user({current_user.id}):request_counts:prompts_amount',         len(index_values_prompt_list))
    vk.set(f'global:user({current_user.id}):request_counts:start_progress_stream',  1)
    vk.set(f'global:user({current_user.id}):request_counts:db_tokens_used_updated', 0)


    tasks                       = [process_single_prompt(index_values_prompt) for index_values_prompt in index_values_prompt_list]
    values_prompt_response_list = await asyncio.gather(*tasks)

    tokens_used_total       = int(vk.get(f'global:user({current_user.id}):request_counts:tokens_used_total'))
    tokens_used_prompts     = int(vk.get(f'global:user({current_user.id}):request_counts:tokens_used_prompts'))
    tokens_used_responses   = int(vk.get(f'global:user({current_user.id}):request_counts:tokens_used_response'))

    try:
        # TODO update db here
        vk.set(f'global:user({current_user.id}):request_counts:db_tokens_used_updated',  1)

        vk.delete(f'global:user({current_user.id}):request_counts:tokens_used_total')
        vk.delete(f'global:user({current_user.id}):request_counts:tokens_used_prompts')
        vk.delete(f'global:user({current_user.id}):request_counts:tokens_used_response')
        vk.delete(f'global:user({current_user.id}):request_counts:prompts_completed')
        vk.delete(f'global:user({current_user.id}):request_counts:prompts_amount')
    except Exception as e: print(f'DB Tokens Used update and VK reset failed:\n\n{e}')

    values_prompt_response_list.sort(key=lambda x: x[0])
    for entry in values_prompt_response_list: entry.pop(0)

    return values_prompt_response_list, tokens_used_total, tokens_used_prompts, tokens_used_responses






### Routes 

## Dashboard(s)

@app.route('/')
@login_required
def dash_base():
    current_window = session.get('current_window', 'dash_compose')
    return render_template(
        'dash/base.html',
        current_window = current_window
    )

# Dashboard Windows (served via HTMX)

@app.route('/dash/window/tokens')
@login_required
def dash_tokens():
    session['current_window'] = 'dash_tokens'
    return render_template(
        'dash/windows/tokens.html',
        window_title = 'Tokens & Plans'
    )

@app.route('/dash/window/compose')
@login_required
def dash_compose():
    session['current_window'] = 'dash_compose'
    return render_template(
        'dash/windows/compose.html',
        window_title = 'Compose',
        current_compose_step = session.get('current_compose_step', 0)
    )

@app.route('/dash/window/compose/new')
@login_required
def dash_compose_new():
    session['current_compose_step'] = 0
    session['current_window'] = 'dash_compose'
    return render_template(
        'dash/windows/compose.html',
        window_title = 'Compose',
        current_compose_step = 0,
    )

@app.route('/dash/window/history')
@login_required
def dash_history():
    session['current_window'] = 'dash_history'
    return render_template(
        'dash/windows/history.html',
        window_title = 'History'
    )

@app.route('/dash/window/help')
@login_required
def dash_help():
    session['current_window'] = 'dash_help'
    return render_template(
        'dash/windows/help.html', 
        window_title = 'Help'
    )

@app.route('/dash/window/account')
@login_required
def dash_account():
    session['current_window'] = 'dash_account'
    return render_template(
        'dash/windows/account.html',
        window_title        = 'Account',
        first_name          = current_user.first_name,
        last_name           = current_user.last_name,
        email               = current_user.email,
        url_encoded_email   = quote(current_user.email),
        ls_customer_portal_url = f'https://{LEMONSQUEEZY_STORE_DOMAIN}'
    )






### Components (served via HTMX)

## Base Components

@app.route('/component/token_count')
@login_required
def comp_token_count():
    tokens_left     = token_count_to_short_string(current_user.token_balance)
    token_allowance = token_count_to_short_string(UserSubscription.query.filter_by(user_id=current_user.id, active=True).first().subscription.included_tokens) 
    return f'{tokens_left} / {token_allowance}'


## Token Page Components

@app.route('/component/subscription_status')
@login_required
def comp_token_page_subscription_status():
    user_subscription = UserSubscription.query.filter_by(user_id=current_user.id, active=True).first()
    
    if not user_subscription: 
        print('Failed to find active UserSubscription for Tokens Page')
        return 'Error: No active Subscription'
    
    subscription_reset_datetime = user_subscription.reset_time.astimezone(ZoneInfo(current_user.timezone))
    current_time                = datetime.now(ZoneInfo(current_user.timezone))
    subscription_reset_delta    = subscription_reset_datetime - current_time

    return render_template(
        'components/tokens/current_subscription.html',
        subscription_display_name       = user_subscription.subscription.display_name,
        subscription_reset_datetime     = subscription_reset_datetime.strftime('%Y-%m-%d %H:%M'),
        subscription_token_allowance    = token_count_to_string(user_subscription.subscription.included_tokens),
        user_token_balance              = token_count_to_string(user_subscription.user.token_balance),
        subscription_reset_delta        = time_delta_to_string(subscription_reset_delta)
    )

    


## Compose Page Components 

@app.route('/component/compose/var-prompt/input/<n>', methods=['GET', 'POST'])
@login_required
def comp_compose_var_prompt(n):
    try: n = int(n)
    except: abort(404)

    if request.method == 'GET':
        session['current_compose_step'] = n

        if n == 0: 
            return render_template(
                'components/compose/var_prompt/input_base.html',
                auto_save_text = get_auto_save_inputs(n)
            )
        
        elif 0 < n and n <= len(session['compose_data']['variable_names']): 

            return render_template(
                'components/compose/var_prompt/input_vars.html',
                auto_save_text          = get_auto_save_inputs(n),
                current_variable_name   = session['compose_data']['variable_names'][n-1],
                n                       = n,
                N                       = len(session['compose_data']['variable_names']),

            )
        
        elif n > len(session['compose_data']['variable_names']):
            return redirect(url_for('comp_compose_var_prompt_confirm'))
        
        else:
            abort(404)
    
    elif request.method == 'POST':

        if n == 0:
            
            raw_text = request.form['textarea']
            if raw_text.strip() == '': return redirect(url_for('comp_compose_var_prompt', n=0))
            set_auto_save_inputs(n, raw_text)
            text_segments, variable_names = process_var_prompt_base_input(raw_text)

            session['compose_data'] = {
                'text_segments':    text_segments,
                'variable_names':   variable_names,
                'variable_values':  [], # list of lists of variable-values
            }

        else:
            raw_text = request.form['textarea']
            set_auto_save_inputs(n, raw_text)
            var_seperation = request.form['var_seperation']

            if var_seperation == 'new_line': 
                var_inputs = raw_text.split('\n')
                while len(var_inputs) > 0 and var_inputs[-1].strip() == '': var_inputs.pop()

            elif var_seperation == 'comma':      
                var_inputs = raw_text.split(',')
                if len(var_inputs) > 0 and var_inputs[-1].strip() == '': var_inputs.pop()

            var_inputs = [var_input.strip() for var_input in var_inputs]
            if n > len(session['compose_data']['variable_values']):
                session['compose_data']['variable_values'].append(var_inputs)
            else: session['compose_data']['variable_values'][n-1] = var_inputs
  
        return redirect(url_for('comp_compose_var_prompt', n=n+1))


@app.route('/component/compose/var-prompt/confirm')
@login_required
def comp_compose_var_prompt_confirm():

    text_segments   = session['compose_data']['text_segments']
    variable_names  = session['compose_data']['variable_names']
    variable_values = session['compose_data']['variable_values']
    
    index_values_prompt_list = create_index_values_prompt_list_from_input(text_segments, variable_values)

    session['compose_data']['index_values_prompt_list'] = index_values_prompt_list

    prompts_list            = [index_values_prompt[2] for index_values_prompt in index_values_prompt_list]
    prompt_token_count      = count_total_tokens_in_prompts_list(prompts_list)
    response_token_count    = int(round(prompt_token_count * 1.874))
    total_token_count       = prompt_token_count + response_token_count   

    base_text_list = []
    for i, segment in enumerate(text_segments):
        base_text_list.append(segment)
        if i < len(variable_names): base_text_list.append(variable_names[i])

    variable_name_and_values = []
    for i, variable_name in enumerate(variable_names):
        variable_name_and_values.append([variable_name, variable_values[i]])

    base_text = []
    for i, segment in enumerate(text_segments):
        base_text.append(segment)
        if i < len(variable_names): 
            base_text.append('{{ ')
            base_text.append(variable_names[i])
            base_text.append(' }}')
    base_text = ''.join(base_text).strip()
    
    if len(base_text) <= 180:   session['compose_data']['display_text'] = base_text
    else:                       session['compose_data']['display_text'] = base_text[0:180].strip() + '...' 

    return render_template(
        'components/compose/var_prompt/confirm_input.html',
        n                       = session['current_compose_step'],
        prompt_token_count      = token_count_to_string(prompt_token_count),
        response_token_count    = token_count_to_string(response_token_count),
        total_token_count       = token_count_to_string(total_token_count),
        base_text_list          = base_text_list,
        variable_list           = variable_name_and_values,
        prompts_list            = prompts_list,
        prompts_amount          = len(prompts_list),
    )

@app.route('/component/compose/var-prompt/process/start')
@login_required
def comp_compose_var_prompt_process_start():
    return render_template('components/compose/var_prompt/process_input.html')

@app.route('/component/compose/var-prompt/process/progress_stream')
@login_required
def comp_compose_var_prompt_process_progress():

    while True: # Wait till up-to-date data is uploaded before streaming
        data_reset = int(vk.get(f'global:user({current_user.id}):request_counts:start_progress_stream') or 0)                           
        if data_reset == 1: 
            vk.set(f'global:user({current_user.id}):request_counts:start_progress_stream', 0)
            break
        time.sleep(0.2)

    def generate():
        prompt_amount           = int(vk.get(f'global:user({current_user.id}):request_counts:prompts_amount') or 0)
        prompts_completed_prev  = 0
        percentage              = 0

        while True:
            prompts_completed = int(vk.get(f'global:user({current_user.id}):request_counts:prompts_completed') or 0)
            total_tokens_used = int(vk.get(f'global:user({current_user.id}):request_counts:tokens_used_total') or 0)

            print(f'{prompts_completed}') #TODO Remove

            if prompts_completed_prev != prompts_completed:
                prompts_completed_prev = prompts_completed
                percentage = (prompts_completed / prompt_amount) * 100

                progress = json.dumps({
                    'completed': prompts_completed,
                    'total': prompt_amount,
                    'tokens': total_tokens_used,
                    'percentage': round(percentage)
                })
                yield f"data: {progress}\n\n"
            
            time.sleep(0.3)
            if percentage == 100: break
        
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/component/compose/var-prompt/process/process')
@login_required
async def comp_compose_var_prompt_process_process():     

    db_tokens_used_updated = int(vk.get(f'global:user({current_user.id}):request_counts:db_tokens_used_updated') or 1)
    if db_tokens_used_updated == 0:
        print("Update DB here")
        #TODO Update User DB tokens used

    #TODO Check if user has enoug tokens

    index_values_prompt_list    = session['compose_data']['index_values_prompt_list']
    variable_names              = session['compose_data']['variable_names']
    display_text                = session['compose_data']['display_text']

    values_prompt_response_list, tokens_used_total, tokens_used_prompts, tokens_used_responses = await process_var_prompt(index_values_prompt_list)

    results_table = []
    if variable_names:
        results_table.append(variable_names + ['Prompt', 'Response'])
        for values_prompt_response in values_prompt_response_list:
            row = []
            for value in values_prompt_response[0]: row.append(value)
            row.append(values_prompt_response[1])
            row.append(values_prompt_response[2])
            results_table.append(row)
    else:
        results_table.append(['Prompt', 'Response'])
        results_table.append([values_prompt_response_list[0][1], values_prompt_response_list[0][2]])

    request_id = str(ulid.new())
    new_request = Request(
        id                      = request_id,
        user_id                 = current_user.id,
        tokens_used_total       = tokens_used_total,
        tokens_used_prompts     = tokens_used_prompts,
        tokens_used_responses   = tokens_used_responses,
        prompt_amount           = len(index_values_prompt_list),
        display_text            = display_text,
        data                    = {
            'type':     'var_prompt',
            'version':  1,
            'data': {
                'variable_names':   variable_names,
                'results_table' :   results_table,
            }
        }
    )
    db.session.add(new_request)
    db.session.commit()

    session['current_compose_step'] = 0
    reset_auto_save_inputs() 

    preview_list = [key_prompt_response[2] for key_prompt_response in values_prompt_response_list[0:10]]
    preview_list_is_complete = True if len(preview_list) <= 10 else False
    
    return render_template(
        'components/compose/var_prompt/view_results.html',
        preview_list                = preview_list,
        preview_list_is_complete    = preview_list_is_complete,
        download_url                = url_for('download', request_id=request_id),
    )
    
# User Actions
@app.route('/component/compose/var-prompt/action/auto-save/<n>', methods=['POST'])
@login_required
def comp_compose_var_prompt_auto_save(n):
    try: n = int(n)
    except: abort(404)
    set_auto_save_inputs(n, request.form['textarea'])
    return "Saved"                    
    
@app.route('/component/compose/var-prompt/action/clear_data/<n>')
@login_required
def comp_compose_var_prompt_clear_data(n):
    try: n = int(n)
    except: abort(404)
    reset_auto_save_inputs()
    session['compose_data'] = {}
    return redirect(url_for('comp_compose_var_prompt', n=n))



@app.route('/download/<request_id>')
@login_required
def download(request_id):

    request = Request.query.filter_by(id=request_id).first()
    if not request:                             abort(404)
    if not request.user_id == current_user.id:  abort(403)

    creation_time = request.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%Y-%m-%d_%H-%M-%S')
    results_table = request.data.get('data', {}).get('results_table', [])
    if not results_table: abort(500)

    print(results_table)
    

    filename = f"{request_id}.csv"
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)

    with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        for row in results_table: writer.writerow(row)

    print('Got this far')

    try: return send_file(filepath, mimetype='text/csv', as_attachment=True, download_name=f'RepetioAI_Results_{creation_time}.csv')
    except FileNotFoundError: return {'error': 'File not found'}, 404






# History Page

@app.route('/component/history/cards_batch/<n>')
@login_required
def comp_history_cards_batch(n):
    try: n = int(n)
    except: abort(404)

    try:
        limit = 10
        offset = (n - 1) * 10
        requests_query = Request.query.filter_by(user_id=current_user.id).order_by(Request.created_at.desc()).offset(offset).limit(limit).all()

        if not requests_query: return "History is empty."
        
        if len(requests_query) < 10:    has_more = False
        else:                           has_more = True    

        requests_list = [
            {
                'id':                       req.id,
                'tokens_used_total':        req.tokens_used_total,
                'tokens_used_prompts':      req.tokens_used_prompts,
                'tokens_used_responses':    req.tokens_used_responses,
                'display_text':             req.display_text,
                'created_at_date':          req.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%Y-%m-%d'),
                'created_at_time':          req.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%H:%M'),
                'created_at_seconds':       req.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%S'), 
                'prompt_amount':            req.prompt_amount,
                'download_url':             url_for('download', request_id=req.id),
            }
            for req in requests_query
        ]

    except Exception as e: 
        print(e)
        abort(500)

    return render_template(
        'components/history/cards_batch.html',
        n = n+1,
        requests_list = requests_list,
        has_more=has_more,
    )


# Token Page

@app.route('/component/token_usage_history/cards_batch/<n>')
@login_required
def comp_token_history_cards_batch(n):
    try: n = int(n)
    except: abort(404)

    try:
        limit = 10
        offset = (n - 1) * 10
        requests_query = Request.query.filter_by(user_id=current_user.id).order_by(Request.created_at.desc()).offset(offset).limit(limit).all() # TODO Make proper DB QUERY 

        if not requests_query: return ""
        
        if len(requests_query) < 10:    has_more = False
        else:                           has_more = True    

        requests_list = [ # TODO Make proper List based on DB structure
            {
                'id':                       req.id,
                'tokens_used_total':        req.tokens_used_total,
                'tokens_used_prompts':      req.tokens_used_prompts,
                'tokens_used_responses':    req.tokens_used_responses,
                'display_text':             req.display_text,
                'created_at_date':          req.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%Y-%m-%d'),
                'created_at_time':          req.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%H:%M'),
                'created_at_seconds':       req.created_at.astimezone(ZoneInfo(current_user.timezone)).strftime('%S'), 
                'prompt_amount':            req.prompt_amount,
                'download_url':             url_for('download', request_id=req.id),
            }
            for req in requests_query
        ]

    except Exception as e: 
        print(e)
        abort(500)

    return render_template(
        'components/history/cards_batch.html',
        n = n+1,
        requests_list = requests_list,
        has_more=has_more,
    )












### Auth & Account Management

## Login / Logout

@app.route('/login', methods=['GET', 'POST'])
def auth_login():
    if request.method == 'GET':
        return render_template(
            'auth/login.html',
            challengejson = create_altcha_challenge_json(),
        )

    elif request.method == 'POST':
        email       = request.form['email'].strip()
        altcha      = request.form['altcha']
        timezone    = request.form['timezone']

        reload = False

        if not altcha_challange_verified(altcha):
            flash('The automatic captcha failed to be solved by your computer. Please try again.')
            reload = True
        if not email:
            flash('All fields are required.')
            reload = True

        if reload: return redirect( url_for('auth_login'))

        try: _ = ZoneInfo(timezone)  # Attempt to create a ZoneInfo object to validate timezone
        except ZoneInfoNotFoundError: timezone = 'UTC'  # Default to UTC if an invalid timezone is provided

        user = User.query.filter_by(email=email).first()
        if user:
            if user.account_active:
                verification_token = url_serializer.dumps(email, salt='email-confirm') # TODO Check if this salt is good
                verification_url = url_for(
                    'auth_verify_login', 
                    verification_token  = verification_token, 
                    encoded_timezone    = quote_plus(timezone),
                    _external           = True,
                )
                
                msg = Message('Login Link', recipients=[email])
                msg.body = f'Your login link is {verification_url}'
                mail.send(msg)

                flash('Success! Please check your email for the login link.') 
                return render_template('auth/login_email_sent.html')           
            else: flash('Tool not yet open to the public. You will be notified via email once access to the tool is granted.') # TODO change once public to "Account not acctive" for people who deactivate theri account
        else: flash('No account is registered with the email you have entered.')

        return redirect(url_for('auth_login'))

@app.route('/login/verify/<verification_token>/<encoded_timezone>')
def auth_verify_login(verification_token, encoded_timezone):
    try: email = url_serializer.loads(verification_token, salt='email-confirm', max_age=3600)  # Link expires after 1 hour
    except:
        flash('The login link is invalid or has expired.')
        return redirect(url_for('auth_login'))
    
    user = User.query.filter_by(email=email).first()
    if user and user.account_active:

        login_user(user)
        
        try: 
            timezone = unquote_plus(encoded_timezone)
            timezone_object = ZoneInfo(timezone)
        except ZoneInfoNotFoundError: timezone = 'UTC'
        
        if timezone and timezone != user.timezone:
            user.timezone = timezone
            db.session.commit()

        if user.is_new:

            user_subscription = UserSubscription(
                user_id         = user.id,
                subscription_id = 1,
                status          = 'active',
                reset_time      = datetime.now(timezone_object) + timedelta(weeks=2),

            )
            db.session.add(user_subscription)
            db.session.commit()
            user.is_new = False
        
        return redirect(url_for('dash_base'))
    
    else:
        flash('Invalid user or account not active.')
        return redirect(url_for('auth_login'))

@app.route('/logout')
@login_required
def auth_logout():
    logout_user()
    return redirect(url_for('auth_login'))

# Onboarding

@app.route('/register', methods=['GET', 'POST'])
def auth_register():

    if request.method == 'GET':
        return render_template(
            'auth/register.html', 
            challengejson=create_altcha_challenge_json()
        )

    elif request.method == 'POST':
        first_name      = request.form['firstname'].strip()
        last_name       = request.form['lastname'].strip()
        email           = request.form['email'].strip()
        legal_consent   = request.form['legal_consent']
        altcha          = request.form['altcha']

        reload = False

        if not altcha_challange_verified(altcha): 
            flash('The automatic captcha failed to be solved by your computer. Please try again.')
            reload = True
        
        if not first_name or not last_name or not email:
            flash('All fields are required.')
            reload = True

        if reload:
            return render_template(
                'auth/register.html',
                input_value_firstname   = first_name,
                input_value_lastname    = last_name,
                input_value_email       = email,
                challengejson           = create_altcha_challenge_json(),
            )

        register = True

        if not legal_consent:
            flash('Please agree to the terms by checking the box.')
            register = False

        if len(first_name) > 60:
            flash('First name cannot be longer than 60 characters.')
            first_name = ''
            register = False

        if len(last_name) > 60:
            flash('Last name cannot be longer than 60 characters.')
            last_name = ''
            register = False

        if len(email) > 150:
            flash('Email cannot be longer than 150 characters.')
            email = ''
            register = False

        if not is_regex_valid_email(email):
            email = ''
            flash('Invalid email format.')
            register = False

        if User.query.filter_by(email=email).first():
            flash('Email already registered.')
            email = ''
            register = False

        if register:
            user = User(
                email                = email, 
                first_name           = first_name, 
                last_name            = last_name, 
                public_reference_id  = str(ulid.new())
            )
            db.session.add(user)
            db.session.commit()
            flash('Registration successful. Please log in with the email you entered.')
            return redirect(url_for('auth_login'))

        return render_template(
            'auth/register.html',
            input_value_firstname   = first_name,
            input_value_lastname    = last_name,
            input_value_email       = email,
            challengejson           = create_altcha_challenge_json(),
        )

@app.route('/plans')
@login_required
def auth_plans():
    return render_template(
        'auth/plans.html',
        client_reference_id = current_user.stripe_client_reference_id,
        customer_email = current_user.email
    )

# Account Managment

@app.route('/account/update/personal_information', methods=['POST'])
@login_required
def auth_update_personal_information():
    first_name  = request.form['firstname'].strip()
    last_name   = request.form['lastname'].strip()

    update = True

    if not first_name or not last_name:
        flash('All fields are required.')
        update = False

    if len(first_name) > 60:
        flash('First name cannot be longer than 60 characters.')
        update = False

    if len(last_name) > 60:
        flash('Last name cannot be longer than 60 characters.')
        update = False

    if not update: return redirect( url_for('comp_account_personal_information'))

    current_user.first_name = first_name
    current_user.last_name = last_name
    db.session.commit()
    flash('Personal information was updated successfully.')

    return redirect( url_for('comp_account_personal_information'))

@app.route('/component/account/personal_information')
@login_required
def comp_account_personal_information():
    return render_template(
        'components/account/personal_information.html',
        first_name           = current_user.first_name,
        last_name            = current_user.last_name,
    )

    

@app.route('/account/update/email', methods=['POST'])
@login_required
def auth_update_email():
    new_email  = request.form['email'].strip()

    update = True

    if new_email == current_user.email:
        flash('The new email address is the same as the old one.')
        return redirect(url_for('comp_account_update_email_cancel'))
    
    elif not is_regex_valid_email(new_email):
        flash('Invalid email format.')
        update = False

    elif len(new_email) > 150:
        flash('Email cannot be longer than 150 characters.')
        update = False
    
    elif User.query.filter_by(email=new_email).first():
        flash('Email is already being used.')
        update = False

    if not update: return redirect(url_for('comp_account_update_email_cancel'))

    verification_token = url_serializer.dumps({'user_id': current_user.id, 'new_email': new_email}, salt='email-change') # TODO
    verification_url = url_for('auth_verify_email_change', verification_token=verification_token, _external=True)

    msg = Message('Verify Email Change', recipients=[new_email])
    msg.body = f'Click the following link to verify your new email: {verification_url}'
    mail.send(msg)

    flash('Request successful. Please complete the update by opening the verification link sent to your new email.')
    return redirect(url_for('comp_account_update_email_awaiting'))


@app.route('/component/account/update_email/awaiting')
@login_required
def comp_account_update_email_awaiting():
    return render_template('components/account/update_email_awaiting.html')

@app.route('/component/account/update_emai/cancel')
@login_required
def comp_account_update_email_cancel():
    return render_template('components/account/update_email_cancel.html', email = current_user.email)


@app.route('/verify-email-change/<verification_token>')
def auth_verify_email_change(verification_token):
    try:
        data = url_serializer.loads(verification_token, salt='email-change', max_age=3600) # TODO Check Salt
        user = User.query.get(data['user_id'])
        new_email = data['new_email']

        if user and user.email != new_email:
            user.email = new_email
            db.session.commit()
            flash('Email updated successfully.')
        else:
            flash('Invalid or expired link.')
    except:
        flash('Invalid or expired link.')

    session['current_window'] = 'dash_account'
    return redirect(url_for('dash_base'))




## Integrations with 3rd Party services 



# Lemon Squeezy
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







if __name__ == '__main__': app.run(debug=True, port=os.getenv("PORT", default=5000))



