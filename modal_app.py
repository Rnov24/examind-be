"""
EXAMIND Backend — Modal deployment entrypoint.

Wraps the FastAPI app with @modal.asgi_app() (WebSocket included).
Deploy:  modal deploy modal_app.py
Serve:    modal serve modal_app.py   (dev, hot-reload-ish)

Required Modal secret (create once):
    modal secret create examind-env \
        DATABASE_URL='mysql+pymysql://<user>:<pass>@<host>:4000/examind?ssl_ca=/etc/ssl/certs/ca-certificates.crt' \
        SECRET_KEY='<64+ char random string>' \
        ENVIRONMENT=production \
        CORS_ORIGINS='["https://<your-frontend>.vercel.app"]' \
        RESEND_API_KEY='...' \
        GEMINI_API_KEY='...'

Generate a SECRET_KEY with:
    python -c "import secrets; print(secrets.token_urlsafe(64))"
"""

import modal

image = (
    modal.Image.debian_slim()
    .pip_install_from_requirements("requirements.txt")
    # copy=True: bake code into the image so every deploy serves fresh code.
    # (Without it, Modal caches the image and warm containers keep serving stale files.)
    .add_local_dir(".", remote_path="/root/examind-be", copy=True)
)

app = modal.App("examind-be")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("examind-env"), modal.Secret.from_name("examind-edge")],
    scaledown_window=300,  # keep warm 5 min after last request; raise on exam days
    timeout=600,
)
@modal.concurrent(max_inputs=100)  # many simultaneous WS proctoring connections
@modal.asgi_app()
def api():
    import sys

    sys.path.insert(0, "/root/examind-be")
    from app.main import app as fastapi_app

    return fastapi_app
