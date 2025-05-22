from datetime       import datetime, timezone
from flask          import render_template, session
from flask_login    import login_required, current_user
from urllib.parse   import quote

from app.functions  import token_count_to_short_string
from app.values     import LEMONSQUEEZY_STORE_DOMAIN




def register_dashboard_routes(app):

    # Dash Full Pages

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

        if current_user.token_balance <= 0:
            return "Not enough tokens"  # TODO: Redirect to purchase page or somthing

        return render_template(
            'dash/windows/compose.html',
            window_title = 'Compose',
            current_compose_step = session.get('current_composition_step', 0)
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


    # Dash Components

    @app.route('/component/token_count')
    @login_required
    def comp_token_count():

        token_balance = current_user.token_balance

        if token_balance > 0: return f'<span class="font-bold"             >{token_count_to_short_string(token_balance)}</span><br><span>Tokens left</span>'
        else:                 return f'<span class="font-bold text-red-500">{token_count_to_short_string(token_balance)}</span><br><span class="text-red-500">Tokens left</span>'
        
        

