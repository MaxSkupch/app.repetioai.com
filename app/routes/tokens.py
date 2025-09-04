
from datetime       import datetime
from flask          import render_template, abort
from flask_login    import login_required, current_user
from zoneinfo       import ZoneInfo

from app.functions  import token_count_to_string, time_delta_to_string
from app.models     import TokenTransaction

def register_tokens_routes(app):
    
    
    @app.route('/component/tokens/transactions_batch/<n>')
    @login_required
    def comp_tokens_transactions_batch(n):
        try: n = int(n)
        except: abort(404)

        limit = 10
        offset = (n - 1) * 10
        transactions = TokenTransaction.query.filter_by(user_id=current_user.id).order_by(TokenTransaction.transaction_date.desc()).offset(offset).limit(limit).all()
        
        if not transactions: return "History is empty."

        # TODO Delete
        for transaction in transactions:
            print(transaction.amount)
            
        if len(transactions) < 10:      has_more = False
        else:                           has_more = True 

        transactions_list = []

        for transaction in transactions:
            plus_or_minus = '+' if transaction.amount >= 0 else '-'

            print

            transactions_list.append({
                'amount':           f'{plus_or_minus}{token_count_to_string(transaction.amount)}',
                'description':      transaction.description,
                'created_at_date':  transaction.transaction_date.astimezone(ZoneInfo(current_user.timezone)).strftime('%Y-%m-%d'),
                'created_at_time':  transaction.transaction_date.astimezone(ZoneInfo(current_user.timezone)).strftime('%H:%M'),
            })
        
        return render_template(
            'components/tokens/token_history_batch.html',
            n = n+1,
            transactions = transactions_list,
            has_more = has_more,
        )