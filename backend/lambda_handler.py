"""AWS Lambda entrypoint. Wraps the FastAPI ASGI app with Mangum.

Handler = lambda_handler.handler (see infra/lambda.tf).
"""
from mangum import Mangum

from main import app

# lifespan="off": DB tables are created out-of-band via `python -m scripts.migrate`,
# not on startup, so we don't run DDL against Neon on every cold start.
_asgi = Mangum(app, lifespan="off")


def handler(event, context):
    # EventBridge keep-warm ping — short-circuit before invoking the app.
    if isinstance(event, dict) and event.get("warmer"):
        return {"warmed": True}
    return _asgi(event, context)
