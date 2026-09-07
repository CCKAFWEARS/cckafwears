from datetime import datetime
from flask_login import UserMixin
from . import db


class AdminUser(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(120), default="CCKAFWEARS")
    shop_address = db.Column(db.String(255), default="")
    shop_lat = db.Column(db.Float, default=5.5560)
    shop_lng = db.Column(db.Float, default=-0.1969)
    momo_number = db.Column(db.String(30), default="")
    momo_network = db.Column(db.String(50), default="MTN Mobile Money")
    bank_name = db.Column(db.String(120), default="")
    bank_account_name = db.Column(db.String(120), default="")
    bank_account_number = db.Column(db.String(60), default="")
    base_delivery_fee = db.Column(db.Float, default=15.0)
    fee_per_km = db.Column(db.Float, default=2.5)

    @staticmethod
    def get():
        return Settings.query.first()


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    image_data = db.Column(db.LargeBinary, nullable=True)
    image_mime_type = db.Column(db.String(80), default="image/jpeg")
    products = db.relationship("Product", backref="category", lazy=True)
    banners = db.relationship("Banner", backref="category", lazy=True)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    image_filename = db.Column(db.String(255), default="")
    image_data = db.Column(db.LargeBinary, nullable=True)
    image_mime_type = db.Column(db.String(80), default="image/jpeg")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    discount_percent = db.Column(db.Float, default=0)
    is_flash_sale = db.Column(db.Boolean, default=False)
    flash_sale_ends_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def is_visible(self):
        return self.is_active and self.in_stock

    @property
    def flash_sale_live(self):
        if not self.is_flash_sale:
            return False
        if self.flash_sale_ends_at and self.flash_sale_ends_at < datetime.utcnow():
            return False
        return True

    @property
    def current_price(self):
        if self.discount_percent and self.discount_percent > 0:
            return round(self.price * (1 - self.discount_percent / 100), 2)
        return self.price

    @property
    def has_discount(self):
        return self.discount_percent and self.discount_percent > 0


class Banner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    banner_type = db.Column(db.String(30), default="homepage", nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    link_url = db.Column(db.String(255), default="")
    image_data = db.Column(db.LargeBinary, nullable=False)
    image_mime_type = db.Column(db.String(80), default="image/jpeg")
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


ORDER_STATUSES = [
    ("pending_payment", "Pending payment"),
    ("payment_review", "Payment reported – awaiting confirmation"),
    ("paid", "Paid"),
    ("out_for_delivery", "Out for delivery"),
    ("delivered", "Delivered / Sold"),
    ("cancelled", "Cancelled"),
]


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_code = db.Column(db.String(20), unique=True, nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(30), nullable=False)
    delivery_address = db.Column(db.String(255), nullable=False)
    delivery_lat = db.Column(db.Float, nullable=True)
    delivery_lng = db.Column(db.Float, nullable=True)
    delivery_distance_km = db.Column(db.Float, nullable=True)
    delivery_fee = db.Column(db.Float, default=0)
    payment_method = db.Column(db.String(30), default="mobile_money")
    items_subtotal = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(30), default="pending_payment")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan")

    @property
    def status_label(self):
        return dict(ORDER_STATUSES).get(self.status, self.status)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    product_name = db.Column(db.String(150))
    unit_price = db.Column(db.Float)
    quantity = db.Column(db.Integer, default=1)

    @property
    def line_total(self):
        return round(self.unit_price * self.quantity, 2)
