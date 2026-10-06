def post_fork(server, worker):
    """Each worker gets its own DB pool after single-process schema preparation."""
    from app import app
    from models import db
    with app.app_context():
        db.engine.dispose(close=False)
