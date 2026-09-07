import random
import string
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort

from .. import db
from ..models import Product, Category, Order, OrderItem, Settings
from ..delivery import calculate_delivery

storefront_bp = Blueprint(
    "storefront", __name__, template_folder="../templates/storefront"
)


def _visible_products_query():
    return Product.query.filter(Product.is_active.is_(True), Product.stock > 0)


def _generate_order_code():
    return "CK" + "".join(random.choices(string.digits, k=6))


@storefront_bp.route("/")
def home():
    flash_sale_products = [
        p for p in _visible_products_query().all() if p.flash_sale_live
    ][:8]
    new_arrivals = _visible_products_query().order_by(Product.created_at.desc()).limit(8).all()
    return render_template(
        "storefront/home.html",
        flash_sale_products=flash_sale_products,
        new_arrivals=new_arrivals,
    )


@storefront_bp.route("/shop")
def shop():
    category_id = request.args.get("category", type=int)
    query = _visible_products_query()
    if category_id:
        query = query.filter(Product.category_id == category_id)
    products = query.order_by(Product.created_at.desc()).all()
    active_category = Category.query.get(category_id) if category_id else None
    return render_template("storefront/shop.html", products=products, active_category=active_category)


@storefront_bp.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_visible:
        abort(404)
    return render_template("storefront/product_detail.html", product=product)


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
    next_url = request.form.get("next") or url_for("storefront.shop")
    return redirect(next_url)


@storefront_bp.route("/wishlist")
def wishlist_view():
    wishlist = _get_wishlist()
    products = [
        p for p in Product.query.filter(Product.id.in_(wishlist)).all() if p.is_visible
    ] if wishlist else []
    return render_template("storefront/wishlist.html", products=products)


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


def _cart_line_items():
    cart = _get_cart()
    line_items = []
    subtotal = 0.0
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


@storefront_bp.route("/checkout", methods=["GET", "POST"])
def checkout():
    line_items, subtotal = _cart_line_items()
    if not line_items:
        flash("Your bag is empty.", "error")
        return redirect(url_for("storefront.shop"))

    settings = Settings.get()

    if request.method == "POST":
        name = request.form.get("customer_name", "").strip()
        phone = request.form.get("customer_phone", "").strip()
        address = request.form.get("delivery_address", "").strip()
        payment_method = request.form.get("payment_method", "mobile_money")

        if not name or not phone or not address:
            flash("Please fill in your name, phone number and delivery address.", "error")
            return render_template("storefront/checkout.html", line_items=line_items, subtotal=subtotal)

        delivery = calculate_delivery(
            address, settings.shop_lat, settings.shop_lng,
            settings.base_delivery_fee, settings.fee_per_km,
        )

        order = Order(
            order_code=_generate_order_code(),
            customer_name=name,
            customer_phone=phone,
            delivery_address=address,
            delivery_lat=delivery["lat"],
            delivery_lng=delivery["lng"],
            delivery_distance_km=delivery["distance_km"],
            delivery_fee=delivery["fee"],
            payment_method=payment_method,
            items_subtotal=subtotal,
            total_amount=round(subtotal + delivery["fee"], 2),
            status="pending_payment",
        )
        db.session.add(order)
        db.session.flush()

        for line in line_items:
            product = line["product"]
            db.session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=product.name,
                    unit_price=product.current_price,
                    quantity=line["quantity"],
                )
            )
            # Reserve stock immediately, same as most shopping sites at checkout.
            # Product.is_visible already checks stock > 0, so hitting zero here
            # automatically removes it from the storefront - no extra flag needed.
            product.stock = max(0, product.stock - line["quantity"])

        db.session.commit()
        session["cart"] = {}
        session.modified = True

        return redirect(url_for("storefront.order_status", order_code=order.order_code))

    return render_template(
        "storefront/checkout.html", line_items=line_items, subtotal=subtotal, settings=settings
    )


@storefront_bp.route("/order/<order_code>")
def order_status(order_code):
    order = Order.query.filter_by(order_code=order_code).first_or_404()
    settings = Settings.get()
    return render_template("storefront/order_status.html", order=order, settings=settings)


@storefront_bp.route("/order/<order_code>/report-payment", methods=["POST"])
def report_payment(order_code):
    order = Order.query.filter_by(order_code=order_code).first_or_404()
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
