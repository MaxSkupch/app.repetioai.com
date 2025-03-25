from os import getenv

# Altcha
ALTCHA_HMAC_KEY             = getenv('ALTCHA_HMAC_KEY', 'ihbfsofb7676f7s')

# Lemon Squeezy
lemonsqueezy_webhook_secret = getenv('LEMONSQUEEZY_WEBHOOK_SECRET')
lemonsqueezy_store_id       = getenv('LEMONSQUEEZY_STORE_ID')
LEMONSQUEEZY_STORE_DOMAIN   = getenv('LEMONSQUEEZY_STORE_DOMAIN')

# OpenAI
openai_model_name                   = getenv('OPENAI_MODEL_NAME')
openai_model_limit_context_window   = int(getenv('OPENAI_MODEL_LIMIT_CONTEXT_WINDOW'))
openai_model_limit_tpm              = int(getenv('OPENAI_MODEL_LIMIT_TPM'))
openai_model_limit_rpm              = int(getenv('OPENAI_MODEL_LIMIT_RPM'))


