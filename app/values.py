from os import getenv
from dotenv import load_dotenv
load_dotenv()

# Altcha
ALTCHA_HMAC_KEY             = getenv('ALTCHA_HMAC_KEY', 'ihbfsofb7676f7s')

# Lemon Squeezy
lemonsqueezy_webhook_secret = getenv('LEMONSQUEEZY_WEBHOOK_SECRET')
lemonsqueezy_store_id       = getenv('LEMONSQUEEZY_STORE_ID')
LEMONSQUEEZY_STORE_DOMAIN   = getenv('LEMONSQUEEZY_STORE_DOMAIN')

# OpenAI  # TODO Fix below
OPENAI_API_MODEL_NAME               = getenv('OPENAI_API_MODEL')
OPENAI_MODEL_LIMIT_CONTEXT_WINDOW   = 10000  # TODO Fix 


# Free Trail Config
FREE_TRAIL_TOKENS = getenv('CONFIG_DB_FREE_TRAIL_TOKEN_ALLOWANCE')