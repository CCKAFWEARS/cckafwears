from datetime import datetime
from flask import request, redirect, url_for, flash, render_template
from flask_login import login_required

from . import db
from .models import Product, Category
from .admin import admin_bp, _save_images
from .storefront import storefront_bp

SIZE_OPTIONS = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]


class ProductSize(db.Model):
    __tablename__ = "product_size"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True)
    size = db.Column(db.String(20), nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)

    product = db.relationship("Product", backref=db.backref("size_rows", cascade="all, delete-orphan", order_by="ProductSize.sort_order"))


def _product_sizes(product):
    return [row.size for row in product.size_rows]


Product.size_options = property(_product_sizes)


@admin_bp.route("/products/new-with-sizes", methods=["POST"])
@login_required
def product_new_with_sizes():
    categories = Category.query.order_by(Category.name).all()
    selected_sizes = [s for s in request.form.getlist("sizes") if s in SIZE_OPTIONS]
    uploaded_images = _save_images(request.files.getlist("images"))
    flash_ends = request.form.get("flash_sale_ends_at")
    primary = uploaded_images[0] if uploaded_images else None
    product = Product(name=request.form.get("name", "").strip(), description=request.form.get("description", "").strip(), price=float(request.form.get("price") or 0), stock=int(request.form.get("stock") or 0), image_filename=primary[2] if primary else "", image_data=primary[0] if primary else None, image_mime_type=primary[1] if primary else "image/jpeg", category_id=int(request.form["category_id"]) if request.form.get("category_id") else None, discount_percent=float(request.form.get("discount_percent") or 0), is_flash_sale=bool(request.form.get("is_flash_sale")), flash_sale_ends_at=datetime.fromisoformat(flash_ends) if flash_ends else None, is_active=True)
    db.session.add(product)
    db.session.flush()
    for index, uploaded in enumerate(uploaded_images):
        from .models import ProductImage
        db.session.add(ProductImage(product_id=product.id, image_data=uploaded[0], image_mime_type=uploaded[1], image_filename=uploaded[2], sort_order=index))
    for index, size in enumerate(selected_sizes):
        db.session.add(ProductSize(product_id=product.id, size=size, sort_order=index))
    db.session.commit()
    flash(f'"{product.name}" was added with {len(selected_sizes)} size option(s).', "success")
    return redirect(url_for("admin.products"))


@admin_bp.route("/products/<int:product_id>/edit-with-sizes", methods=["POST"])
@login_required
def product_edit_with_sizes(product_id):
    product = Product.query.get_or_404(product_id)
    selected_sizes = [s for s in request.form.getlist("sizes") if s in SIZE_OPTIONS]
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
    uploaded_images = _save_images(request.files.getlist("images"))
    if uploaded_images:
        from .models import ProductImage
        primary = uploaded_images[0]
        product.image_data, product.image_mime_type, product.image_filename = primary
        next_sort = max([image.sort_order for image in product.images], default=-1) + 1
        for index, uploaded in enumerate(uploaded_images):
            db.session.add(ProductImage(product_id=product.id, image_data=uploaded[0], image_mime_type=uploaded[1], image_filename=uploaded[2], sort_order=next_sort + index))
    for row in list(product.size_rows):
        db.session.delete(row)
    for index, size in enumerate(selected_sizes):
        db.session.add(ProductSize(product_id=product.id, size=size, sort_order=index))
    db.session.commit()
    flash(f'"{product.name}" was updated with {len(selected_sizes)} size option(s).', "success")
    return redirect(url_for("admin.products"))


@storefront_bp.route("/cart/add-size/<int:product_id>", methods=["POST"])
def cart_add_size(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_visible:
        return redirect(url_for("storefront.shop"))
    available = product.size_options
    size = request.form.get("size", "").strip().upper()
    if available and size not in available:
        flash("Please select a valid size before adding this item to your bag.", "error")
        return redirect(url_for("storefront.product_detail", product_id=product.id))
    qty = max(1, request.form.get("quantity", 1, type=int))
    cart = session.setdefault("cart", {})
    key = str(product_id)
    cart[key] = min(product.stock, cart.get(key, 0) + qty)
    sizes = session.setdefault("cart_sizes", {})
    if size:
        sizes[key] = size
    session["cart"] = cart
    session["cart_sizes"] = sizes
    session.modified = True
    flash(f"Added {product.name}{' — Size ' + size if size else ''} to your bag.", "success")
    return redirect(url_for("storefront.cart_view"))
