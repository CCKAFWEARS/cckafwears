import os
from datetime import datetime

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, current_app
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from .. import db
from ..models import AdminUser, Product, Category, Order, Settings, ORDER_STATUSES

admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}


def _allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def _save_image(file_storage):
    if not file_storage or file_storage.filename == "":
        return ""
    if not _allowed_file(file_storage.filename):
        flash("Image must be a png, jpg or webp file.", "error")
        return ""
    filename = secure_filename(file_storage.filename)
    unique_name = f"{int(datetime.utcnow().timestamp())}_{filename}"
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name)
    file_storage.save(path)
    return unique_name


# ---------- Auth ----------

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = AdminUser.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("admin.dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("admin/login.html")


@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


# ---------- Dashboard ----------

@admin_bp.route("/")
@login_required
def dashboard():
    low_stock = Product.query.filter(Product.stock <= 3, Product.stock > 0).all()
    out_of_stock = Product.query.filter(Product.stock == 0).all()
    pending_orders = Order.query.filter(Order.status.in_(["pending_payment", "payment_review"])).order_by(Order.created_at.desc()).all()
    paid_orders = Order.query.filter_by(status="paid").order_by(Order.created_at.desc()).all()
    total_products = Product.query.count()
    return render_template(
        "admin/dashboard.html",
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        pending_orders=pending_orders,
        paid_orders=paid_orders,
        total_products=total_products,
    )


# ---------- Products ----------

@admin_bp.route("/products")
@login_required
def products():
    all_products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin/products.html", products=all_products)


@admin_bp.route("/products/new", methods=["GET", "POST"])
@login_required
def product_new():
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        image_filename = _save_image(request.files.get("image"))
        flash_ends = request.form.get("flash_sale_ends_at")
        product = Product(
            name=request.form.get("name", "").strip(),
            description=request.form.get("description", "").strip(),
            price=float(request.form.get("price") or 0),
            stock=int(request.form.get("stock") or 0),
            image_filename=image_filename,
            category_id=int(request.form["category_id"]) if request.form.get("category_id") else None,
            discount_percent=float(request.form.get("discount_percent") or 0),
            is_flash_sale=bool(request.form.get("is_flash_sale")),
            flash_sale_ends_at=datetime.fromisoformat(flash_ends) if flash_ends else None,
            is_active=True,
        )
        db.session.add(product)
        db.session.commit()
        flash(f'"{product.name}" was added to the shop.', "success")
        return redirect(url_for("admin.products"))
    return render_template("admin/product_form.html", product=None, categories=categories)


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        product.name = request.form.get("name", "").strip()
        product.description = request.form.get("description", "").strip()
        product.price = float(request.form.get("price") or 0)
        product.stock = int(request.form.get("stock") or 0)
        product.category_id = int(request.form["category_id"]) if request.form.get("category_id") else None
        product.discount_percent = float(request.form.get("discount_percent") or 0)
        product.is_flash_sale = bool(request.form.get("is_flash_sale"))
        flash_ends = request.form.get("flash_sale_ends_at")
        product.flash_sale_ends_at = datetime.fromisoformat(flash_ends) if flash_ends else None
        product.is_active = bool(request.form.get("is_active"))

        new_image = _save_image(request.files.get("image"))
        if new_image:
            product.image_filename = new_image

        db.session.commit()
        flash(f'"{product.name}" was updated.', "success")
        return redirect(url_for("admin.products"))
    return render_template("admin/product_form.html", product=product, categories=categories)


@admin_bp.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("admin.products"))


# ---------- Categories ----------

@admin_bp.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name and not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))
            db.session.commit()
            flash(f'Category "{name}" added.', "success")
        return redirect(url_for("admin.categories"))
    all_categories = Category.query.order_by(Category.name).all()
    return render_template("admin/categories.html", categories=all_categories)


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@login_required
def category_delete(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    flash("Category deleted.", "success")
    return redirect(url_for("admin.categories"))


# ---------- Orders ----------

@admin_bp.route("/orders")
@login_required
def orders():
    status_filter = request.args.get("status")
    query = Order.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    all_orders = query.order_by(Order.created_at.desc()).all()
    return render_template("admin/orders.html", orders=all_orders, statuses=ORDER_STATUSES, status_filter=status_filter)


@admin_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template("admin/order_detail.html", order=order, statuses=ORDER_STATUSES)


@admin_bp.route("/orders/<int:order_id>/set-status", methods=["POST"])
@login_required
def order_set_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get("status")
    valid_statuses = [s[0] for s in ORDER_STATUSES]
    if new_status in valid_statuses:
        order.status = new_status
        db.session.commit()
        flash(f"Order {order.order_code} marked as {order.status_label}.", "success")
    return redirect(url_for("admin.order_detail", order_id=order.id))


# ---------- Settings ----------

@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    s = Settings.get()
    if request.method == "POST":
        s.shop_name = request.form.get("shop_name", s.shop_name)
        s.shop_address = request.form.get("shop_address", s.shop_address)
        s.momo_number = request.form.get("momo_number", s.momo_number)
        s.momo_network = request.form.get("momo_network", s.momo_network)
        s.bank_name = request.form.get("bank_name", s.bank_name)
        s.bank_account_name = request.form.get("bank_account_name", s.bank_account_name)
        s.bank_account_number = request.form.get("bank_account_number", s.bank_account_number)
        s.base_delivery_fee = float(request.form.get("base_delivery_fee") or s.base_delivery_fee)
        s.fee_per_km = float(request.form.get("fee_per_km") or s.fee_per_km)

        new_lat = request.form.get("shop_lat")
        new_lng = request.form.get("shop_lng")
        if new_lat:
            s.shop_lat = float(new_lat)
        if new_lng:
            s.shop_lng = float(new_lng)

        db.session.commit()
        flash("Settings updated.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", settings=s)


@admin_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        if not check_password_hash(current_user.password_hash, current_pw):
            flash("Current password is incorrect.", "error")
        elif len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "error")
        else:
            current_user.password_hash = generate_password_hash(new_pw)
            db.session.commit()
            flash("Password changed.", "success")
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/change_password.html")
