from datetime       import datetime, timezone
from flask          import render_template, session
from flask_login    import login_required, current_user
from urllib.parse   import quote

from app            import db
from app.functions  import token_count_to_short_string
from app.models     import UserSubscription
from app.values     import LEMONSQUEEZY_STORE_DOMAIN




def register_dashboard_routes(app):

    @app.route('/')
    @login_required
    def dash_base():
        current_window = session.get('current_window', 'dash_compose')
        
        return render_template(
            'dash/base.html',
            current_window = current_window
        )

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

        print(f'{current_user.token_balance}')

        if current_user.token_balance <= 0:
            return "Not enough tokens"

        return render_template(
            'dash/windows/compose.html',
            window_title = 'Compose',
            current_compose_step = session.get('current_compose_step', 0)
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

    @app.route('/component/token_count')
    @login_required
    def comp_token_count():

        # Check user subscription status on evry load
        # Also check before processing any request to prevent user from using service without subscription by bypassing this page
        def user_has_active_subscription():
            user_subscription = UserSubscription.query.filter_by(user_id=current_user.id, active=True).first()
            
            if  not user_subscription: 
                return False
            if user_subscription.end_time and user_subscription.end_time > datetime.now(timezone.utc):
                user_subscription.active = False
                db.session.commit()
                return False
            
            return True

    
        if user_has_active_subscription(): 
            tokens_left     = token_count_to_short_string(current_user.token_balance)
            token_allowance = token_count_to_short_string(UserSubscription.query.filter_by(user_id=current_user.id, active=True).first().subscription.included_tokens)    
            return f'<span class="font-bold">{tokens_left} / {token_allowance}</span><br><span>Tokens left</span>'
        
        else:                           
            return f'<span class="font-bold text-red-600">No Plan</span><br><span class="text-red-600">Upgrade here</span>'

