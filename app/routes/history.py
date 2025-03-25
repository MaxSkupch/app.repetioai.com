from flask          import abort, render_template, url_for
from flask_login    import login_required, current_user
from zoneinfo       import ZoneInfo

from app.models     import Request


def register_history_routes(app):

    @app.route('/component/history/cards_batch/<n>')
    @login_required
    def comp_request_history_cards_batch(n):
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

