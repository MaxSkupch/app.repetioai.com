import json
import re
import ulid

from altcha         import ChallengeOptions, create_challenge, verify_solution
from datetime       import datetime, timedelta
from dotenv         import load_dotenv
from flask          import request, render_template, flash, redirect, url_for
from flask_login    import login_user, logout_user, login_required, current_user
from flask_mail     import Message
from urllib.parse   import quote_plus, unquote_plus
from zoneinfo       import ZoneInfo, ZoneInfoNotFoundError

from app            import mail, db
from app.functions  import is_regex_valid_email
from app.models     import User, TokenTransaction
from app.values     import ALTCHA_HMAC_KEY, FREE_TRAIL_TOKENS


load_dotenv()


def create_altcha_challenge_json():
    try:
        challenge = create_challenge(ChallengeOptions(hmac_key=ALTCHA_HMAC_KEY, max_number=100000))
        return json.dumps(challenge.__dict__)
    except Exception as e:
        return json.dumps({"error": f"Failed to create challenge: {str(e)}"})
    
def altcha_challange_verified(altcha_input):
    verified = False
    if altcha_input:
        try: verified, err = verify_solution(altcha_input, ALTCHA_HMAC_KEY, check_expires=True)
        except Exception as e: 
            print(e)
            verified = False
    return verified





def register_auth_routes(app):

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
                    verification_token = app.url_serializer.dumps(email, salt='email-confirm') # TODO Check if this salt is good
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
        try: email = app.url_serializer.loads(verification_token, salt='email-confirm', max_age=3600)  # Link expires after 1 hour
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
                current_user.timezone = timezone
                db.session.commit()

            if not current_user.first_login_completed:

                free_trial = TokenTransaction(
                    user_id         = user.id,
                    amount          = FREE_TRAIL_TOKENS, 
                    description      = 'Free trial tokens'
                )
                current_user.token_balance = FREE_TRAIL_TOKENS
                current_user.first_login_completed = True
                db.session.add(free_trial)
                db.session.commit()
                
            
            return redirect(url_for('dash_base'))
        
        else:
            flash('Invalid user or account not active.')
            return redirect(url_for('auth_login'))

    @app.route('/logout')
    @login_required
    def auth_logout():
        logout_user()
        return redirect(url_for('auth_login'))

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
