import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "admin.login"


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-before-going-live")
    os.makedirs(app.instance_path, exist_ok=True)

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # Render/other hosts sometimes give postgres:// - SQLAlchemy needs postgresql://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    else:
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
            app.instance_path, "cckafwears.db"
        )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa

    @login_manager.user_loader
    def load_user(user_id):
        return models.AdminUser.query.get(int(user_id))

    from .storefront import storefront_bp
    from .admin import admin_bp

    app.register_blueprint(storefront_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    # Make settings/cart count available to every template
    from .models import Settings, Category

    @app.context_processor
    def inject_globals():
        from flask import session

        cart = session.get("cart", {})
        cart_count = sum(cart.values()) if cart else 0
        settings = Settings.get()
        categories = Category.query.order_by(Category.name).all()
        return dict(shop_settings=settings, cart_count=cart_count, nav_categories=categories)

    with app.app_context():
        db.create_all()
        _seed_defaults()

    return app


def _seed_defaults():
    """Create the settings row and the first admin account if they don't exist yet."""
    from .models import Settings, AdminUser
    from werkzeug.security import generate_password_hash

    if Settings.query.first() is None:
        s = Settings(
            shop_name="CCKAFWEARS",
            shop_address="Accra Central, Greater Accra, Ghana",
            shop_lat=5.5560,
            shop_lng=-0.1969,
            momo_number="0550000000",
            momo_network="MTN Mobile Money",
            bank_name="",
            bank_account_name="",
            bank_account_number="",
            base_delivery_fee=15.0,
            fee_per_km=2.5,
        )
        db.session.add(s)

    if AdminUser.query.first() is None:
        admin = AdminUser(
            username="admin",
            password_hash=generate_password_hash("changeme123"),
        )
        db.session.add(admin)

    db.session.commit()
