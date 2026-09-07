import json
import os
from functools import wraps

from flask import Blueprint, Response, jsonify, render_template, request, url_for
from flask_login import current_user

from . import db
from .models import AdminUser, Customer, Notification, PushSubscription, Order

try:
    from pywebpush import webpush
except Exception:
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


def _send_push_info(subscription_info, title, message, target_url):
    if not _vapid_ready():
        return
    try:
        webpush(subscription_info=json.loads(subscription_info), data=json.dumps({"title": title, "body": message, "url": target_url}), vapid_private_key=os.environ["VAPID_PRIVATE_KEY"], vapid_claims={"sub": os.environ["VAPID_SUBJECT"]}, ttl=86400)
    except Exception:
        pass


def _send_push_to_rows(rows, title, message, target_url):
    for row in rows:
        _send_push_info(row.subscription_json, title, message, target_url)


def notify_customer(customer_id, title, message, target_url="/"):
    if not customer_id:
        return
    db.session.add(Notification(customer_id=customer_id, title=title, message=message, url=target_url))
    db.session.commit()
    _send_push_to_rows(PushSubscription.query.filter_by(customer_id=customer_id).all(), title, message, target_url)


def notify_admins(title, message, target_url="/admin/"):
    admin_ids = [a.id for a in AdminUser.query.all()]
    for admin_id in admin_ids:
        db.session.add(Notification(admin_user_id=admin_id, title=title, message=message, url=target_url))
    db.session.commit()
    rows = PushSubscription.query.filter(PushSubscription.admin_user_id.in_(admin_ids)).all() if admin_ids else []
    _send_push_to_rows(rows, title, message, target_url)


@notifications_bp.get("/service-worker.js")
def service_worker():
    return Response(render_template("service-worker.js"), mimetype="application/javascript")


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
    from sqlalchemy import event, inspect
    from sqlalchemy.orm import Session as SASession

    @event.listens_for(SASession, "before_flush")
    def _capture_order_events(session, flush_context, instances):
        events = session.info.setdefault("cck_order_events", [])
        seen = session.info.setdefault("cck_order_event_keys", set())
        for obj in list(session.new) + list(session.dirty):
            if not isinstance(obj, Order):
                continue
            if obj in session.new:
                key = ("new", id(obj))
                if key not in seen:
                    seen.add(key)
                    events.append(("new", obj))
            else:
                if inspect(obj).attrs.status.history.has_changes() and obj.id:
                    key = ("status", obj.id, obj.status)
                    if key not in seen:
                        seen.add(key)
                        events.append(("status", obj))

    @event.listens_for(SASession, "after_commit")
    def _deliver_order_events(session):
        events = session.info.pop("cck_order_events", [])
        session.info.pop("cck_order_event_keys", None)
        if not events:
            return
        try:
            from sqlalchemy.orm import Session
            with Session(db.engine) as delivery_session:
                push_jobs = []
                for event_type, original_order in events:
                    order = delivery_session.get(Order, original_order.id)
                    if not order:
                        continue
                    if event_type == "new":
                        title = "New CCKAFWEARS order"
                        message = f"{order.customer_name} placed order {order.order_code} for GH¢{order.total_amount:.2f}."
                        target = url_for("admin.order_detail", order_id=order.id)
                        admin_ids = [row[0] for row in delivery_session.query(AdminUser.id).all()]
                        for admin_id in admin_ids:
                            delivery_session.add(Notification(admin_user_id=admin_id, title=title, message=message, url=target))
                        rows = delivery_session.query(PushSubscription).filter(PushSubscription.admin_user_id.in_(admin_ids)).all() if admin_ids else []
                        push_jobs.extend((r.subscription_json, title, message, target) for r in rows)
                    elif event_type == "status" and order.customer_id:
                        title = f"Order {order.order_code} updated"
                        message = f"Your order is now: {order.status_label}."
                        target = url_for("storefront.order_status", order_code=order.order_code)
                        delivery_session.add(Notification(customer_id=order.customer_id, title=title, message=message, url=target))
                        rows = delivery_session.query(PushSubscription).filter_by(customer_id=order.customer_id).all()
                        push_jobs.extend((r.subscription_json, title, message, target) for r in rows)
                delivery_session.commit()
            for subscription_json, title, message, target in push_jobs:
                _send_push_info(subscription_json, title, message, target)
        except Exception:
            pass
