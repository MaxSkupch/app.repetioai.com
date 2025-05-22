import os

from flask              import Flask
from flask_login        import LoginManager
from flask_session      import Session
from itsdangerous       import URLSafeTimedSerializer
from redis              import Redis

from app.extensions     import db, mail 
from app.models         import User


# Extensions
server_session = Session()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # Flask Configurations
    app.config['SECRET_KEY'] = os.getenv('FLASK_SESSION_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('POSTGRES_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Redis/Valkey Configurations
    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_PERMANENT'] = False
    app.config['SESSION_USE_SIGNER'] = True
    app.config['SESSION_REDIS'] = Redis.from_url(os.getenv('VALKEY_URL'))

    # Mail Configurations
    app.config['MAIL_SERVER'] = 'smtp.ionos.de'
    app.config['MAIL_PORT'] = 465
    app.config['MAIL_USE_TLS'] = False
    app.config['MAIL_USE_SSL'] = True
    app.config['MAIL_USERNAME'] = 'no-reply@repetioai.com'
    app.config['MAIL_PASSWORD'] = os.getenv('SMTP_MAIL_SERVER_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = ('Repetio AI', 'no-reply@repetioai.com')
    app.config['MAIL_DEBUG'] = False

    # Initialize Extensions
    db.init_app(app)
    mail.init_app(app)
    server_session.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = 'auth_login'

    @login_manager.user_loader
    def load_user(user_id): 
        return db.session.get(User, int(user_id))

    # Global Variables
    app.url_serializer = URLSafeTimedSerializer(os.getenv('URL_SERIALIZER_SECRET_KEY', 'default-key'))
    app.vk = Redis.from_url(os.getenv('VALKEY_URL'), decode_responses=True)

    # Register Routes
    from app.routes.account         import register_account_page_routes;    register_account_page_routes(app)
    from app.routes.compose         import register_compose_routes;         register_compose_routes(app)
    from app.routes.dashboard       import register_dashboard_routes;       register_dashboard_routes(app)
    from app.routes.history         import register_history_routes;         register_history_routes(app)
    from app.routes.auth            import register_auth_routes;            register_auth_routes(app)
    from app.routes.transactions    import register_transaction_routes;     register_transaction_routes(app)

    return app