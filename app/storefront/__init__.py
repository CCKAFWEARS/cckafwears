import random
import secrets
import string
from datetime import datetime, timedelta
from functools import wraps
from io import BytesIO

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort, send_file, send_from_directory, current_app
from flask_login import current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash

from .. import db
from ..models import Product, Category, Order, OrderItem, Settings, Banner, Customer
from ..delivery import calculate_delivery
from ..email_utils import send_password_reset_code, send_order_confirmation, send_admin_order_notification

storefront_bp = Blueprint("storefront", __name__, template_folder="../templates/storefront")


def _visible_products_query():
    return Product.query.filter(Product.is_active.is_(True), Product.stock > 0)


def _generate_order_code():
    return "CK" + "".join(random.choices(string.digits, k=6))


def _customer_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not isinstance(current_user, Customer):
            flash("Please log in to continue.", "error")
            return redirect(url_for("storefront.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def _make_otp():
    return f"{secrets.randbelow(1000000):06d}"


@storefront_bp.route("/account/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated and isinstance(current_user, Customer):
        return redirect(url_for("storefront.account"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(name) < 2 or "@" not in email or len(password) < 8:
            flash("Enter your name, a valid Gmail address and a password of at least 8 characters.", "error")
            return render_template("storefront/register.html")
        customer = Customer.query.filter_by(email=email).first()
        if customer:
            flash("An account with that email already exists. Please log in.", "error")
            return redirect(url_for("storefront.login"))
        customer = Customer(name=name, email=email, password_hash=generate_password_hash(password))
        db.session.add(customer)
        db.session.commit()
        login_user(customer)
        flash("Your customer account was created successfully.", "success")
        return redirect(url_for("storefront.account"))
    return render_template("storefront/register.html")


@storefront_bp.route("/account/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and isinstance(current_user, Customer):
        return redirect(url_for("storefront.account"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        customer = Customer.query.filter_by(email=email).first()
        if not customer or not check_password_hash(customer.password_hash, password):
            flash("Email or password is incorrect.", "error")
            return render_template("storefront/login.html")
        login_user(customer)
        flash("Welcome back!", "success")
        return redirect(request.form.get("next") or url_for("storefront.account"))
    return render_template("storefront/login.html")


@storefront_bp.route("/account/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("storefront.home"))


@storefront_bp.route("/account")
@_customer_required
def account():
    orders = Order.query.filter_by(customer_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("storefront/account.html", customer=current_user, orders=orders)


@storefront_bp.route("/account/settings", methods=["GET", "POST"])
@_customer_required
def account_settings():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if len(name) < 2:
            flash("Please enter a valid name.", "error")
        else:
            current_user.name = name
            db.session.commit()
            flash("Your information has been updated.", "success")
        return redirect(url_for("storefront.account_settings"))
    return render_template("storefront/account_settings.html", customer=current_user)


@storefront_bp.route("/account/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        customer = Customer.query.filter_by(email=email).first()
        if customer:
            code = _make_otp()
            customer.reset_token_hash = generate_password_hash(code)
            customer.reset_token_expires_at = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()
            send_password_reset_code(customer, code)
        flash("If an account exists for that email, a password reset code has been sent.", "success")
        return redirect(url_for("storefront.reset_password", email=email))
    return render_template("storefront/forgot_password.html")


@storefront_bp.route("/account/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        code = request.form.get("code", "").strip()
        password = request.form.get("password", "")
        customer = Customer.query.filter_by(email=email).first()
        valid = customer and customer.reset_token_hash and customer.reset_token_expires_at and customer.reset_token_expires_at >= datetime.utcnow() and check_password_hash(customer.reset_token_hash, code)
        if not valid or len(password) < 8:
            flash("The reset code is invalid or expired, or the new password is too short.", "error")
            return render_template("storefront/reset_password.html", email=email)
        customer.password_hash = generate_password_hash(password)
        customer.reset_token_hash = None
        customer.reset_token_expires_at = None
        db.session.commit()
        flash("Your password has been reset. You can now log in.", "success")
        return redirect(url_for("storefront.login"))
    return render_template("storefront/reset_password.html", email=request.args.get("email", ""))


@storefront_bp.route("/")
def home():
    flash_sale_products = [p for p in _visible_products_query().all() if p.flash_sale_live][:8]
    new_arrivals = _visible_products_query().order_by(Product.created_at.desc()).limit(8).all()
    banners = Banner.query.filter_by(banner_type="homepage", is_active=True).order_by(Banner.sort_order.asc(), Banner.created_at.desc()).all()
    category_banners = Banner.query.filter_by(banner_type="promotion", is_active=True).order_by(Banner.sort_order.asc(), Banner.created_at.desc()).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template("storefront/home.html", flash_sale_products=flash_sale_products, new_arrivals=new_arrivals, banners=banners, category_banners=category_banners, categories=categories)


@storefront_bp.route("/shop")
def shop():
    category_id = request.args.get("category", type=int)
    search_term = request.args.get("q", "").strip()
    query = _visible_products_query()
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search_term:
        like = f"%{search_term}%"
        query = query.filter((Product.name.ilike(like)) | (Product.description.ilike(like)))
    products = query.order_by(Product.created_at.desc()).all()
    active_category = Category.query.get(category_id) if category_id else None
    category_banner = None
    if active_category and not search_term:
        category_banner = Banner.query.filter_by(category_id=active_category.id, banner_type="category", is_active=True).order_by(Banner.sort_order.asc(), Banner.created_at.desc()).first()
    return render_template("storefront/shop.html", products=products, active_category=active_category, category_banner=category_banner, search_term=search_term)


@storefront_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_visible:
        abort(404)
    return render_template("storefront/product_detail.html", product=product)


@storefront_bp.route("/media/product/<int:product_id>")
def product_media(product_id):
    product = Product.query.get_or_404(product_id)
    if product.image_data:
        return send_file(BytesIO(product.image_data), mimetype=product.image_mime_type or "image/jpeg", max_age=31536000)
    if product.image_filename:
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], product.image_filename)
    abort(404)


@storefront_bp.route("/media/category/<int:category_id>")
def category_media(category_id):
    category = Category.query.get_or_404(category_id)
    if not category.image_data:
        abort(404)
    return send_file(BytesIO(category.image_data), mimetype=category.image_mime_type or "image/jpeg", max_age=31536000)


@storefront_bp.route("/media/banner/<int:banner_id>")
def banner_media(banner_id):
    banner = Banner.query.get_or_404(banner_id)
    if not banner.image_data:
        abort(404)
    return send_file(BytesIO(banner.image_data), mimetype=banner.image_mime_type or "image/jpeg", max_age=31536000)


def _get_cart():
    return session.setdefault("cart", {})


def _get_wishlist():
    return session.setdefault("wishlist", [])


@storefront_bp.route("/wishlist/toggle/<int:product_id>", methods=["POST"])
def wishlist_toggle(product_id):
    product = Product.query.get_or_404(product_id)
    wishlist = _get_wishlist()
    if product_id in wishlist:
        wishlist.remove(product_id)
        flash(f"Removed {product.name} from your wishlist.", "success")
    else:
        wishlist.append(product_id)
        flash(f"Added {product.name} to your wishlist.", "success")
    session["wishlist"] = wishlist
    session.modified = True
    return redirect(request.form.get("next") or url_for("storefront.shop"))


@storefront_bp.route("/wishlist")
def wishlist_view():
    wishlist = _get_wishlist()
    products = [p for p in Product.query.filter(Product.id.in_(wishlist)).all() if p.is_visible] if wishlist else []
    return render_template("storefront/wishlist.html", products=products)


def _cart_line_items():
    cart = _get_cart()
    line_items, subtotal = [], 0.0
    for product_id_str, qty in cart.items():
        product = Product.query.get(int(product_id_str))
        if not product or not product.is_active:
            continue
        qty = min(qty, product.stock) if product.stock else 0
        if qty <= 0:
            continue
        line_total = round(product.current_price * qty, 2)
        subtotal += line_total
        line_items.append({"product": product, "quantity": qty, "line_total": line_total})
    return line_items, round(subtotal, 2)


@storefront_bp.route("/cart")
def cart_view():
    line_items, subtotal = _cart_line_items()
    return render_template("storefront/cart.html", line_items=line_items, subtotal=subtotal)


@storefront_bp.route("/cart/add/<int:product_id>", methods=["POST"])
def cart_add(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_visible:
        abort(404)
    qty = max(1, request.form.get("quantity", 1, type=int))
    cart = _get_cart()
    key = str(product_id)
    cart[key] = min(product.stock, cart.get(key, 0) + qty)
    session["cart"] = cart
    session.modified = True
    flash(f"Added {product.name} to your bag.", "success")
    return redirect(url_for("storefront.cart_view"))


@storefront_bp.route("/cart/update/<int:product_id>", methods=["POST"])
def cart_update(product_id):
    cart = _get_cart()
    qty = request.form.get("quantity", 0, type=int)
    key = str(product_id)
    if qty <= 0:
        cart.pop(key, None)
    else:
        product = Product.query.get(product_id)
        if product:
            cart[key] = min(product.stock, qty)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("storefront.cart_view"))


@storefront_bp.route("/cart/remove/<int:product_id>", methods=["POST"])
def cart_remove(product_id):
    cart = _get_cart()
    cart.pop(str(product_id), None)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("storefront.cart_view"))


@storefront_bp.route("/checkout", methods=["GET", "POST"])
@_customer_required
def checkout():
    line_items, subtotal = _cart_line_items()
    if not line_items:
        flash("Your bag is empty.", "error")
        return redirect(url_for("storefront.shop"))
    settings = Settings.get()
    if request.method == "POST":
        phone = request.form.get("customer_phone", "").strip()
        address = request.form.get("delivery_address", "").strip()
        payment_method = request.form.get("payment_method", "mobile_money")
        if not phone or not address:
            flash("Please fill in your phone number and delivery address.", "error")
            return render_template("storefront/checkout.html", line_items=line_items, subtotal=subtotal, settings=settings, customer=current_user)
        delivery = calculate_delivery(address, settings.shop_lat, settings.shop_lng, settings.base_delivery_fee, settings.fee_per_km)
        order = Order(order_code=_generate_order_code(), customer_id=current_user.id, customer_email=current_user.email, customer_name=current_user.name, customer_phone=phone, delivery_address=address, delivery_lat=delivery["lat"], delivery_lng=delivery["lng"], delivery_distance_km=delivery["distance_km"], delivery_fee=delivery["fee"], payment_method=payment_method, items_subtotal=subtotal, total_amount=round(subtotal + delivery["fee"], 2), status="pending_payment")
        db.session.add(order)
        db.session.flush()
        for line in line_items:
            product = line["product"]
            db.session.add(OrderItem(order_id=order.id, product_id=product.id, product_name=product.name, unit_price=product.current_price, quantity=line["quantity"]))
            product.stock = max(0, product.stock - line["quantity"])
        db.session.commit()
        send_order_confirmation(order)
        send_admin_order_notification(order)
        session["cart"] = {}
        session.modified = True
        flash("Order placed successfully. A confirmation has been sent to your email.", "success")
        return redirect(url_for("storefront.order_status", order_code=order.order_code))
    return render_template("storefront/checkout.html", line_items=line_items, subtotal=subtotal, settings=settings, customer=current_user)


@storefront_bp.route("/order/<order_code>")
def order_status(order_code):
    order = Order.query.filter_by(order_code=order_code).first_or_404()
    if current_user.is_authenticated and isinstance(current_user, Customer) and order.customer_id not in (None, current_user.id):
        abort(403)
    return render_template("storefront/order_status.html", order=order, settings=Settings.get())


@storefront_bp.route("/order/<order_code>/report-payment", methods=["POST"])
def report_payment(order_code):
    order = Order.query.filter_by(order_code=order_code).first_or_404()
    if current_user.is_authenticated and isinstance(current_user, Customer) and order.customer_id not in (None, current_user.id):
        abort(403)
    if order.status == "pending_payment":
        order.status = "payment_review"
        db.session.commit()
        flash("Thanks! We'll confirm your payment shortly.", "success")
    return redirect(url_for("storefront.order_status", order_code=order.order_code))


@storefront_bp.route("/track", methods=["GET", "POST"])
def track_order():
    order = None
    if request.method == "POST":
        code = request.form.get("order_code", "").strip().upper()
        order = Order.query.filter_by(order_code=code).first()
        if not order:
            flash("We couldn't find an order with that code.", "error")
    return render_template("storefront/track.html", order=order)
