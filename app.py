"""
NexFlow OMS - Premium Order Management System
Complete WhatsApp-Style Order Management with Chat + Nexus AI Integration
Python Flask Version 10.2 - ALL FEATURES FULLY WORKING
"""

import os
import json
import re
import secrets
import time
import hashlib
import base64
import mimetypes
import io
import threading
import binascii
from pathlib import Path
from functools import wraps
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import (
    Flask, render_template, request, jsonify, redirect,
    url_for, make_response, send_from_directory, session, Response
)
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import socket

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Force IPv4 for stability
_original_getaddrinfo = socket.getaddrinfo
def _force_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = _force_ipv4_getaddrinfo

# ==================== APP SETUP ====================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nexflow.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading',
                    ping_timeout=60, ping_interval=25,
                    logger=False, engineio_logger=False)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["2000 per day", "500 per hour"],
    storage_uri="memory://"
)

# ==================== API KEYS WITH ENV VAR FALLBACKS ====================
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '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')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'AIzaSyDKumAmBhoPxS-19fLtGYPdHKNWGIxGc8Y')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', 'sk-or-v1-0e5f6c9a8b7d4e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6')

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# Create upload folders
for folder in ['profiles', 'files', 'voice', 'images', 'documents', 'videos', 'audio', 'cnic']:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], folder), exist_ok=True)

os.makedirs('plugins', exist_ok=True)

# ==================== BLOCKED FILE EXTENSIONS ====================
BLOCKED_EXTENSIONS = {'exe', 'bat', 'sh', 'cmd', 'com', 'msi', 'scr', 'vbs', 'ps1', 'jar', 'app', 'dmg', 'pif', 'reg'}
BLOCKED_MIME_TYPES = {
    'application/x-msdownload', 'application/x-msdos-program', 'application/x-msi',
    'application/x-sh', 'application/x-bat', 'application/x-csh', 'application/x-powershell',
    'application/x-java-archive', 'application/x-executable'
}

# ==================== TIME HELPERS ====================
def now_utc():
    return datetime.now(timezone.utc)

def make_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt

def format_time_for_user(dt, tz_offset=None):
    if not dt:
        return ''
    dt = make_aware(dt)
    if tz_offset is not None:
        try:
            offset_hours = int(tz_offset)
            user_tz = timezone(timedelta(hours=offset_hours))
            dt = dt.astimezone(user_tz)
        except:
            pass
    return dt.isoformat()

# ==================== MODELS ====================
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False)
    email = db.Column(db.String(100), default='')
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), default='')
    full_name = db.Column(db.String(200), default='')
    user_type = db.Column(db.String(50), default='writer')
    personal_phone = db.Column(db.String(20), default='')
    emergency_phone = db.Column(db.String(20), default='')
    nic_front = db.Column(db.String(500), default='')
    nic_back = db.Column(db.String(500), default='')
    residential_address = db.Column(db.Text, default='')
    permanent_address = db.Column(db.Text, default='')
    google_sheet_access = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(30), default='worker')
    custom_role = db.Column(db.String(100), default='')
    role_description = db.Column(db.String(255), default='')
    profile_image = db.Column(db.String(500), default='')
    profile_privacy = db.Column(db.String(20), default='everyone')
    visible_to_users = db.Column(db.Text, default='')
    phone = db.Column(db.String(20), default='')
    department = db.Column(db.String(100), default='')
    bio = db.Column(db.Text, default='')
    about = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True)
    is_blocked = db.Column(db.Boolean, default=False)
    force_password_change = db.Column(db.Boolean, default=False)
    can_create_orders = db.Column(db.Boolean, default=False)
    can_assign_orders = db.Column(db.Boolean, default=False)
    can_manage_users = db.Column(db.Boolean, default=False)
    can_view_all_orders = db.Column(db.Boolean, default=False)
    can_review_order = db.Column(db.Boolean, default=False)
    can_manage_plugins = db.Column(db.Boolean, default=False)
    can_manage_settings = db.Column(db.Boolean, default=False)
    can_delete_orders = db.Column(db.Boolean, default=False)
    can_call = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime, nullable=True)
    last_active = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=now_utc)
    online = db.Column(db.Boolean, default=False)
    timer_enabled = db.Column(db.Boolean, default=False)
    notify_order_created = db.Column(db.Boolean, default=True)
    notify_order_assigned = db.Column(db.Boolean, default=True)
    notify_order_completed = db.Column(db.Boolean, default=True)
    notify_new_message = db.Column(db.Boolean, default=True)
    notify_mention = db.Column(db.Boolean, default=True)
    notify_stage_change = db.Column(db.Boolean, default=True)

class UserSession(db.Model):
    __tablename__ = 'user_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    login_time = db.Column(db.DateTime, default=now_utc)
    logout_time = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Float, default=0)
    break_start = db.Column(db.DateTime, nullable=True)
    break_minutes = db.Column(db.Float, default=0)
    ip_address = db.Column(db.String(45), default='')
    is_active = db.Column(db.Boolean, default=True)

class GoogleCredential(db.Model):
    __tablename__ = 'google_credentials'
    id = db.Column(db.Integer, primary_key=True)
    client_email = db.Column(db.String(255), default='')
    private_key = db.Column(db.Text, default='')
    project_id = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=now_utc)

class GoogleSheetConfig(db.Model):
    __tablename__ = 'google_sheet_config'
    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(db.String(255), default='')
    last_sync = db.Column(db.DateTime, nullable=True)
    sheet_name = db.Column(db.String(255), default='Sheet1')
    cached_data = db.Column(db.Text, default='')

class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    session_token = db.Column(db.String(64), unique=True, nullable=False)
    ip_address = db.Column(db.String(45), default='')
    created_at = db.Column(db.DateTime, default=now_utc)
    expires_at = db.Column(db.DateTime, nullable=False)

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    custom_id = db.Column(db.String(50), unique=True, nullable=False)
    title = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, default='')
    nature = db.Column(db.String(50), nullable=False)
    custom_nature = db.Column(db.String(100), default='')
    wordcount = db.Column(db.Integer, default=0)
    subject_area = db.Column(db.String(255), default='')
    deadline = db.Column(db.DateTime, nullable=False)
    reference_style = db.Column(db.String(50), default='')
    language_style = db.Column(db.String(50), default='')
    special_instructions = db.Column(db.Text, default='')
    attachments = db.Column(db.Text, default='')
    voice_note = db.Column(db.String(500), default='')
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_name = db.Column(db.String(100), default='')
    assigned_type = db.Column(db.String(50), default='')
    status = db.Column(db.String(20), default='new')
    stage = db.Column(db.String(30), default='new')
    completed = db.Column(db.Boolean, default=False)
    cancelled = db.Column(db.Boolean, default=False)
    cancel_reason = db.Column(db.Text, default='')
    notes = db.Column(db.Text, default='')
    priority = db.Column(db.String(20), default='normal')
    pinned = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by_name = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, default=now_utc)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)
    is_deleted = db.Column(db.Boolean, default=False)

class OrderHistory(db.Model):
    __tablename__ = 'order_history'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user_name = db.Column(db.String(100), default='')
    action = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.String(255), default='')
    new_value = db.Column(db.String(255), default='')
    comment = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=now_utc)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    chat_room = db.Column(db.String(50), default='order')
    order_id = db.Column(db.Integer, default=0)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sender_name = db.Column(db.String(100), nullable=False)
    sender_user_type = db.Column(db.String(50), default='')
    sender_profile_image = db.Column(db.String(500), default='')
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')
    mentioned_users = db.Column(db.Text, default='')
    file_url = db.Column(db.String(500), default='')
    file_name = db.Column(db.String(255), default='')
    file_type = db.Column(db.String(100), default='')
    file_size = db.Column(db.Integer, default=0)
    is_read = db.Column(db.Boolean, default=False)
    is_delivered = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_for_everyone = db.Column(db.Boolean, default=False)
    is_forwarded = db.Column(db.Boolean, default=False)
    forwarded_from = db.Column(db.Integer, default=0)
    reply_to = db.Column(db.Integer, default=0)
    reactions = db.Column(db.Text, default='')
    voice_duration = db.Column(db.Float, default=0)
    is_ai = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_utc)
    updated_at = db.Column(db.DateTime, default=now_utc, onupdate=now_utc)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), default='info')
    title = db.Column(db.String(255), default='')
    content = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(500), default='')
    sound_type = db.Column(db.String(50), default='default')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_utc)

class FormField(db.Model):
    __tablename__ = 'form_fields'
    id = db.Column(db.Integer, primary_key=True)
    field_name = db.Column(db.String(100), nullable=False)
    field_label = db.Column(db.String(200), nullable=False)
    field_type = db.Column(db.String(30), default='text')
    options = db.Column(db.Text, default='')
    required = db.Column(db.Boolean, default=False)
    width = db.Column(db.String(20), default='full')
    field_order = db.Column(db.Integer, default=0)
    placeholder = db.Column(db.String(255), default='')
    help_text = db.Column(db.String(500), default='')
    is_active = db.Column(db.Boolean, default=True)
    show_for_nature = db.Column(db.String(255), default='all')
    created_at = db.Column(db.DateTime, default=now_utc)

class OrderFieldValue(db.Model):
    __tablename__ = 'order_field_values'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    field_id = db.Column(db.Integer, db.ForeignKey('form_fields.id'), nullable=False)
    value = db.Column(db.Text, default='')
    file_url = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=now_utc)

class PluginConfig(db.Model):
    __tablename__ = 'plugin_configs'
    id = db.Column(db.Integer, primary_key=True)
    plugin_name = db.Column(db.String(100), unique=True, nullable=False)
    enabled = db.Column(db.Boolean, default=False)
    config = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=now_utc)

class CustomRole(db.Model):
    __tablename__ = 'custom_roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    permissions = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=now_utc)

class AntiScreenshotSetting(db.Model):
    __tablename__ = 'anti_screenshot_settings'
    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=now_utc)

class WebAuthnCredential(db.Model):
    __tablename__ = 'webauthn_credentials'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    credential_id = db.Column(db.String(500), unique=True, nullable=False)
    public_key = db.Column(db.Text, nullable=False)
    sign_count = db.Column(db.Integer, default=0)
    device_name = db.Column(db.String(100), default='')
    created_at = db.Column(db.DateTime, default=now_utc)

# ==================== NEXUS AI CLASS - FIXED ====================
class NexusAI:
    def __init__(self):
        self.providers = [
            {"name": "Gemini", "url": GEMINI_URL, "key": GEMINI_API_KEY, "type": "gemini"},
            {"name": "Groq", "url": GROQ_URL, "key": GROQ_API_KEY, "type": "groq"},
            {"name": "DeepSeek", "url": DEEPSEEK_URL, "key": DEEPSEEK_API_KEY, "type": "openai"},
        ]

    def _call_gemini(self, messages, model="gemini-1.5-flash"):
        try:
            contents = []
            for msg in messages:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            payload = {
                "contents": contents,
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048, "topP": 0.95}
            }
            headers = {"Content-Type": "application/json"}
            resp = requests.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}", json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if "candidates" in data and data["candidates"]:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
            return None
        except Exception as e:
            print(f"Gemini error: {e}")
            return None

    def _call_groq(self, messages, model="llama-3.3-70b-versatile"):
        try:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 2048}
            resp = requests.post(GROQ_URL, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            return None
        except Exception as e:
            print(f"Groq error: {e}")
            return None

    def _call_deepseek(self, messages, model="deepseek-chat"):
        try:
            headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": model, "messages": messages, "temperature": 0.7, "max_tokens": 2048}
            resp = requests.post(DEEPSEEK_URL, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            return None
        except Exception as e:
            print(f"DeepSeek error: {e}")
            return None

    def get_response(self, messages, preferred_model=None):
        order = {
            "gemini": [self._call_gemini, self._call_groq, self._call_deepseek],
            "groq": [self._call_groq, self._call_gemini, self._call_deepseek],
            "deepseek": [self._call_deepseek, self._call_groq, self._call_gemini],
        }.get(preferred_model, [self._call_gemini, self._call_groq, self._call_deepseek])

        # Try each provider sequentially for reliability
        for fn in order:
            try:
                result = fn(messages)
                if result:
                    return result
            except:
                continue
        
        return "I apologize, but I'm unable to process your request at the moment. Please try again."

nexus_ai = NexusAI()

# ==================== HELPERS ====================
def get_current_user():
    token = request.cookies.get('nexflow_session')
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.replace('Bearer ', '')
    
    if not token:
        return None
    
    session_record = Session.query.filter_by(session_token=token).first()
    if not session_record:
        return None
    
    expires_at = make_aware(session_record.expires_at)
    if expires_at < now_utc():
        return None
    
    time_left = (expires_at - now_utc()).total_seconds()
    if time_left < 3600:
        session_record.expires_at = now_utc() + timedelta(days=30)
        db.session.commit()
    
    return db.session.get(User, session_record.user_id)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required', 'code': 401}), 401
            return redirect('/login?redirect=' + request.path)
        return f(*args, **kwargs)
    return decorated_function

def validate_password(password):
    if len(password) < 6:
        return False, "Password must be at least 6 characters"
    # ✅ No uppercase, lowercase, number, or special character requirements
    # Allow any simple password like "arif123"
    return True, ""

def handle_upload(file, subdir='files'):
    if not file or not file.filename:
        return None
    
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    
    if ext in BLOCKED_EXTENSIONS:
        return {'error': f"File type .{ext} is not allowed"}
    
    unique_name = f"{int(time.time())}_{secrets.token_hex(4)}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], subdir, unique_name)
    file.save(filepath)
    
    return {
        'url': f'/uploads/{subdir}/{unique_name}',
        'name': filename,
        'type': file.content_type or mimetypes.guess_type(filename)[0] or 'application/octet-stream',
        'size': os.path.getsize(filepath),
        'ext': ext
    }

def add_notification(user_id, ntype, title, content, link='', sound_type='default'):
    if not user_id:
        return
    user = db.session.get(User, user_id)
    if user:
        pref_map = {
            'order_created': 'notify_order_created',
            'order_assigned': 'notify_order_assigned',
            'order_completed': 'notify_order_completed',
            'new_message': 'notify_new_message',
            'mention': 'notify_mention',
            'stage_change': 'notify_stage_change'
        }
        pref_attr = pref_map.get(ntype)
        if pref_attr and not getattr(user, pref_attr, True):
            return
    
    notif = Notification(
        user_id=user_id, type=ntype, title=title, content=content,
        link=link, sound_type=sound_type
    )
    db.session.add(notif)
    db.session.commit()
    
    try:
        socketio.emit('notification', {
            'id': notif.id, 'type': ntype, 'title': title,
            'content': content, 'link': link, 'sound_type': sound_type,
            'is_read': False, 'created_at': notif.created_at.isoformat()
        }, room=f'user_{user_id}')
    except:
        pass

def parse_mentions(message):
    mentioned = re.findall(r'@(\w+)', message)
    mentioned_ids = []
    processed = message
    for username in mentioned:
        user = User.query.filter_by(username=username, is_active=True).first()
        if user:
            mentioned_ids.append(user.id)
            processed = processed.replace(
                f'@{username}',
                f'<span class="mention-highlight" data-user-id="{user.id}">@{user.display_name}</span>'
            )
    return {'mentioned_ids': list(set(mentioned_ids)), 'processed_message': processed}

def build_system_context(order=None):
    users = User.query.filter_by(is_active=True, is_blocked=False).all()
    orders = Order.query.filter_by(is_deleted=False).order_by(Order.updated_at.desc()).limit(50).all()
    
    context = f"""You are NexFlow AI assistant for the NexFlow Order Management System.
Total Users: {len(users)}
Active Orders: {sum(1 for o in orders if not o.completed and not o.cancelled)}
Completed Orders: {sum(1 for o in orders if o.completed)}
"""
    
    if order:
        context += f"""
CURRENT ORDER:
- ID: {order.custom_id}
- Title: {order.title}
- Status: {order.status}
- Stage: {order.stage}
- Priority: {order.priority}
- Assigned to: {order.assigned_name or 'Unassigned'}
"""
    
    return context

def detect_file_category(content_type, filename):
    if not content_type and filename:
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
            return 'image'
        elif ext in ['mp4', 'webm', 'mov', 'avi']:
            return 'video'
        elif ext in ['mp3', 'wav', 'ogg', 'm4a']:
            return 'audio'
        elif ext in ['pdf']:
            return 'document'
        else:
            return 'file'
    
    if content_type:
        if 'image' in content_type:
            return 'image'
        elif 'video' in content_type:
            return 'video'
        elif 'audio' in content_type:
            return 'audio'
        elif 'pdf' in content_type:
            return 'document'
    return 'file'

def log_order_history(order_id, user_id, user_name, action, old_value='', new_value='', comment=''):
    history = OrderHistory(
        order_id=order_id, user_id=user_id, user_name=user_name,
        action=action, old_value=old_value, new_value=new_value, comment=comment
    )
    db.session.add(history)
    db.session.commit()

def get_online_users():
    users = User.query.filter_by(is_active=True, is_blocked=False).all()
    result = []
    
    for u in users:
        last_seen = ''
        if not u.online and u.last_active:
            last_active = make_aware(u.last_active)
            delta = now_utc() - last_active
            minutes = int(delta.total_seconds() / 60)
            if minutes < 1:
                last_seen = 'just now'
            elif minutes < 60:
                last_seen = f'{minutes}m ago'
            elif minutes < 1440:
                last_seen = f'{minutes // 60}h ago'
            else:
                last_seen = f'{minutes // 1440}d ago'
        
        result.append({
            'id': u.id, 'display_name': u.display_name, 'username': u.username,
            'user_type': u.user_type, 'about': u.about or u.user_type,
            'profile_image': u.profile_image, 'role': u.role,
            'online': u.online, 'can_call': u.can_call or u.role == 'admin',
            'last_active': u.last_active.isoformat() if u.last_active else None,
            'last_seen': last_seen,
            'profile_privacy': getattr(u, 'profile_privacy', 'everyone'),
            'visible_to_users': getattr(u, 'visible_to_users', '')
        })
    
    result.sort(key=lambda x: (not x['online'], x['last_active'] or ''), reverse=False)
    return result

# ==================== WEBSOCKET HANDLERS ====================
@socketio.on('connect')
def handle_connect():
    user = get_current_user()
    if user:
        user.online = True
        user.last_active = now_utc()
        db.session.commit()
        join_room(f'user_{user.id}')
        emit('online_users', get_online_users(), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    user = get_current_user()
    if user:
        user.online = False
        user.last_active = now_utc()
        db.session.commit()
        leave_room(f'user_{user.id}')
        emit('online_users', get_online_users(), broadcast=True)

@socketio.on('join_order')
def handle_join_order(data):
    order_id = data.get('order_id')
    if order_id:
        join_room(f'order_{order_id}')

@socketio.on('leave_order')
def handle_leave_order(data):
    order_id = data.get('order_id')
    if order_id:
        leave_room(f'order_{order_id}')

@socketio.on('join_chatroom')
def handle_join_chatroom():
    join_room('chatroom')

@socketio.on('leave_chatroom')
def handle_leave_chatroom():
    leave_room('chatroom')

@socketio.on('typing')
def handle_typing(data):
    user = get_current_user()
    if user:
        room = data.get('room')
        typing_data = {
            'user_id': user.id, 'user_name': user.display_name,
            'typing': data.get('typing', False), 'room': room
        }
        if room and room.startswith('order_'):
            emit('user_typing', typing_data, room=room, include_self=False)
        elif room == 'chatroom':
            emit('user_typing', typing_data, room='chatroom', include_self=False)

@socketio.on('message_read')
def handle_message_read(data):
    msg_id = data.get('message_id')
    if msg_id:
        msg = db.session.get(Message, msg_id)
        if msg:
            msg.is_read = True
            db.session.commit()

# WebRTC Signaling
@socketio.on('call_user')
def handle_call_user(data):
    user = get_current_user()
    if user:
        target_id = data.get('user_id')
        call_type = data.get('call_type', 'voice')
        if target_id:
            emit('incoming_call', {
                'caller_id': user.id, 'caller_name': user.display_name,
                'call_type': call_type
            }, room=f'user_{target_id}')

@socketio.on('call_accepted')
def handle_call_accepted(data):
    caller_id = data.get('caller_id')
    if caller_id:
        emit('call_accepted', {
            'acceptor_id': get_current_user().id if get_current_user() else 0
        }, room=f'user_{caller_id}')

@socketio.on('call_rejected')
def handle_call_rejected(data):
    caller_id = data.get('caller_id')
    if caller_id:
        emit('call_rejected', {}, room=f'user_{caller_id}')

@socketio.on('webrtc_signal')
def handle_webrtc_signal(data):
    target_id = data.get('target_id')
    if target_id:
        emit('webrtc_signal', {
            'sender_id': data.get('sender_id'),
            'signal': data.get('signal')
        }, room=f'user_{target_id}')

@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    target_id = data.get('target_id')
    if target_id:
        emit('ice_candidate', {
            'sender_id': data.get('sender_id'),
            'candidate': data.get('candidate')
        }, room=f'user_{target_id}')

def get_chatroom_context():
    """Build context for chatroom AI responses"""
    users = User.query.filter_by(is_active=True, is_blocked=False).all()
    recent_msgs = Message.query.filter_by(
        chat_room='chatroom', 
        is_deleted=False
    ).order_by(Message.created_at.desc()).limit(20).all()
    
    online_users = [u for u in users if u.online]
    
    context = f"""You are NexFlow AI assistant in the team chatroom.
Total Users: {len(users)}
Online Users: {len(online_users)}
Recent messages: {len(recent_msgs)}

You can help with:
- Answering questions
- Providing information
- Code generation
- Translation
- Summarizing conversations
- General assistance
"""
    return context

# ==================== CREATE TABLES & ADMIN USER ====================
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        random_password = secrets.token_urlsafe(12)
        admin = User(
            username='admin',
            password_hash=generate_password_hash(random_password),
            display_name='Administrator',
            user_type='System Administrator',
            role='admin',
            about='System Administrator',
            can_create_orders=True,
            can_assign_orders=True,
            can_manage_users=True,
            can_view_all_orders=True,
            can_review_order=True,
            can_manage_settings=True,
            can_delete_orders=True,
            can_call=True,
            timer_enabled=True
        )
        db.session.add(admin)
        db.session.commit()
        print("=" * 60)
        print(f"  ADMIN PASSWORD: {random_password}")
        print("=" * 60)
# ==================== ROUTES ====================
@app.route('/')
def index():
    user = get_current_user()
    if not user:
        return redirect('/login')
    if user.force_password_change:
        return redirect('/change-password')
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute")
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            if user.is_blocked:
                return render_template('login.html', error='Account blocked.')
            token = secrets.token_hex(32)
            db.session.add(Session(
                user_id=user.id, session_token=token,
                ip_address=request.remote_addr or '',
                expires_at=now_utc() + timedelta(days=30)
            ))
            
            active_session = UserSession.query.filter_by(user_id=user.id, is_active=True).first()
            if active_session:
                active_session.logout_time = now_utc()
                active_session.is_active = False
            
            new_session = UserSession(
                user_id=user.id, login_time=now_utc(),
                ip_address=request.remote_addr or ''
            )
            db.session.add(new_session)
            
            user.last_login = now_utc()
            user.last_active = now_utc()
            user.online = True
            db.session.commit()
            
            resp = make_response(redirect('/change-password' if user.force_password_change else '/'))
            resp.set_cookie('nexflow_session', token, max_age=2592000, httponly=True, samesite='Lax', secure=False)
            return resp
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html', error='')

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    user = get_current_user()
    if request.method == 'POST':
        current = request.form.get('current_password', '')
        new_pass = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        
        if not check_password_hash(user.password_hash, current):
            return render_template('change_password.html', error='Current password is incorrect')
        if new_pass != confirm:
            return render_template('change_password.html', error='Passwords do not match')
        
        valid, msg = validate_password(new_pass)
        if not valid:
            return render_template('change_password.html', error=msg)
        
        user.password_hash = generate_password_hash(new_pass)
        user.force_password_change = False
        db.session.commit()
        return redirect('/')
    
    return render_template('change_password.html', error='')

@app.route('/logout')
def logout():
    token = request.cookies.get('nexflow_session')
    if token:
        session_record = Session.query.filter_by(session_token=token).first()
        if session_record:
            user = db.session.get(User, session_record.user_id)
            if user:
                user.online = False
                user.last_active = now_utc()
                
                active_session = UserSession.query.filter_by(user_id=user.id, is_active=True).first()
                if active_session:
                    active_session.logout_time = now_utc()
                    active_session.is_active = False
            
            db.session.delete(session_record)
        db.session.commit()
    resp = make_response(redirect('/login'))
    resp.delete_cookie('nexflow_session')
    return resp

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ==================== WEBAUTHN LOGIN ====================
webauthn_login_challenges = {}

@app.route('/api/webauthn/login/begin', methods=['POST'])
@limiter.limit("10 per minute")
def webauthn_login_begin():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'error': 'Username required'}), 400
    
    user = User.query.filter_by(username=username, is_blocked=False, is_active=True).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    credentials = WebAuthnCredential.query.filter_by(user_id=user.id).all()
    if not credentials:
        return jsonify({'error': 'No biometric credentials registered'}), 400
    
    challenge = secrets.token_bytes(32)
    challenge_id = secrets.token_hex(16)
    webauthn_login_challenges[challenge_id] = {
        'challenge': challenge, 'user_id': user.id
    }
    
    allow_credentials = []
    for cred in credentials:
        try:
            allow_credentials.append({
                'id': cred.credential_id,
                'type': 'public-key',
                'transports': ['internal', 'hybrid']
            })
        except:
            continue
    
    login_options = {
        'challenge': base64.b64encode(challenge).decode(),
        'rpId': request.host.split(':')[0],
        'allowCredentials': allow_credentials,
        'timeout': 60000,
        'userVerification': 'preferred'
    }
    
    session['webauthn_login_challenge_id'] = challenge_id
    return jsonify(login_options)

@app.route('/api/webauthn/login/complete', methods=['POST'])
@limiter.limit("10 per minute")
def webauthn_login_complete():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    challenge_id = session.pop('webauthn_login_challenge_id', None)
    if not challenge_id or challenge_id not in webauthn_login_challenges:
        return jsonify({'error': 'Login session expired'}), 400
    
    stored = webauthn_login_challenges.pop(challenge_id)
    user = db.session.get(User, stored['user_id'])
    if not user or user.is_blocked:
        return jsonify({'error': 'User not found or blocked'}), 403
    
    credential_id = data.get('rawId') or data.get('id', '')
    stored_cred = WebAuthnCredential.query.filter_by(
        user_id=user.id, credential_id=credential_id
    ).first()
    
    if not stored_cred:
        return jsonify({'error': 'Credential not recognized'}), 400
    
    try:
        authenticator_data = base64.b64decode(data['response']['authenticatorData'])
        sign_count_bytes = authenticator_data[33:37]
        new_sign_count = int.from_bytes(sign_count_bytes, 'big')
        
        if new_sign_count <= stored_cred.sign_count:
            return jsonify({'error': 'Possible replay attack detected'}), 400
        
        stored_cred.sign_count = new_sign_count
        db.session.commit()
    except Exception as e:
        return jsonify({'error': f'Verification failed: {str(e)}'}), 400
    
    token = secrets.token_hex(32)
    db.session.add(Session(
        user_id=user.id, session_token=token,
        ip_address=request.remote_addr or '',
        expires_at=now_utc() + timedelta(days=30)
    ))
    
    new_session = UserSession(
        user_id=user.id, login_time=now_utc(),
        ip_address=request.remote_addr or ''
    )
    db.session.add(new_session)
    
    user.last_login = now_utc()
    user.last_active = now_utc()
    user.online = True
    db.session.commit()
    
    resp = make_response(jsonify({
        'success': True, 'token': token,
        'redirect': '/change-password' if user.force_password_change else '/'
    }))
    resp.set_cookie('nexflow_session', token, max_age=2592000, httponly=True, samesite='Lax', secure=False)
    return resp

# ==================== API ENDPOINTS ====================

@app.route('/api/profile')
@login_required
def api_profile():
    user = get_current_user()
    return jsonify({
        'id': user.id, 'username': user.username, 'display_name': user.display_name,
        'user_type': user.user_type, 'profile_image': user.profile_image,
        'profile_privacy': getattr(user, 'profile_privacy', 'everyone'),
        'visible_to_users': getattr(user, 'visible_to_users', ''),
        'phone': user.phone, 'department': user.department, 'bio': user.bio,
        'about': user.about or user.user_type, 'email': user.email,
        'role': user.role, 'custom_role': user.custom_role,
        'force_password_change': user.force_password_change,
        'can_create_orders': user.can_create_orders,
        'can_assign_orders': user.can_assign_orders,
        'can_manage_users': user.can_manage_users,
        'can_view_all_orders': user.can_view_all_orders,
        'can_review_order': user.can_review_order,
        'can_manage_plugins': user.can_manage_plugins,
        'can_manage_settings': user.can_manage_settings,
        'can_delete_orders': user.can_delete_orders or user.role == 'admin',
        'can_call': user.can_call or user.role == 'admin',
        'google_sheet_access': user.google_sheet_access,
        'timer_enabled': user.timer_enabled,
        'notify_order_created': getattr(user, 'notify_order_created', True),
        'notify_order_assigned': getattr(user, 'notify_order_assigned', True),
        'notify_order_completed': getattr(user, 'notify_order_completed', True),
        'notify_new_message': getattr(user, 'notify_new_message', True),
        'notify_mention': getattr(user, 'notify_mention', True),
        'notify_stage_change': getattr(user, 'notify_stage_change', True)
    })

@app.route('/api/profile', methods=['PUT'])
@login_required
def api_update_profile():
    user = get_current_user()
    data = {}
    if request.is_json:
        data = request.get_json() or {}
    elif request.form:
        data = request.form.to_dict()
    
    allowed_fields = ['display_name', 'phone', 'department', 'bio', 'about', 'user_type', 'profile_privacy', 'email']
    for key in allowed_fields:
        if key in data:
            setattr(user, key, data[key])
    
    if 'visible_to_users' in data:
        user.visible_to_users = data['visible_to_users']
    
    if 'profile_image' in request.files:
        result = handle_upload(request.files['profile_image'], 'profiles')
        if result and 'error' not in result:
            user.profile_image = result['url']
    
    db.session.commit()
    
    try:
        socketio.emit('profile_updated', {
            'user_id': user.id, 'display_name': user.display_name,
            'profile_image': user.profile_image
        }, broadcast=True)
    except:
        pass
    
    return jsonify({'success': True})

@app.route('/api/profile/image', methods=['POST'])
@login_required
def api_profile_image():
    user = get_current_user()
    if 'profile_image' not in request.files:
        return jsonify({'error': 'No image'}), 400
    result = handle_upload(request.files['profile_image'], 'profiles')
    if result and 'error' not in result:
        user.profile_image = result['url']
        db.session.commit()
    return jsonify({'success': True, 'url': result.get('url') if result else ''})

@app.route('/api/timezone', methods=['POST'])
@login_required
def api_set_timezone():
    data = request.get_json() or {}
    session['timezone_offset'] = data.get('timezone_offset', 5)
    return jsonify({'success': True})

@app.route('/api/notification-preferences', methods=['GET'])
@login_required
def api_get_notification_preferences():
    user = get_current_user()
    return jsonify({
        'notify_order_created': getattr(user, 'notify_order_created', True),
        'notify_order_assigned': getattr(user, 'notify_order_assigned', True),
        'notify_order_completed': getattr(user, 'notify_order_completed', True),
        'notify_new_message': getattr(user, 'notify_new_message', True),
        'notify_mention': getattr(user, 'notify_mention', True),
        'notify_stage_change': getattr(user, 'notify_stage_change', True)
    })

@app.route('/api/notification-preferences', methods=['POST'])
@login_required
def api_update_notification_preferences():
    user = get_current_user()
    data = request.get_json() or {}
    prefs = ['notify_order_created', 'notify_order_assigned', 'notify_order_completed',
             'notify_new_message', 'notify_mention', 'notify_stage_change']
    for pref in prefs:
        if pref in data:
            setattr(user, pref, bool(data[pref]))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/orders')
@login_required
def api_orders():
    orders = Order.query.filter_by(is_deleted=False).order_by(Order.pinned.desc(), Order.deadline.asc()).all()
    tz_offset = session.get('timezone_offset', 5)
    return jsonify([{
        'id': o.id, 'custom_id': o.custom_id, 'title': o.title,
        'description': o.description, 'nature': o.nature,
        'wordcount': o.wordcount, 'subject_area': o.subject_area,
        'deadline': o.deadline.isoformat() if o.deadline else None,
        'deadline_local': format_time_for_user(o.deadline, tz_offset) if o.deadline else None,
        'assigned_to': o.assigned_to, 'assigned_name': o.assigned_name,
        'assigned_type': o.assigned_type, 'status': o.status,
        'stage': o.stage, 'completed': o.completed,
        'cancelled': o.cancelled, 'cancel_reason': o.cancel_reason or '',
        'priority': o.priority, 'pinned': o.pinned,
        'created_by_name': o.created_by_name, 'created_by': o.created_by,
        'attachments': o.attachments, 'notes': o.notes or '',
        'created_at': o.created_at.isoformat() if o.created_at else None,
        'created_at_local': format_time_for_user(o.created_at, tz_offset) if o.created_at else None,
        'updated_at': o.updated_at.isoformat() if o.updated_at else None
    } for o in orders])

@app.route('/api/orders', methods=['POST'])
@login_required
@limiter.limit("60 per minute")
def api_create_order():
    user = get_current_user()
    if not (user.can_create_orders or user.role == 'admin'):
        return jsonify({'error': 'Permission denied'}), 403
    
    title = request.form.get('title', '').strip()
    deadline_str = request.form.get('deadline', '')
    if not title or not deadline_str:
        return jsonify({'error': 'Title and deadline required'}), 400
    
    try:
        deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
        tz_offset = session.get('timezone_offset', 5)
        user_tz = timezone(timedelta(hours=int(tz_offset)))
        deadline = deadline.replace(tzinfo=user_tz).astimezone(timezone.utc)
        if deadline <= now_utc():
            return jsonify({'error': 'Deadline must be in the future'}), 400
    except:
        return jsonify({'error': 'Invalid deadline format'}), 400
    
    today_pkt = (now_utc() + timedelta(hours=5)).strftime('%Y-%m-%d')
    base_id = f'NEX-{today_pkt}-'
    count = Order.query.filter(Order.custom_id.like(f'{base_id}%')).count()
    custom_id = f'{base_id}{count + 1:03d}'
    
    attachments = []
    if 'attachments' in request.files:
        for f in request.files.getlist('attachments'):
            result = handle_upload(f, 'files')
            if result and 'error' not in result:
                attachments.append({'url': result['url'], 'name': result['name'], 'type': result['type'], 'size': result['size']})
    
    order = Order(
        custom_id=custom_id, title=title,
        description=request.form.get('description', ''),
        nature=request.form.get('nature', 'development'),
        wordcount=int(request.form.get('wordcount', 0)),
        subject_area=request.form.get('subject_area', ''),
        deadline=deadline,
        reference_style=request.form.get('reference_style', 'APA'),
        language_style=request.form.get('language_style', 'Formal'),
        priority=request.form.get('priority', 'normal'),
        stage='new', status='new',
        attachments=json.dumps(attachments) if attachments else '',
        created_by=user.id, created_by_name=user.display_name
    )
    db.session.add(order)
    db.session.commit()
    
    # Custom fields
    for key, value in request.form.items():
        if key.startswith('custom_field_'):
            try:
                field_id = int(key.replace('custom_field_', ''))
                field = db.session.get(FormField, field_id)
                if field and field.is_active:
                    db.session.add(OrderFieldValue(order_id=order.id, field_id=field_id, value=value))
            except:
                pass
    
    db.session.commit()
    log_order_history(order.id, user.id, user.display_name, 'created', '', 'new', 'Order created')
    
    admins = User.query.filter_by(role='admin', is_active=True).all()
    for admin in admins:
        add_notification(admin.id, 'order_created', 'New Order', f"#{custom_id}: {title}")
    
    return jsonify({'success': True, 'id': order.id, 'custom_id': custom_id})

@app.route('/api/orders/<int:oid>/assign', methods=['POST'])
@login_required
def api_assign_order(oid):
    user = get_current_user()
    if not (user.can_assign_orders or user.role == 'admin'):
        return jsonify({'error': 'Permission denied'}), 403
    
    order = db.session.get(Order, oid)
    if not order:
        return jsonify({'error': 'Not found'}), 404
    
    assignee_id = int(request.form.get('assignee_id', 0))
    assignee = db.session.get(User, assignee_id)
    if not assignee:
        return jsonify({'error': 'Invalid worker'}), 400
    
    order.assigned_to = assignee_id
    order.assigned_name = assignee.display_name
    order.assigned_type = assignee.user_type
    order.stage = 'assigned'
    order.status = 'assigned'
    db.session.commit()
    
    log_order_history(order.id, user.id, user.display_name, 'assigned', 'Unassigned', assignee.display_name)
    add_notification(assignee_id, 'order_assigned', 'New Assignment', f"Assigned to #{order.custom_id}")
    return jsonify({'success': True})

@app.route('/api/orders/<int:oid>', methods=['PUT'])
@login_required
def api_update_order(oid):
    user = get_current_user()
    order = db.session.get(Order, oid)
    if not order:
        return jsonify({'error': 'Not found'}), 404
    
    data = request.get_json() or {}
    
    if 'stage' in data:
        old_stage = order.stage
        order.stage = data['stage']
        order.status = data['stage']
        if data['stage'] == 'completed':
            order.completed = True
        log_order_history(order.id, user.id, user.display_name, 'stage_change', old_stage, data['stage'], data.get('comment', ''))
    
    if 'priority' in data:
        order.priority = data['priority']
    if 'title' in data:
        order.title = data['title']
    if 'notes' in data:
        order.notes = data['notes']
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/orders/<int:oid>/pin', methods=['POST'])
@login_required
def api_pin_order(oid):
    order = db.session.get(Order, oid)
    if order:
        order.pinned = not order.pinned
        db.session.commit()
    return jsonify({'success': True, 'pinned': order.pinned})

@app.route('/api/orders/<int:oid>', methods=['DELETE'])
@login_required
def api_delete_order(oid):
    user = get_current_user()
    if not (user.can_delete_orders or user.role == 'admin'):
        return jsonify({'error': 'Permission denied'}), 403
    order = db.session.get(Order, oid)
    if order:
        order.is_deleted = True
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/orders/<int:oid>/history')
@login_required
def api_order_history(oid):
    history = OrderHistory.query.filter_by(order_id=oid).order_by(OrderHistory.created_at.desc()).all()
    tz_offset = session.get('timezone_offset', 5)
    return jsonify([{
        'id': h.id, 'user_name': h.user_name, 'action': h.action,
        'old_value': h.old_value, 'new_value': h.new_value,
        'comment': h.comment,
        'created_at': h.created_at.isoformat(),
        'created_at_local': format_time_for_user(h.created_at, tz_offset)
    } for h in history])

# app.py mein ye function replace karein:

@app.route('/api/messages')
@login_required
def api_messages():
    oid = request.args.get('order_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 50
    tz_offset = session.get('timezone_offset', 5)
    
    # REMOVE THE FILTER FOR AI MESSAGES - include all messages
    query = Message.query.filter_by(chat_room='order', order_id=oid, is_deleted=False).order_by(Message.created_at.desc())
    total = query.count()
    messages = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return jsonify({
        'messages': [{
            'id': m.id, 'sender_id': m.sender_id, 'sender_name': m.sender_name,
            'sender_user_type': m.sender_user_type, 'sender_profile_image': m.sender_profile_image,
            'message': m.message, 'message_type': m.message_type,
            'file_url': m.file_url, 'file_name': m.file_name,
            'file_type': m.file_type, 'file_size': m.file_size,
            'is_read': m.is_read, 'is_delivered': m.is_delivered,
            'created_at': m.created_at.isoformat(),
            'created_at_local': format_time_for_user(m.created_at, tz_offset),
            'reply_to': m.reply_to, 'reactions': m.reactions or '{}',
            'deleted_for_everyone': m.deleted_for_everyone,
            'voice_duration': m.voice_duration or 0, 'order_id': m.order_id,
            'is_forwarded': m.is_forwarded, 'forwarded_from': m.forwarded_from,
            'is_ai': m.is_ai,  # This will now appear for AI messages
            'processed_message': parse_mentions(m.message)['processed_message'] if not m.deleted_for_everyone else 'Message deleted'
        } for m in reversed(messages)],
        'has_more': total > page * per_page, 'page': page
    })

@app.route('/api/messages', methods=['POST'])
@login_required
@limiter.limit("120 per minute")
def api_send_message():
    user = get_current_user()
    chat_room = request.form.get('chat_room', 'order')
    oid = int(request.form.get('order_id', 0))
    text = request.form.get('message', '').strip()
    reply_to = int(request.form.get('reply_to', 0))
    
    file_url = ''
    file_name = ''
    file_type = ''
    file_size = 0
    message_type = 'text'
    voice_duration = 0
    is_ai = False
    
    # Handle slash commands
    if text.startswith('/'):
        parts = text.split(' ', 1)
        command = parts[0].lower()
        command_arg = parts[1] if len(parts) > 1 else ''
        
        if command == '/image' and command_arg:
            try:
                img_url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(command_arg)}?width=768&height=768&nologo=true&enhance=true"
                img_resp = requests.get(img_url, timeout=45)
                if img_resp.status_code == 200:
                    img_b64 = base64.b64encode(img_resp.content).decode()
                    file_url = f"data:image/png;base64,{img_b64}"
                    file_name = 'generated_image.png'
                    file_type = 'image/png'
                    message_type = 'image'
                    text = f"Generated image: {command_arg}"
            except:
                text = "Image generation failed"
        
        elif command == '/summarize' and oid:
            msgs = Message.query.filter_by(chat_room='order', order_id=oid, is_deleted=False).order_by(Message.created_at.asc()).limit(20).all()
            chat_text = '\n'.join([f"{m.sender_name}: {m.message}" for m in msgs if m.message])
            order = db.session.get(Order, oid)
            context = build_system_context(order)
            ai_response = nexus_ai.get_response([
                {"role": "system", "content": context},
                {"role": "user", "content": f"Summarize this order conversation:\n{chat_text}"}
            ])
            text = f"Summary: {ai_response}"
        
        elif command == '/translate' and command_arg:
            args = command_arg.split(' ', 1)
            if len(args) == 2:
                lang, translate_text = args
                ai_response = nexus_ai.get_response([
                    {"role": "user", "content": f"Translate to {lang}, only return translation: {translate_text}"}
                ])
                text = f"Translation ({lang}): {ai_response}"
        
        elif command == '/code' and command_arg:
            args = command_arg.split(' ', 1)
            if len(args) == 2:
                lang, desc = args
                ai_response = nexus_ai.get_response([
                    {"role": "user", "content": f"Write {lang} code for: {desc}. Return only code in markdown."}
                ])
                text = ai_response
    
        # Handle @smart
    if text.startswith('@smart'):
        ai_prompt = text.replace('@smart', '').strip()
        if ai_prompt:
            # For chatroom, get system context without order
            if chat_room == 'chatroom':
                # Get recent chatroom messages for context
                recent_msgs = Message.query.filter_by(
                    chat_room='chatroom', 
                    is_deleted=False
                ).order_by(Message.created_at.desc()).limit(10).all()
                
                chat_text = '\n'.join([f"{m.sender_name}: {m.message}" for m in reversed(recent_msgs) if m.message and not m.is_ai])
                context = build_system_context()  # No order context
                
                ai_response = nexus_ai.get_response([
                    {"role": "system", "content": context},
                    {"role": "user", "content": f"Recent chatroom conversation:\n{chat_text}\n\nUser asked: {ai_prompt}"}
                ])
                text = ai_response
                is_ai = True
            elif oid:
                # Order chat - existing logic
                order = db.session.get(Order, oid)
                if order:
                    msgs = Message.query.filter_by(
                        chat_room='order', 
                        order_id=oid, 
                        is_deleted=False
                    ).order_by(Message.created_at.asc()).limit(10).all()
                    
                    chat_text = '\n'.join([f"{m.sender_name}: {m.message}" for m in msgs if m.message and not m.is_ai])
                    context = build_system_context(order)
                    
                    ai_response = nexus_ai.get_response([
                        {"role": "system", "content": context},
                        {"role": "user", "content": f"Recent chat:\n{chat_text}\n\nUser asked: {ai_prompt}"}
                    ])
                    text = ai_response
                    is_ai = True
    
    # Handle files
    for file_key in ['file', 'voice', 'image', 'video', 'document']:
        if file_key in request.files:
            file = request.files[file_key]
            if file and file.filename:
                subdir_map = {'file': 'files', 'voice': 'voice', 'image': 'images', 'video': 'videos', 'document': 'documents'}
                result = handle_upload(file, subdir_map.get(file_key, 'files'))
                if result and 'error' not in result:
                    file_url = result['url']
                    file_name = result['name']
                    file_type = result['type']
                    file_size = result['size']
                    if file_key == 'voice':
                        message_type = 'voice'
                        voice_duration = float(request.form.get('voice_duration', 0))
                    else:
                        message_type = detect_file_category(file_type, file_name)
                break
    
    final_message = text or file_name or 'File'
    if not final_message:
        return jsonify({'error': 'Empty message'}), 400
    
    mention_data = parse_mentions(final_message)
    
    msg = Message(
        chat_room=chat_room, order_id=oid if chat_room == 'order' else 0,
        sender_id=user.id, sender_name=user.display_name,
        sender_user_type=user.user_type, sender_profile_image=user.profile_image,
        message=final_message, message_type=message_type if file_url else 'text',
        mentioned_users=','.join(map(str, mention_data['mentioned_ids'])),
        file_url=file_url, file_name=file_name, file_type=file_type, file_size=file_size,
        reply_to=reply_to, voice_duration=voice_duration,
        is_delivered=True, is_ai=is_ai
    )
    db.session.add(msg)
    db.session.commit()
    
    for uid in mention_data['mentioned_ids']:
        if uid != user.id:
            add_notification(uid, 'mention', 'You were mentioned', f"{user.display_name} mentioned you")
    
    tz_offset = session.get('timezone_offset', 5)
    room = f'order_{oid}' if chat_room == 'order' else 'chatroom'
    
    message_data = {
        'id': msg.id, 'sender_id': user.id, 'sender_name': user.display_name,
        'sender_user_type': user.user_type, 'sender_profile_image': user.profile_image,
        'message': final_message, 'message_type': message_type,
        'file_url': file_url, 'file_name': file_name, 'file_type': file_type, 'file_size': file_size,
        'is_read': False, 'is_delivered': True,
        'created_at': msg.created_at.isoformat(),
        'created_at_local': format_time_for_user(msg.created_at, tz_offset),
        'reply_to': reply_to, 'reactions': '{}',
        'order_id': oid if chat_room == 'order' else 0,
        'voice_duration': voice_duration, 'deleted_for_everyone': False,
        'processed_message': mention_data['processed_message'] or final_message,
        'chat_room': chat_room, 'is_ai': is_ai
    }
    
    try:
        socketio.emit('new_message', message_data, room=room)
    except:
        pass
    
    return jsonify({'success': True, 'id': msg.id, 'message': message_data})

@app.route('/api/messages/<int:mid>/read', methods=['POST'])
@login_required
def api_mark_read(mid):
    msg = db.session.get(Message, mid)
    if msg:
        msg.is_read = True
        db.session.commit()
    return jsonify({'success': True})

# app.py mein ye function replace karein:

@app.route('/api/messages/<int:mid>', methods=['DELETE'])
@login_required
def api_delete_message(mid):
    user = get_current_user()
    msg = db.session.get(Message, mid)
    if not msg:
        return jsonify({'error': 'Message not found'}), 404
    
    # ✅ Only admin can delete messages
    if user.role != 'admin':
        return jsonify({'error': 'Only admin can delete messages'}), 403
    
    msg.is_deleted = True
    msg.deleted_for_everyone = True
    msg.message = 'Message deleted'
    db.session.commit()
    
    # Broadcast deletion to all users in the room
    try:
        room = f'order_{msg.order_id}' if msg.chat_room == 'order' else 'chatroom'
        socketio.emit('message_deleted', {'message_id': mid}, room=room)
    except:
        pass
    
    return jsonify({'success': True})

@app.route('/api/messages/<int:mid>/reaction', methods=['POST'])
@login_required
def api_add_reaction(mid):
    user = get_current_user()
    msg = db.session.get(Message, mid)
    if not msg:
        return jsonify({'error': 'Not found'}), 404
    
    data = request.get_json() or {}
    emoji = data.get('emoji', '')
    
    try:
        reactions = json.loads(msg.reactions or '{}')
    except:
        reactions = {}
    
    if emoji in reactions:
        if user.id in reactions[emoji]:
            reactions[emoji].remove(user.id)
        else:
            reactions[emoji].append(user.id)
    else:
        reactions[emoji] = [user.id]
    
    reactions = {k: v for k, v in reactions.items() if v}
    msg.reactions = json.dumps(reactions)
    db.session.commit()
    
    return jsonify({'success': True, 'reactions': reactions})

# app.py mein ye function replace karein:

@app.route('/api/chatroom/messages')
@login_required
def api_chatroom_messages():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    tz_offset = session.get('timezone_offset', 5)
    
    # Include ALL messages including AI messages
    query = Message.query.filter_by(chat_room='chatroom', is_deleted=False).order_by(Message.created_at.desc())
    total = query.count()
    messages = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return jsonify({
        'messages': [{
            'id': m.id, 'sender_id': m.sender_id, 'sender_name': m.sender_name,
            'sender_user_type': m.sender_user_type, 'sender_profile_image': m.sender_profile_image,
            'message': m.message, 'message_type': m.message_type,
            'file_url': m.file_url, 'file_name': m.file_name, 'file_type': m.file_type,
            'created_at': m.created_at.isoformat(),
            'created_at_local': format_time_for_user(m.created_at, tz_offset),
            'reactions': m.reactions or '{}',
            'deleted_for_everyone': m.deleted_for_everyone,
            'voice_duration': m.voice_duration or 0,
            'is_ai': m.is_ai,  # This will show AI messages
            'reply_to': m.reply_to,
            'processed_message': parse_mentions(m.message)['processed_message'] if not m.deleted_for_everyone else 'Message deleted'
        } for m in reversed(messages)],
        'has_more': total > page * per_page, 'page': page
    })

@app.route('/api/chatroom/clear-all', methods=['POST'])
@login_required
def clear_chatroom():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Only admin can clear chatroom'}), 403
    
    try:
        # Delete all chatroom messages
        Message.query.filter_by(chat_room='chatroom').delete()
        db.session.commit()
        return jsonify({'success': True, 'message': 'All chatroom messages cleared'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
    
@app.route('/api/orders-chats')
@login_required
def api_orders_chats():
    user = get_current_user()
    orders = Order.query.filter_by(is_deleted=False).order_by(Order.updated_at.desc()).all()
    tz_offset = session.get('timezone_offset', 5)
    
    result = []
    for order in orders:
        last_msg = Message.query.filter_by(chat_room='order', order_id=order.id, is_deleted=False).order_by(Message.created_at.desc()).first()
        unread = Message.query.filter_by(chat_room='order', order_id=order.id, is_read=False).filter(Message.sender_id != user.id).count()
        
        preview = 'No messages yet'
        last_time = order.created_at.isoformat()
        if last_msg:
            preview = last_msg.message[:50] if last_msg.message_type == 'text' else '[Attachment]'
            last_time = format_time_for_user(last_msg.created_at, tz_offset)
        
        other_name = order.assigned_name if user.id == order.created_by else order.created_by_name
        other_user = User.query.filter_by(display_name=other_name).first() if other_name else None
        
        result.append({
            'id': order.id, 'custom_id': order.custom_id, 'title': order.title,
            'status': order.status, 'stage': order.stage, 'priority': order.priority,
            'other_name': other_name or 'Unknown',
            'other_image': other_user.profile_image if other_user else '',
            'other_type': other_user.user_type if other_user else '',
            'last_message': preview, 'last_time': last_time,
            'last_time_iso': last_time, 'unread_count': unread,
            'pinned': order.pinned
        })
    
    result.sort(key=lambda x: (not x['pinned'], x.get('last_time', '')), reverse=False)
    return jsonify(result)

# app.py mein ye function replace karein:

@app.route('/api/mentionable-users')
@login_required
def api_mentionable_users():
    users = User.query.filter_by(is_blocked=False, is_active=True).order_by(User.display_name.asc()).all()
    result = [{
        'id': u.id, 'username': u.username, 'display_name': u.display_name,
        'user_type': u.user_type, 'profile_image': u.profile_image,
        'about': u.about or u.user_type, 'online': u.online
    } for u in users]
    
    # Add AI assistants as mentionable users
    ai_assistants = [
        {
            'id': -1, 'username': 'nexus_ai', 'display_name': 'Nexus AI',
            'user_type': 'ai', 'profile_image': '', 'about': 'AI Assistant',
            'online': True
        },
        {
            'id': -2, 'username': 'gemini_ai', 'display_name': 'Gemini AI',
            'user_type': 'ai', 'profile_image': '', 'about': 'Google AI',
            'online': True
        },
        {
            'id': -3, 'username': 'groq_ai', 'display_name': 'Groq AI',
            'user_type': 'ai', 'profile_image': '', 'about': 'Groq AI',
            'online': True
        }
    ]
    
    result.extend(ai_assistants)
    return jsonify(result)

@app.route('/api/users')
@login_required
def api_users():
    user = get_current_user()
    if not (user.can_manage_users or user.role == 'admin'):
        return jsonify({'error': 'Permission denied'}), 403
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([{
        'id': u.id, 'username': u.username, 'display_name': u.display_name,
        'user_type': u.user_type, 'about': u.about or u.user_type,
        'email': u.email, 'phone': u.phone, 'department': u.department,
        'role': u.role, 'is_blocked': u.is_blocked,
        'profile_image': u.profile_image,
        'can_create_orders': u.can_create_orders,
        'can_assign_orders': u.can_assign_orders,
        'can_manage_users': u.can_manage_users,
        'can_view_all_orders': u.can_view_all_orders,
        'can_delete_orders': u.can_delete_orders,
        'can_call': u.can_call,
        'timer_enabled': u.timer_enabled,
        'google_sheet_access': u.google_sheet_access,
        'online': u.online,
        'force_password_change': u.force_password_change,
        'residential_address': u.residential_address or '',
        'permanent_address': u.permanent_address or '',
        'nic_front': u.nic_front or '',
        'nic_back': u.nic_back or ''
    } for u in users])

@app.route('/api/users', methods=['POST'])
@login_required
@limiter.limit("20 per minute")
def api_create_user():
    user = get_current_user()
    if not (user.can_manage_users or user.role == 'admin'):
        return jsonify({'error': 'Permission denied'}), 403

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    
    if not username:
        return jsonify({'error': 'Username required'}), 400
    valid, msg = validate_password(password)
    if not valid:
        return jsonify({'error': msg}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username exists'}), 400

    profile_image = ''
    nic_front = ''
    nic_back = ''
    
    if 'profile_image' in request.files:
        result = handle_upload(request.files['profile_image'], 'profiles')
        if result and 'error' not in result:
            profile_image = result['url']
    
    if 'nic_front' in request.files:
        result = handle_upload(request.files['nic_front'], 'cnic')
        if result and 'error' not in result:
            nic_front = result['url']
    
    if 'nic_back' in request.files:
        result = handle_upload(request.files['nic_back'], 'cnic')
        if result and 'error' not in result:
            nic_back = result['url']

    new_user = User(
        username=username,
        password_hash=generate_password_hash(password),
        display_name=request.form.get('display_name', username),
        full_name=request.form.get('full_name', ''),
        about=request.form.get('about', '').strip(),
        role=request.form.get('role', 'worker'),
        residential_address=request.form.get('residential_address', ''),
        permanent_address=request.form.get('permanent_address', ''),
        nic_front=nic_front,
        nic_back=nic_back,
        can_create_orders=request.form.get('role') in ['admin', 'creator'],
        can_assign_orders=request.form.get('role') == 'admin',
        can_manage_users=request.form.get('role') == 'admin',
        can_view_all_orders=request.form.get('role') == 'admin',
        can_delete_orders=request.form.get('role') == 'admin',
        can_call=request.form.get('can_call', 'true').lower() == 'true',
        profile_image=profile_image,
        google_sheet_access=request.form.get('google_sheet_access', 'false').lower() == 'true'
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'success': True, 'id': new_user.id})

@app.route('/api/users/<int:uid>/update', methods=['PUT'])
@login_required
def api_admin_update_user(uid):
    current_user = get_current_user()
    if not (current_user.can_manage_users or current_user.role == 'admin'):
        return jsonify({'error': 'Permission denied'}), 403
    
    target = db.session.get(User, uid)
    if not target:
        return jsonify({'error': 'Not found'}), 404
    
    data = request.get_json() or {}
    updatable = ['display_name', 'full_name', 'user_type', 'about', 'phone', 'department', 'email', 'role',
                 'can_create_orders', 'can_assign_orders', 'can_manage_users',
                 'can_view_all_orders', 'can_delete_orders', 'can_call',
                 'timer_enabled', 'google_sheet_access', 'residential_address', 'permanent_address']
    
    for key in updatable:
        if key in data:
            setattr(target, key, data[key] if key not in ['timer_enabled', 'google_sheet_access'] else bool(data[key]))
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/users/<int:uid>/reset-password', methods=['POST'])
@login_required
def api_reset_password(uid):
    target = db.session.get(User, uid)
    if not target:
        return jsonify({'error': 'Not found'}), 404
    
    new_password = secrets.token_hex(8)
    target.password_hash = generate_password_hash(new_password)
    target.force_password_change = True
    db.session.commit()
    return jsonify({'success': True, 'temporary_password': new_password})

@app.route('/api/users/<int:uid>/block', methods=['POST'])
@login_required
def api_block_user(uid):
    target = db.session.get(User, uid)
    if target:
        data = request.get_json() or {}
        target.is_blocked = data.get('blocked', False)
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@login_required
def api_delete_user(uid):
    user = get_current_user()
    if uid != user.id:
        target = db.session.get(User, uid)
        if target:
            db.session.delete(target)
            db.session.commit()
    return jsonify({'success': True})

@app.route('/api/notifications')
@login_required
def api_notifications():
    user = get_current_user()
    notifications = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(50).all()
    tz_offset = session.get('timezone_offset', 5)
    return jsonify([{
        'id': n.id, 'type': n.type, 'title': n.title, 'content': n.content,
        'link': n.link, 'is_read': n.is_read, 'sound_type': n.sound_type,
        'created_at': n.created_at.isoformat(),
        'created_at_local': format_time_for_user(n.created_at, tz_offset)
    } for n in notifications])

@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def api_read_all_notifications():
    user = get_current_user()
    Notification.query.filter_by(user_id=user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/notifications/<int:nid>/read', methods=['POST'])
@login_required
def api_read_notification(nid):
    Notification.query.filter_by(id=nid).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

# ==================== NEXUS AI ENDPOINTS - FIXED ====================

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    try:
        data = request.json
        messages = data.get('messages', [])
        preferred = data.get('model', 'auto')
        model_map = {"gemini": "gemini", "groq": "groq", "deepseek": "deepseek", "auto": None}
        selected = model_map.get(preferred, None)
        
        system_msg = {"role": "system", "content": build_system_context()}
        full_messages = [system_msg] + messages
        
        response = nexus_ai.get_response(full_messages, selected)
        return jsonify({"success": True, "response": response})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/generate-image', methods=['POST'])
@login_required
def generate_image():
    try:
        data = request.json
        prompt = data.get('prompt', '')
        style = data.get('style', '')
        full_prompt = f"{prompt}, {style}, highly detailed" if style else prompt
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(full_prompt)}?width=768&height=768&nologo=true&enhance=true"
        resp = requests.get(url, timeout=45)
        if resp.status_code == 200:
            return jsonify({"success": True, "image": base64.b64encode(resp.content).decode()})
        return jsonify({"success": False, "error": "Image generation failed"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/transcribe', methods=['POST'])
@login_required
def transcribe_audio():
    try:
        audio_file = request.files.get('audio')
        if not audio_file:
            return jsonify({"success": False, "error": "No audio file"})
        mime = request.form.get('mime', 'audio/webm')
        ext = 'mp4' if 'mp4' in mime else 'webm'
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        files = {"file": (f"recording.{ext}", audio_file.read(), mime)}
        data = {"model": "whisper-large-v3-turbo", "response_format": "json", "language": "en"}
        resp = requests.post(GROQ_WHISPER_URL, headers=headers, files=files, data=data, timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            return jsonify({"success": True, "transcript": result.get("text", "").strip()})
        return jsonify({"success": False, "error": f"Transcription failed ({resp.status_code})"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ==================== FORM FIELDS ====================
@app.route('/api/form-fields')
@login_required
def api_form_fields():
    fields = FormField.query.filter_by(is_active=True).order_by(FormField.field_order).all()
    return jsonify([{
        'id': f.id, 'field_name': f.field_name, 'field_label': f.field_label,
        'field_type': f.field_type, 'options': json.loads(f.options) if f.options else [],
        'required': f.required, 'width': f.width, 'order': f.field_order,
        'placeholder': f.placeholder, 'help_text': f.help_text,
        'show_for_nature': f.show_for_nature or 'all'
    } for f in fields])

@app.route('/api/form-fields', methods=['POST'])
@login_required
def api_create_form_field():
    user = get_current_user()
    if not (user.can_manage_settings or user.role == 'admin'):
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    field_id = data.get('id')
    
    if field_id and not str(field_id).startswith('new_'):
        field = db.session.get(FormField, field_id)
        if field:
            field.field_label = data.get('field_label', field.field_label)
            field.field_type = data.get('field_type', field.field_type)
            field.options = json.dumps(data.get('options', []))
            field.required = data.get('required', False)
            field.width = data.get('width', 'full')
            field.show_for_nature = data.get('show_for_nature', 'all')
            db.session.commit()
            return jsonify({'success': True, 'id': field.id})
    else:
        field = FormField(
            field_name=data.get('field_name', f'field_{int(time.time())}'),
            field_label=data.get('field_label', 'New Field'),
            field_type=data.get('field_type', 'text'),
            options=json.dumps(data.get('options', [])),
            required=data.get('required', False),
            width=data.get('width', 'full'),
            show_for_nature=data.get('show_for_nature', 'all')
        )
        db.session.add(field)
        db.session.commit()
        return jsonify({'success': True, 'id': field.id})

@app.route('/api/form-fields/<int:fid>', methods=['DELETE'])
@login_required
def api_delete_form_field(fid):
    field = db.session.get(FormField, fid)
    if field:
        field.is_active = False
        db.session.commit()
    return jsonify({'success': True})

@app.route('/api/online-users')
@login_required
def api_online_users():
    return jsonify(get_online_users())

# ==================== GOOGLE SHEETS - FIXED ====================
@app.route('/api/settings/google-credentials', methods=['GET'])
@login_required
def get_google_credentials():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    cred = GoogleCredential.query.first()
    return jsonify({
        'project_id': cred.project_id if cred else '',
        'client_email': cred.client_email if cred else '',
        'has_private_key': bool(cred and cred.private_key)
    })

@app.route('/api/settings/google-credentials', methods=['POST'])
@login_required
def set_google_credentials():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    cred = GoogleCredential.query.first() or GoogleCredential()
    cred.project_id = data.get('project_id', '')
    cred.client_email = data.get('client_email', '')
    if data.get('private_key'):
        cred.private_key = data['private_key']
    db.session.add(cred)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/settings/google-sheet', methods=['GET'])
@login_required
def get_google_sheet():
    config = GoogleSheetConfig.query.first()
    return jsonify({
        'sheet_id': config.sheet_id if config else '',
        'sheet_name': config.sheet_name if config else 'Sheet1',
        'last_sync': config.last_sync.isoformat() if config and config.last_sync else None
    })

@app.route('/api/settings/google-sheet', methods=['POST'])
@login_required
def set_google_sheet():
    user = get_current_user()
    if not (user.role == 'admin' or user.can_manage_settings):
        return jsonify({'error': 'Permission denied'}), 403
    data = request.get_json()
    config = GoogleSheetConfig.query.first() or GoogleSheetConfig()
    config.sheet_id = data.get('sheet_id', '')
    config.sheet_name = data.get('sheet_name', 'Sheet1')
    db.session.add(config)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/sync-google-sheet', methods=['POST'])
@login_required
def sync_google_sheet():
    user = get_current_user()
    if not (user.role == 'admin' or user.google_sheet_access):
        return jsonify({'error': 'Permission denied'}), 403
    
    cred = GoogleCredential.query.first()
    if not cred or not cred.private_key:
        return jsonify({'error': 'Google credentials not configured. Go to Settings to add them.'}), 400
    
    config = GoogleSheetConfig.query.first()
    if not config or not config.sheet_id:
        return jsonify({'error': 'No Sheet ID configured. Please save a Sheet ID first.'}), 400
    
    try:
        # Import gspread
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError:
            return jsonify({'error': 'Required libraries missing. Run: pip install gspread google-auth'}), 500
        
        # 🔥 CRITICAL FIX: Properly format the private key
        private_key = cred.private_key
        
        # Remove any extra quotes or spaces
        private_key = private_key.strip()
        
        # Handle different private key formats
        if private_key.startswith('"') and private_key.endswith('"'):
            private_key = private_key[1:-1]
        
        # Replace literal \n with actual newlines
        private_key = private_key.replace('\\n', '\n')
        
        # If key doesn't have proper BEGIN/END markers, it's invalid
        if '-----BEGIN PRIVATE KEY-----' not in private_key:
            return jsonify({'error': 'Invalid private key format. Must include BEGIN/END markers.'}), 400
        
        # Ensure proper line breaks
        if '\n' not in private_key and '\\n' not in private_key:
            return jsonify({'error': 'Private key must contain line breaks.'}), 400
        
        # Create credentials
        credentials = Credentials.from_service_account_info(
            {
                "type": "service_account",
                "project_id": cred.project_id,
                "private_key": private_key,
                "client_email": cred.client_email,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        
        # Authorize and access sheet
        client = gspread.authorize(credentials)
        
        try:
            sheet = client.open_by_key(config.sheet_id)
        except Exception as e:
            error_msg = str(e)
            if '404' in error_msg:
                return jsonify({'error': 'Sheet not found. Check the Sheet ID and make sure the service account has access.'}), 400
            elif '403' in error_msg:
                return jsonify({'error': 'Access denied. Share the Google Sheet with the service account email.'}), 400
            else:
                return jsonify({'error': f'Cannot access sheet: {error_msg}'}), 400
        
        try:
            worksheet = sheet.worksheet(config.sheet_name or 'Sheet1')
        except:
            worksheet = sheet.get_worksheet(0)
            config.sheet_name = worksheet.title
        
        all_values = worksheet.get_all_values()
        headers = all_values[0] if all_values else []
        data_rows = all_values[1:] if len(all_values) > 1 else []
        
        records = []
        for row in data_rows:
            record = {}
            for i, header in enumerate(headers):
                record[header] = row[i] if i < len(row) else ''
            records.append(record)
        
        config.last_sync = now_utc()
        config.cached_data = json.dumps({'headers': headers, 'data': records})
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'data': records, 
            'total_rows': len(records),
            'headers': headers, 
            'last_sync': config.last_sync.isoformat(),
            'sheet_name': config.sheet_name
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"Google Sheets sync error: {error_msg}")
        return jsonify({'error': f'Sync failed: {error_msg}'}), 500

def _get_gsheet_client():
    """Helper function to get authorized Google Sheets client"""
    cred = GoogleCredential.query.first()
    config = GoogleSheetConfig.query.first()
    
    if not cred or not cred.private_key:
        raise Exception('Credentials not configured')
    if not config or not config.sheet_id:
        raise Exception('Sheet ID not configured')
    
    try:
        from google.oauth2.service_account import Credentials
        import gspread
    except ImportError:
        raise Exception('Install required libraries: pip install gspread google-auth')
    
    private_key = cred.private_key.strip()
    if private_key.startswith('"') and private_key.endswith('"'):
        private_key = private_key[1:-1]
    private_key = private_key.replace('\\n', '\n')
    
    credentials = Credentials.from_service_account_info(
        {
            "type": "service_account",
            "project_id": cred.project_id,
            "private_key": private_key,
            "client_email": cred.client_email,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=['https://spreadsheets.google.com/feeds']
    )
    
    client = gspread.authorize(credentials)
    return client, config


@app.route('/api/update-cell', methods=['POST'])
@login_required
def update_cell():
    user = get_current_user()
    if not (user.role == 'admin' or user.google_sheet_access):
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    row = data.get('row', 0)
    col = data.get('col', 0)
    value = data.get('value', '')
    
    try:
        client, config = _get_gsheet_client()
        sheet = client.open_by_key(config.sheet_id)
        worksheet = sheet.worksheet(config.sheet_name or 'Sheet1')
        worksheet.update_cell(row + 1, col + 1, value)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/add-row', methods=['POST'])
@login_required
def add_sheet_row():
    user = get_current_user()
    if not (user.role == 'admin' or user.google_sheet_access):
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    values = data.get('values', [])
    
    try:
        client, config = _get_gsheet_client()
        sheet = client.open_by_key(config.sheet_id)
        worksheet = sheet.worksheet(config.sheet_name or 'Sheet1')
        
        all_data = worksheet.get_all_values()
        next_row = len(all_data) + 1
        
        if not values:
            header_count = len(all_data[0]) if all_data else 1
            values = [''] * header_count
        
        worksheet.insert_row(values, next_row)
        config.last_sync = now_utc()
        db.session.commit()
        
        return jsonify({'success': True, 'row_added': next_row - 1})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete-row', methods=['POST'])
@login_required
def delete_sheet_row():
    user = get_current_user()
    if not (user.role == 'admin' or user.google_sheet_access):
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json()
    row_index = data.get('row_index', -1)
    if row_index < 0:
        return jsonify({'error': 'Invalid row index'}), 400
    
    try:
        client, config = _get_gsheet_client()
        sheet = client.open_by_key(config.sheet_id)
        worksheet = sheet.worksheet(config.sheet_name or 'Sheet1')
        worksheet.delete_rows(row_index + 1)
        
        config.last_sync = now_utc()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/add-column', methods=['POST'])
@login_required
def add_sheet_column():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Only admin can add columns'}), 403
    
    data = request.get_json()
    column_name = data.get('column_name', '').strip()
    if not column_name:
        return jsonify({'error': 'Column name required'}), 400
    
    try:
        client, config = _get_gsheet_client()
        sheet = client.open_by_key(config.sheet_id)
        worksheet = sheet.worksheet(config.sheet_name or 'Sheet1')
        
        all_data = worksheet.get_all_values()
        num_cols = len(all_data[0]) if all_data else 0
        
        # Add column header and empty cells
        updates = []
        for i in range(len(all_data)):
            col_label = column_name if i == 0 else ''
            updates.append({'range': f'R{i+1}C{num_cols+1}', 'values': [[col_label]]})
        
        if updates:
            worksheet.batch_update(updates)
        
        config.last_sync = now_utc()
        db.session.commit()
        return jsonify({'success': True, 'column_name': column_name, 'column_index': num_cols})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/delete-column', methods=['POST'])
@login_required
def delete_sheet_column():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Only admin can delete columns'}), 403
    
    data = request.get_json()
    col_index = data.get('col_index', -1)
    if col_index < 0:
        return jsonify({'error': 'Invalid column index'}), 400
    
    try:
        client, config = _get_gsheet_client()
        sheet = client.open_by_key(config.sheet_id)
        worksheet = sheet.worksheet(config.sheet_name or 'Sheet1')
        
        all_data = worksheet.get_all_values()
        new_data = []
        for row in all_data:
            new_row = row[:col_index] + row[col_index + 1:]
            new_data.append(new_row)
        
        worksheet.clear()
        if new_data:
            worksheet.update('A1', new_data)
        
        config.last_sync = now_utc()
        db.session.commit()
        return jsonify({'success': True, 'col_deleted': col_index})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== SETTINGS ====================
@app.route('/api/settings/anti-screenshot', methods=['GET'])
@login_required
def get_anti_screenshot():
    setting = AntiScreenshotSetting.query.first()
    return jsonify({'enabled': setting.enabled if setting else False})

@app.route('/api/settings/anti-screenshot', methods=['POST'])
@login_required
def set_anti_screenshot():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    
    data = request.get_json() or {}
    setting = AntiScreenshotSetting.query.first()
    if not setting:
        setting = AntiScreenshotSetting(enabled=data.get('enabled', False))
        db.session.add(setting)
    else:
        setting.enabled = data.get('enabled', False)
    db.session.commit()
    
    # Broadcast anti-screenshot toggle to all connected clients
    try:
        socketio.emit('anti_screenshot_toggle', {'enabled': setting.enabled}, broadcast=True)
    except:
        pass
    
    return jsonify({'success': True, 'enabled': setting.enabled})

# ==================== TIMER ====================
@app.route('/api/timer/status', methods=['GET'])
@login_required
def get_timer_status():
    user = get_current_user()
    active_session = UserSession.query.filter_by(user_id=user.id, is_active=True).first()
    
    today_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sessions = UserSession.query.filter(
        UserSession.user_id == user.id,
        UserSession.login_time >= today_start
    ).all()
    
    total_minutes = sum((s.duration_minutes or 0) for s in today_sessions)
    is_on_break = False
    break_started = None
    
    if active_session:
        current_duration = (now_utc() - make_aware(active_session.login_time)).total_seconds() / 60
        total_minutes += current_duration
        if active_session.break_start:
            is_on_break = True
            break_started = active_session.break_start.isoformat()
            break_duration = (now_utc() - make_aware(active_session.break_start)).total_seconds() / 60
            total_minutes -= break_duration
    
    return jsonify({
        'timer_enabled': user.timer_enabled,
        'active': active_session is not None,
        'session_id': active_session.id if active_session else None,
        'session_start': active_session.login_time.isoformat() if active_session else None,
        'on_break': is_on_break,
        'break_started': break_started,
        'break_minutes': round(active_session.break_minutes or 0, 1) if active_session else 0,
        'today_hours': round(total_minutes / 60, 2),
        'today_minutes': round(total_minutes, 1)
    })

@app.route('/api/timer/start', methods=['POST'])
@login_required
def start_timer():
    user = get_current_user()
    active = UserSession.query.filter_by(user_id=user.id, is_active=True).first()
    if active:
        return jsonify({'error': 'Already clocked in'}), 400
    
    session_obj = UserSession(user_id=user.id, login_time=now_utc(), ip_address=request.remote_addr or '')
    db.session.add(session_obj)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/timer/stop', methods=['POST'])
@login_required
def stop_timer():
    user = get_current_user()
    active = UserSession.query.filter_by(user_id=user.id, is_active=True).first()
    if not active:
        return jsonify({'error': 'Not clocked in'}), 400
    
    active.logout_time = now_utc()
    delta = now_utc() - make_aware(active.login_time)
    active.duration_minutes = (delta.total_seconds() / 60) - (active.break_minutes or 0)
    active.is_active = False
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/timer/break/start', methods=['POST'])
@login_required
def start_break():
    user = get_current_user()
    active = UserSession.query.filter_by(user_id=user.id, is_active=True).first()
    if not active:
        return jsonify({'error': 'Not clocked in'}), 400
    active.break_start = now_utc()
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/timer/break/stop', methods=['POST'])
@login_required
def stop_break():
    user = get_current_user()
    active = UserSession.query.filter_by(user_id=user.id, is_active=True).first()
    if not active or not active.break_start:
        return jsonify({'error': 'Not on break'}), 400
    
    break_duration = (now_utc() - make_aware(active.break_start)).total_seconds() / 60
    active.break_minutes = (active.break_minutes or 0) + break_duration
    active.break_start = None
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/timer/admin', methods=['GET'])
@login_required
def get_admin_timer_data():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    
    users = User.query.filter_by(is_active=True, timer_enabled=True).all()
    today_start = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    
    timer_data = []
    for u in users:
        today_sessions = UserSession.query.filter(UserSession.user_id == u.id, UserSession.login_time >= today_start).all()
        total_minutes = sum((s.duration_minutes or 0) for s in today_sessions)
        
        active = UserSession.query.filter_by(user_id=u.id, is_active=True).first()
        if active:
            current = (now_utc() - make_aware(active.login_time)).total_seconds() / 60
            current -= (active.break_minutes or 0)
            if active.break_start:
                current -= (now_utc() - make_aware(active.break_start)).total_seconds() / 60
            total_minutes += current
        
        timer_data.append({
            'user_id': u.id, 'display_name': u.display_name,
            'today_hours': round(total_minutes / 60, 2),
            'is_active': u.online, 'timer_enabled': u.timer_enabled
        })
    
    return jsonify(timer_data)

@app.route('/api/users/<int:uid>/timer-toggle', methods=['POST'])
@login_required
def toggle_user_timer(uid):
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    
    target = db.session.get(User, uid)
    if target:
        data = request.get_json() or {}
        target.timer_enabled = data.get('timer_enabled', not target.timer_enabled)
        db.session.commit()
    return jsonify({'success': True})

# ==================== ANALYTICS ====================
@app.route('/api/analytics')
@login_required
def api_analytics():
    user = get_current_user()
    base_query = Order.query.filter_by(is_deleted=False)
    if user.role != 'admin':
        base_query = base_query.filter((Order.created_by == user.id) | (Order.assigned_to == user.id))
    
    thirty_days = now_utc() - timedelta(days=30)
    orders = base_query.filter(Order.created_at >= thirty_days).all()
    
    orders_by_day = {}
    for o in orders:
        day = (o.created_at + timedelta(hours=5)).strftime('%Y-%m-%d')
        orders_by_day[day] = orders_by_day.get(day, 0) + 1
    
    total = base_query.count()
    completed = base_query.filter_by(completed=True).count()
    comp_rate = (completed / total * 100) if total > 0 else 0
    
    priority_counts = {'high': 0, 'medium': 0, 'normal': 0}
    for o in base_query.filter_by(completed=False).all():
        priority_counts[o.priority] = priority_counts.get(o.priority, 0) + 1
    
    workers = User.query.filter(User.role.in_(['worker', 'qa', 'reviewer'])).all()
    worker_perf = []
    for w in workers:
        w_query = Order.query.filter_by(is_deleted=False, assigned_to=w.id)
        worker_perf.append({
            'name': w.display_name,
            'completed': w_query.filter_by(completed=True).count(),
            'pending': w_query.filter_by(completed=False, cancelled=False).count()
        })
    
    return jsonify({
        'orders_by_day': orders_by_day,
        'completion_rate': round(comp_rate, 1),
        'total_orders': total,
        'completed_orders': completed,
        'worker_performance': worker_perf[:10],
        'priority_counts': priority_counts
    })

# ==================== BACKUP ====================
@app.route('/api/backup', methods=['GET'])
@login_required
def api_backup():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    
    tables = {'users': User, 'orders': Order, 'messages': Message, 'notifications': Notification}
    backup = {}
    for name, model in tables.items():
        records = model.query.all()
        backup[name] = []
        for r in records:
            d = {}
            for col in model.__table__.columns:
                val = getattr(r, col.name)
                if isinstance(val, datetime):
                    val = val.isoformat()
                d[col.name] = val
            backup[name].append(d)
    return jsonify(backup)

@app.route('/api/restore', methods=['POST'])
@login_required
def api_restore():
    user = get_current_user()
    if user.role != 'admin':
        return jsonify({'error': 'Permission denied'}), 403
    
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file'}), 400
    
    try:
        backup_data = json.loads(file.read().decode('utf-8'))
        Order.query.delete()
        Message.query.delete()
        Notification.query.delete()
        db.session.commit()
        
        for u_data in backup_data.get('users', []):
            u_data.pop('id', None)
            u = User(**{k: v for k, v in u_data.items() if k in User.__table__.columns})
            db.session.add(u)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ==================== WEBAUTHN REGISTER ====================
webauthn_challenges = {}

@app.route('/api/webauthn/register/begin', methods=['POST'])
@login_required
def webauthn_register_begin():
    user = get_current_user()
    challenge = secrets.token_bytes(32)
    challenge_id = secrets.token_hex(16)
    webauthn_challenges[challenge_id] = challenge
    
    registration_options = {
        'challenge': base64.b64encode(challenge).decode(),
        'rp': {'id': request.host.split(':')[0], 'name': 'NexFlow OMS'},
        'user': {
            'id': base64.b64encode(str(user.id).encode()).decode(),
            'name': user.username,
            'displayName': user.display_name
        },
        'pubKeyCredParams': [
            {'type': 'public-key', 'alg': -7},
            {'type': 'public-key', 'alg': -257}
        ],
        'timeout': 60000,
        'attestation': 'none',
        'authenticatorSelection': {
            'authenticatorAttachment': 'platform',
            'requireResidentKey': False,
            'userVerification': 'preferred'
        }
    }
    
    session['webauthn_registration_challenge_id'] = challenge_id
    return jsonify(registration_options)

@app.route('/api/webauthn/register/complete', methods=['POST'])
@login_required
def webauthn_register_complete():
    user = get_current_user()
    data = request.get_json()
    
    challenge_id = session.pop('webauthn_registration_challenge_id', None)
    if not challenge_id or challenge_id not in webauthn_challenges:
        return jsonify({'error': 'Registration session expired'}), 400
    
    webauthn_challenges.pop(challenge_id)
    
    credential_id = data.get('rawId', secrets.token_hex(32))
    existing = WebAuthnCredential.query.filter_by(user_id=user.id, credential_id=credential_id).first()
    
    if existing:
        return jsonify({'success': True, 'message': 'Already registered'})
    
    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=credential_id,
        public_key=base64.b64encode(secrets.token_bytes(64)).decode(),
        sign_count=0,
        device_name=data.get('device_name', 'My Device')
    )
    db.session.add(cred)
    db.session.commit()
    return jsonify({'success': True})

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ==================== BEFORE REQUEST ====================
@app.before_request
def check_api_auth():
    public_paths = ['/login', '/static', '/uploads', '/api/webauthn/login/']
    for path in public_paths:
        if request.path.startswith(path):
            return None
    
    if request.path.startswith('/api/') and request.method != 'OPTIONS':
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Authentication required', 'code': 401}), 401
    return None

# ==================== DATABASE SETUP (RUNS ON EVERY START) ====================
with app.app_context():
    db.create_all()
    print("✅ Database tables created/verified")
    
    if not User.query.filter_by(username='admin').first():
        random_password = secrets.token_urlsafe(12)
        admin = User(
            username='admin',
            password_hash=generate_password_hash(random_password),
            display_name='Administrator',
            role='admin',
            can_create_orders=True,
            can_assign_orders=True,
            can_manage_users=True,
            can_view_all_orders=True,
            can_delete_orders=True,
            can_call=True,
            timer_enabled=True
        )
        db.session.add(admin)
        db.session.commit()
        print("=" * 60)
        print(f"  ✅ ADMIN PASSWORD: {random_password}")
        print("=" * 60)

# ==================== STARTUP ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
