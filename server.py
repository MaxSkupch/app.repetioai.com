from os             import getenv

from app            import create_app
from app.extensions import db
from app.models     import Subscription

app = create_app()

with app.app_context():
    db.create_all()

    # TODO Remove before Prod
    free_trail = Subscription.query.filter_by(id=1).first()
    if not free_trail: 
        free_trail = Subscription(
            display_name    = 'Free Trail', 
            monthly_cost    = 0, 
            included_tokens = 20_000
        )
        db.session.add(free_trail)
            
    db.session.commit()

if __name__ == '__main__': 
    app.run(debug=True, port=getenv("PORT", default=5000))

