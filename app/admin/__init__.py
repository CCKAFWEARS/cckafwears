from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import os
import hmac
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from app.models import AdminUser

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# ... existing admin routes remain unchanged ...

@admin_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    reset_token = os.environ.get("ADMIN_RESET_TOKEN", "").strip()
    if not reset_token:
        flash("Password reset is not configured. Set ADMIN_RESET_TOKEN in Render first.", "error")
        return redirect(url_for("admin.login"))

    if request.method == "POST":
        submitted_token = request.form.get("reset_token", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not hmac.compare_digest(submitted_token, reset_token):
            flash("Invalid password reset token.", "error")
        elif len(new_password) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new_password != confirm_password:
            flash("The new passwords do not match.", "error")
        else:
            # The reset token authorizes recovery, so the user does not need
            # to know or enter the existing admin username.
            user = AdminUser.query.order_by(AdminUser.id.asc()).first()
            if not user:
                flash("No admin account exists.", "error")
            else:
                user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash(
                    f"Admin password reset successfully. Your admin username is: {user.username}",
                    "success",
                )
                return redirect(url_for("admin.login"))

    return render_template("admin/reset_password.html")
