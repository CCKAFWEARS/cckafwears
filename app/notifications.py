import json
import os
from functools import wraps

from flask import Blueprint, jsonify, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import Session

from . import db
from .models import AdminUser, Customer, Notification, PushSubscription

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover
    WebPushException = Exception
    webpush = None

notifications_bp = Blueprint("notifications", __name__)


def _is_customer():
    return current_user.is_authenticated and isinstance(current_user, Customer)


def _is_admin():
    return current_user.is_authenticated and isinstance(current_user, AdminUser)


def _require_any_user(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not (_is_customer() or _is_admin()):
            return jsonify({"error": "login required"}), 401
        return view(*args, **kwargs)
    return wrapped


def _vapid_ready():
    return bool(os.environ.get("VAPID_PRIVATE_KEY", "").strip() and os.environ.get("VAPID_PUBLIC_KEY", "").strip() and os.environ.get("VAPID_SUBJECT", "").strip() and webpush)


def _send_push(subscription, title, message, target_url):
    if not _vapid_ready():
        return True
    payload = json.dumps({"title": title, "body": message, "url": target_url})
    try:
        webpush(
            subscription_info=json.loads(subscription.subscription_json),
            data=payload,
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": os.environ["VAPID_SUBJECT"]},
            ttl=86400,
        )
        return True
    except WebPushException as exc:
        if getattr(exc, "response", None) is not None and getattr(exc.response, "status_code", None) in (404, 410):
            db.session.delete(subscription)
            return False
        return False
    except Exception:
        return False


def _push_to_subscriptions(subscriptions, title, message, target_url):
    for subscription in list(subscriptions):
        _send_push(subscription, title, message, target_url)
    db.session.commit()


def notify_customer(customer_id, title, message, target_url="/"):
    if not customer_id:
        return
    notification = Notification(customer_id=customer_id, title=title, message=message, url=target_url)
    db.session.add(notification)
    db.session.commit()
    subscriptions = PushSubscription.query.filter_by(customer_id=customer_id).all()
    _push_to_subscriptions(subscriptions, title, message, target_url)


def notify_admins(title, message, target_url="/admin/"):
    admin_ids = [a.id for a in AdminUser.query.all()]
    for admin_id in admin_ids:
        db.session.add(Notification(admin_user_id=admin_id, title=title, message=message, url=target_url))
    db.session.commit()
    subscriptions = PushSubscription.query.filter(PushSubscription.admin_user_id.in_(admin_ids)).all() if admin_ids else []
    _push_to_subscriptions(subscriptions, title, message, target_url)


def queue_order_status_notification(order):
    if order.customer_id:
        notify_customer(
            order.customer_id,
            f"Order {order.order_code} updated",
            f"Your order is now: {order.status_label}.",
            url_for("storefront.order_status", order_code=order.order_code),
        )


def queue_new_order_notification(order):
    notify_admins(
        "New CCKAFWEARS order",
        f"{order.customer_name} placed order {order.order_code} for GH¢{order.total_amount:.2f}.",
        url_for("admin.order_detail", order_id=order.id),
    )


@notifications_bp.get("/service-worker.js")
def service_worker():
    return render_template("service-worker.js", vapid_public_key=os.environ.get("VAPID_PUBLIC_KEY", ""), mimetype="application/javascript")


@notifications_bp.get("/api/push/public-key")
def public_key():
    return jsonify({"publicKey": os.environ.get("VAPID_PUBLIC_KEY", "")})


@notifications_bp.post("/api/push/subscribe")
def subscribe():
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return jsonify({"error": "Invalid push subscription"}), 400
    subscription = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not subscription:
        subscription = PushSubscription(endpoint=endpoint, subscription_json=json.dumps({"endpoint": endpoint, "keys": keys}))
        db.session.add(subscription)
    else:
        subscription.subscription_json = json.dumps({"endpoint": endpoint, "keys": keys})
    if _is_customer():
        subscription.customer_id = current_user.id
        subscription.admin_user_id = None
    elif _is_admin():
        subscription.admin_user_id = current_user.id
        subscription.customer_id = None
    db.session.commit()
    return jsonify({"ok": True})


@notifications_bp.post("/api/push/unsubscribe")
def unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = (data.get("endpoint") or "").strip()
    if endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint).delete()
        db.session.commit()
    return jsonify({"ok": True})


@notifications_bp.get("/notifications")
@_require_any_user
def notification_list():
    query = Notification.query.filter(Notification.customer_id == current_user.id) if _is_customer() else Notification.query.filter(Notification.admin_user_id == current_user.id)
    notifications = query.order_by(Notification.created_at.desc()).limit(50).all()
    return render_template("notifications.html", notifications=notifications)


@notifications_bp.post("/notifications/<int:notification_id>/read")
@_require_any_user
def notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    owner_ok = (notification.customer_id == current_user.id) if _is_customer() else (notification.admin_user_id == current_user.id)
    if not owner_ok:
        return jsonify({"error": "forbidden"}), 403
    notification.is_read = True
    db.session.commit()
    return jsonify({"ok": True})


@notifications_bp.get("/api/notifications/unread-count")
@_require_any_user
def unread_count():
    query = Notification.query.filter_by(is_read=False)
    query = query.filter(Notification.customer_id == current_user.id) if _is_customer() else query.filter(Notification.admin_user_id == current_user.id)
    return jsonify({"count": query.count()})


def register_notification_listeners():
    from sqlalchemy import event
    from sqlalchemy.orm import Session as SASession

    @event.listens_for(SASession, "before_flush")
    def _capture_order_events(session, flush_context, instances):
        events = session.info.setdefault("cck_order_events", [])
        for obj in session.new:
            if obj.__class__.__name__ == "Order":
                events.append(("new", obj.id, obj.order_code, obj.customer_id, obj.status, obj.total_amount))
        for obj in session.dirty:
            if obj.__class__.__name__ != "Order":
                continue
            state = __import__("sqlalchemy").inspect(obj)
            history = state.attrs.status.history
            if history.has_changes() and obj.id:
                events.append(("status", obj.id, obj.order_code, obj.customer_id, obj.status, obj.total_amount))

    @event.listens_for(SASession, "after_commit")
    def _deliver_order_events(session):
        events = session.info.pop("cck_order_events", [])
        if not events:
            return
        try:
            for event_type, order_id, order_code, customer_id, status, total_amount in events:
                from flask import has_app_context
                if not has_app_context():
                    continue
                from .models import Order
                order = Order.query.get(order_id)
                if not order:
                    continue
                if event_type == "new":
                    queue_new_order_notification(order)
                elif event_type == "status":
                    queue_order_status_notification(order)
        except Exception:
            # Notifications must never break a successful order/payment update.
            pass
