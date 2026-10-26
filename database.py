import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
GENERATED_DIR = os.path.join(DATA_DIR, "generated")
DB_PATH = os.path.join(DATA_DIR, "instatech.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)


def _load_dotenv():
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            pass


_load_dotenv()

DEFAULT_SETTINGS = {
    # Marka & Görsel Şablon Ayarları
    "brand_name": "SİBER KAPSÜL",
    "brand_handle": "@siberkapsul",
    "brand_footer_text": "Detaylar açıklamada • Kaydetmeyi unutma",
    "template_style": "modern_gradient",  # modern_gradient, cyber_frame, minimal_magazine
    "accent_color": "#00E5FF",            # Siber Mavi
    "show_source_credit": True,

    # Yapay Zeka (Google Gemini) Ayarları
    "gemini_api_key": "",
    "gemini_model": "gemini-3-flash-preview",
    "ai_tone": "Merak uyandıran, akıcı, profesyonel ve etkileşim odaklı teknoloji habercisi dili",
    "custom_hashtags": "#siberkapsul #teknoloji #yapayzeka #gündem #bilim #yazılım #donanım #kesfet",

    # Instagram Hesap Ayarları (Kullanıcı Adı / Şifre)
    "ig_username": "",
    "ig_password": "",
    "ig_verification_code": "",

    # Tam Otomatik Zamanlayıcı (Auto-Pilot) Ayarları
    "auto_pilot_enabled": False,
    "fetch_interval_minutes": 45,
    "post_interval_minutes": 180,
    "max_posts_per_day": 6,
    "auto_translate_and_render": True,
    "auto_share_story": True,
}

DEFAULT_SOURCES = [
    # Yabancı Kaynaklar
    {
        "name": "TechCrunch",
        "category": "yabanci",
        "source_type": "rss",
        "url": "https://techcrunch.com/feed/",
        "enabled": 1
    },
    {
        "name": "The Verge",
        "category": "yabanci",
        "source_type": "rss",
        "url": "https://www.theverge.com/rss/index.xml",
        "enabled": 1
    },
    {
        "name": "Ars Technica",
        "category": "yabanci",
        "source_type": "rss",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "enabled": 1
    },
    # Yerli Kaynaklar
    {
        "name": "Webtekno",
        "category": "yerli",
        "source_type": "rss",
        "url": "https://www.webtekno.com/rss.xml",
        "enabled": 1
    },
    {
        "name": "ShiftDelete.Net",
        "category": "yerli",
        "source_type": "rss",
        "url": "https://shiftdelete.net/feed",
        "enabled": 1
    },
    {
        "name": "DonanımHaber",
        "category": "yerli",
        "source_type": "rss",
        "url": "https://www.donanimhaber.com/rss/tum/",
        "enabled": 1
    },
    {
        "name": "Technopat",
        "category": "yerli",
        "source_type": "rss",
        "url": "https://www.technopat.net/feed/",
        "enabled": 1
    },
    # Reddit & Sosyal Gündem
    {
        "name": "Reddit r/technology",
        "category": "sosyal",
        "source_type": "reddit",
        "url": "https://www.reddit.com/r/technology/hot.json?limit=15",
        "enabled": 1
    },
    {
        "name": "Reddit r/artificial",
        "category": "sosyal",
        "source_type": "reddit",
        "url": "https://www.reddit.com/r/artificial/hot.json?limit=15",
        "enabled": 1
    },
    {
        "name": "Reddit r/gadgets",
        "category": "sosyal",
        "source_type": "reddit",
        "url": "https://www.reddit.com/r/gadgets/hot.json?limit=15",
        "enabled": 1
    }
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            source_type TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            enabled INTEGER DEFAULT 1,
            last_fetched_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS news_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT NOT NULL UNIQUE,
            source_name TEXT NOT NULL,
            source_category TEXT NOT NULL,
            original_title TEXT NOT NULL,
            original_summary TEXT,
            original_url TEXT,
            image_url TEXT,
            tr_category_badge TEXT,
            tr_headline TEXT,
            tr_subheadline TEXT,
            tr_caption TEXT,
            generated_image_path TEXT,
            status TEXT DEFAULT 'pending',
            instagram_code TEXT,
            error_message TEXT,
            score INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            published_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Varsayılan ayarları yükle
    try:
        cur.execute("ALTER TABLE news_items ADD COLUMN generated_story_path TEXT")
    except Exception:
        pass

    for k, v in DEFAULT_SETTINGS.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, json.dumps(v)))

    # Varsayılan haber kaynaklarını yükle
    for src in DEFAULT_SOURCES:
        cur.execute("""
            INSERT OR IGNORE INTO sources (name, category, source_type, url, enabled)
            VALUES (?, ?, ?, ?, ?)
        """, (src["name"], src["category"], src["source_type"], src["url"], src["enabled"]))

    conn.commit()
    conn.close()


def add_log(level: str, message: str):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT INTO system_logs (level, message, created_at) VALUES (?, ?, ?)", (level, message, now))
    # Eski logları temizle (son 250 kayıt kalsın)
    cur.execute("DELETE FROM system_logs WHERE id NOT IN (SELECT id FROM system_logs ORDER BY id DESC LIMIT 250)")
    conn.commit()
    conn.close()


def get_logs(limit: int = 80) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_settings() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM settings")
    result = dict(DEFAULT_SETTINGS)
    for row in cur.fetchall():
        try:
            result[row["key"]] = json.loads(row["value"])
        except Exception:
            result[row["key"]] = row["value"]
    conn.close()

    # Ortam değişkeni (Environment Variable) tanımlıysa ve veritabanında boşsa ortam değişkenini kullan
    if not result.get("gemini_api_key") and os.environ.get("GEMINI_API_KEY"):
        result["gemini_api_key"] = os.environ["GEMINI_API_KEY"]
    if not result.get("ig_username") and os.environ.get("IG_USERNAME"):
        result["ig_username"] = os.environ["IG_USERNAME"]
    if not result.get("ig_password") and os.environ.get("IG_PASSWORD"):
        result["ig_password"] = os.environ["IG_PASSWORD"]

    return result


def get_public_settings() -> Dict[str, Any]:
    """Arayüze gönderilirken şifre ve API anahtarını maskeler (Ağ üzerinden açık şifre gitmez)."""
    s = get_settings()
    if s.get("gemini_api_key"):
        s["gemini_api_key"] = "********"
    if s.get("ig_password"):
        s["ig_password"] = "********"
    return s


def update_settings(new_settings: Dict[str, Any]):
    conn = get_conn()
    cur = conn.cursor()
    for k, v in new_settings.items():
        if k in DEFAULT_SETTINGS:
            # Maskelenmiş değer ("********") gelirse mevcut şifreyi/anahtarı koru
            if k in ("gemini_api_key", "ig_password") and (v == "********" or v == ""):
                continue
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, json.dumps(v)))
    conn.commit()
    conn.close()


def get_sources() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sources ORDER BY id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def toggle_source(source_id: int, enabled: bool):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE sources SET enabled = ? WHERE id = ?", (1 if enabled else 0, source_id))
    conn.commit()
    conn.close()


def add_source(name: str, category: str, source_type: str, url: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO sources (name, category, source_type, url, enabled) VALUES (?, ?, ?, ?, 1)",
        (name, category, source_type, url)
    )
    conn.commit()
    conn.close()


def delete_source(source_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    conn.commit()
    conn.close()


def insert_news_item(item: Dict[str, Any]) -> Optional[int]:
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cur.execute("""
            INSERT INTO news_items (
                guid, source_name, source_category, original_title,
                original_summary, original_url, image_url, score, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (
            item["guid"],
            item["source_name"],
            item["source_category"],
            item["original_title"],
            item.get("original_summary", ""),
            item.get("original_url", ""),
            item.get("image_url", ""),
            item.get("score", 0),
            now
        ))
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id
    except sqlite3.IntegrityError:
        conn.close()
        return None


def get_news_items(status: Optional[str] = None, category: Optional[str] = None, limit: int = 60) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    query = "SELECT * FROM news_items WHERE 1=1"
    params = []
    if status and status != "all":
        query += " AND status = ?"
        params.append(status)
    if category and category != "all":
        query += " AND source_category = ?"
        params.append(category)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_news_item(item_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM news_items WHERE id = ?", (item_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_news_item(item_id: int, fields: Dict[str, Any]):
    conn = get_conn()
    cur = conn.cursor()
    sets = ", ".join([f"{k} = ?" for k in fields.keys()])
    values = list(fields.values()) + [item_id]
    cur.execute(f"UPDATE news_items SET {sets} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_stats() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM news_items")
    total = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM news_items WHERE status = 'ready'")
    ready = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM news_items WHERE status = 'published'")
    published = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) as c FROM news_items WHERE status = 'pending'")
    pending = cur.fetchone()["c"]

    today_prefix = datetime.now().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) as c FROM news_items WHERE status = 'published' AND published_at LIKE ?", (f"{today_prefix}%",))
    published_today = cur.fetchone()["c"]

    conn.close()
    return {
        "total": total,
        "pending": pending,
        "ready": ready,
        "published": published,
        "published_today": published_today
    }
