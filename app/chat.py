import secrets
from datetime import datetime

from flask import Blueprint, jsonify, request, session, url_for
from flask_login import current_user

from . import db
from .models import AdminUser, Customer, ChatConversation, ChatMessage
from .notifications import notify_admins

chat_bp = Blueprint("chat", __name__)


def _visitor_token():
    token = session.get("cck_chat_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["cck_chat_token"] = token
    return token


def _conversation_for_visitor(create=False):
    token = _visitor_token()
    conversation = ChatConversation.query.filter_by(visitor_token=token).first()
    if not conversation and create:
        name = getattr(current_user, "name", None) if isinstance(current_user, Customer) else "Shop visitor"
        customer_id = current_user.id if isinstance(current_user, Customer) else None
        conversation = ChatConversation(visitor_token=token, customer_id=customer_id, customer_name=name or "Shop visitor", status="bot")
        db.session.add(conversation)
        db.session.flush()
        db.session.add(ChatMessage(conversation_id=conversation.id, sender_type="bot", sender_name="CCKAFWEARS Assistant", body="Hi! I’m here to help. If you need a member of our team, just tap ‘Speak to a person’."))
        db.session.commit()
    return conversation


def _serialize_message(message):
    return {"id": message.id, "sender": message.sender_type, "name": message.sender_name, "body": message.body, "created_at": message.created_at.isoformat()}


@chat_bp.post("/api/chat/start")
def start_chat():
    conversation = _conversation_for_visitor(create=True)
    return jsonify({"conversation_id": conversation.id, "status": conversation.status, "messages": [_serialize_message(m) for m in conversation.messages]})


@chat_bp.get("/api/chat/messages")
def visitor_messages():
    conversation = _conversation_for_visitor(create=False)
    if not conversation:
        return jsonify({"conversation_id": None, "status": "bot", "messages": []})
    after = request.args.get("after", 0, type=int)
    messages = ChatMessage.query.filter(ChatMessage.conversation_id == conversation.id, ChatMessage.id > after).order_by(ChatMessage.id.asc()).all()
    return jsonify({"conversation_id": conversation.id, "status": conversation.status, "messages": [_serialize_message(m) for m in messages]})


@chat_bp.post("/api/chat/message")
def visitor_message():
    data = request.get_json(silent=True) or {}
    body = (data.get("message") or "").strip()
    if not body or len(body) > 2000:
        return jsonify({"error": "Message must be between 1 and 2000 characters."}), 400
    conversation = _conversation_for_visitor(create=True)
    if conversation.status == "closed":
        conversation.status = "bot"
    db.session.add(ChatMessage(conversation_id=conversation.id, sender_type="customer", sender_name=conversation.customer_name or "Shop visitor", body=body))
    conversation.updated_at = datetime.utcnow()
    db.session.commit()
    if conversation.status == "active":
        return jsonify({"ok": True, "status": conversation.status})
    return jsonify({"ok": True, "status": conversation.status, "reply": _bot_reply(body)})


def _bot_reply(body):
    text = body.lower()
    if any(x in text for x in ("human", "person", "agent", "staff", "someone", "representative")):
        return "Of course. Tap ‘Speak to a person’ and I’ll connect you with our team."
    if "deliver" in text or "shipping" in text:
        return "We deliver across Ghana, and free shipping applies to orders over GHS 500."
    if "return" in text:
        return "We offer easy returns. If you need help with a specific order, tap ‘Speak to a person’."
    if "size" in text:
        return "For the best fit, check the size information on the product page. If you’re unsure, our team can help you choose."
    if "track" in text or "order" in text:
        return "You can use Track order to check your order. If you need us to look into it, tap ‘Speak to a person’."
    if "shop" in text or "product" in text or "dress" in text or "shoe" in text or "bag" in text:
        return "Absolutely — browse the collection using Shop. If you want a recommendation from a person, I can connect you."
    return "I can help with products, sizes, delivery, returns and order tracking. If my answer isn’t clear, tap ‘Speak to a person’ and our team can take over."


@chat_bp.post("/api/chat/human")
def request_human():
    conversation = _conversation_for_visitor(create=True)
    if conversation.status != "active":
        conversation.status = "waiting"
    if isinstance(current_user, Customer):
        conversation.customer_id = current_user.id
        conversation.customer_name = current_user.name
    conversation.updated_at = datetime.utcnow()
    db.session.add(ChatMessage(conversation_id=conversation.id, sender_type="system", sender_name="CCKAFWEARS", body="You’ve been placed in the live-chat queue. A team member will reply here as soon as possible."))
    db.session.commit()
    notify_admins("New live chat request", f"{conversation.customer_name} is waiting for a CCKAFWEARS team member.", url_for("admin.chat", conversation_id=conversation.id))
    return jsonify({"ok": True, "status": conversation.status, "conversation_id": conversation.id})


def _admin_conversation(conversation_id):
    if not current_user.is_authenticated or not isinstance(current_user, AdminUser):
        return None
    return ChatConversation.query.get_or_404(conversation_id)


@chat_bp.get("/admin/chat")
def admin_chat():
    if not current_user.is_authenticated or not isinstance(current_user, AdminUser):
        from flask import redirect
        return redirect(url_for("admin.login"))
    conversations = ChatConversation.query.order_by(ChatConversation.updated_at.desc()).limit(100).all()
    return __import__("flask").render_template("admin/chat.html", conversations=conversations)


@chat_bp.get("/admin/chat/<int:conversation_id>/data")
def admin_chat_data(conversation_id):
    conversation = _admin_conversation(conversation_id)
    if conversation is None:
        return jsonify({"error": "login required"}), 401
    after = request.args.get("after", 0, type=int)
    messages = ChatMessage.query.filter(ChatMessage.conversation_id == conversation.id, ChatMessage.id > after).order_by(ChatMessage.id.asc()).all()
    return jsonify({"conversation_id": conversation.id, "status": conversation.status, "customer_name": conversation.customer_name, "messages": [_serialize_message(m) for m in messages]})


@chat_bp.post("/admin/chat/<int:conversation_id>/reply")
def admin_chat_reply(conversation_id):
    conversation = _admin_conversation(conversation_id)
    if conversation is None:
        return jsonify({"error": "login required"}), 401
    data = request.get_json(silent=True) or {}
    body = (data.get("message") or "").strip()
    if not body or len(body) > 2000:
        return jsonify({"error": "Message must be between 1 and 2000 characters."}), 400
    conversation.status = "active"
    conversation.assigned_admin_id = current_user.id
    conversation.updated_at = datetime.utcnow()
    db.session.add(ChatMessage(conversation_id=conversation.id, sender_type="admin", sender_name=current_user.username, body=body))
    db.session.commit()
    return jsonify({"ok": True, "status": conversation.status})


@chat_bp.post("/admin/chat/<int:conversation_id>/close")
def admin_chat_close(conversation_id):
    conversation = _admin_conversation(conversation_id)
    if conversation is None:
        return jsonify({"error": "login required"}), 401
    conversation.status = "closed"
    conversation.updated_at = datetime.utcnow()
    db.session.add(ChatMessage(conversation_id=conversation.id, sender_type="system", sender_name="CCKAFWEARS", body="This chat has been closed. The customer can start a new conversation at any time."))
    db.session.commit()
    return jsonify({"ok": True})
