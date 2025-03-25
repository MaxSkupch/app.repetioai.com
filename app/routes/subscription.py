
from datetime       import datetime
from flask          import render_template
from flask_login    import login_required, current_user
from zoneinfo       import ZoneInfo

from app.functions  import token_count_to_string, time_delta_to_string
from app.models     import UserSubscription




def register_subscription_routes(app):

    @app.route('/component/subscription_status')
    @login_required
    def comp_token_page_subscription_status():
        user_subscription = UserSubscription.query.filter_by(user_id=current_user.id, active=True).first()
        
        if not user_subscription: return render_template('components/tokens/no_active_subscription.html')
        
        subscription_reset_datetime = user_subscription.next_reset_time.astimezone(ZoneInfo(current_user.timezone))
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