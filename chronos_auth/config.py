from preview_config import require_secret

TOKEN_ALGORITHM = "HS256"
TOKEN_EXPIRATION_HOURS = 24
SECRET_KEY = require_secret("PREVIEW_SSO_SECRET")
