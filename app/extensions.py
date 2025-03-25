from dotenv             import load_dotenv
from flask_sqlalchemy   import SQLAlchemy
from flask_mail         import Mail
from os                 import getenv
from openai             import AsyncOpenAI

load_dotenv() 

db              = SQLAlchemy()
mail            = Mail()
openai_client   = AsyncOpenAI(
    api_key         = getenv('OPENAI_API_KEY'),
    project         = getenv('OPENAI_API_PROJECT'),
    organization    = getenv('OPENAI_API_ORGANIZATION'),
)