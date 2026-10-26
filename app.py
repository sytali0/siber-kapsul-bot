import hashlib
import hmac
import os
import time
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import database
import scraper
import pipeline
import image_generator
import instagram_publisher

database.init_db()

app = FastAPI(
    title="InstaTech Otomasyon Sistemi",
    version="1.1.0",
    docs_url=None,   # Üretim ortamında Swagger/ReDoc arayüzünü dışarıya kapat
    redoc_url=None
)

STATIC_DIR = os.path.join(database.BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/generated", StaticFiles(directory=database.GENERATED_DIR), name="generated")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Brute-force koruması için başarısız giriş sayacı
_failed_logins: Dict[str, list] = {}


def get_admin_password() -> str:
    return (os.environ.get("ADMIN_PASSWORD") or "").strip()


def make_auth_token(password: str) -> str:
    secret = password.encode("utf-8")
    return hmac.new(secret, b"instatech-admin-session-v1", hashlib.sha256).hexdigest()


def verify_admin(request: Request):
    """ADMIN_PASSWORD ortam değişkeni tanımlıysa tüm API isteklerinde yetki kontrolü yapar."""
    admin_pw = get_admin_password()
    if not admin_pw:
        # Yerel (localhost) kullanımda şifre belirlenmemişse doğrudan izin ver
        return True

    expected_token = make_auth_token(admin_pw)
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    cookie_token = (request.cookies.get("instatech_token") or "").strip()

    token = header_token or cookie_token
    if not token or not hmac.compare_digest(token, expected_token):
        raise HTTPException(status_code=401, detail="Yetkisiz erişim. Lütfen yönetici şifresi ile giriş yapın.")
    return True


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


@app.on_event("startup")
def on_startup():
    database.add_log("INFO", "InstaTech Otomasyon Sistemi başlatıldı.")
    pipeline.start_background_worker()


class LoginRequest(BaseModel):
    password: str


class CustomRenderRequest(BaseModel):
    tr_category_badge: str
    tr_headline: str
    tr_subheadline: Optional[str] = ""
    tr_caption: str
    image_url: Optional[str] = ""
    template_style: Optional[str] = None
    accent_color: Optional[str] = None


class SourceCreateRequest(BaseModel):
    name: str
    category: str
    source_type: str
    url: str


class ManualNewsRequest(BaseModel):
    title: str
    summary: Optional[str] = ""
    image_url: Optional[str] = ""
    source_name: Optional[str] = "Özel Haber"


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/health")
def api_health():
    """Bulut sunucular ve UptimeRobot için 7/24 uyanık tutma (keep-alive) uç noktası."""
    return {"status": "ok", "service": "siberkapsul-bot"}


@app.get("/api/auth/status")
def api_auth_status(request: Request):
    admin_pw = get_admin_password()
    if not admin_pw:
        return {"auth_required": False, "authenticated": True}
    expected = make_auth_token(admin_pw)
    token = (request.headers.get("X-Admin-Token") or request.cookies.get("instatech_token") or "").strip()
    is_valid = bool(token and hmac.compare_digest(token, expected))
    return {"auth_required": True, "authenticated": is_valid}


@app.post("/api/auth/login")
def api_auth_login(req: LoginRequest, request: Request, response: Response):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    attempts = [t for t in _failed_logins.get(client_ip, []) if now - t < 300]
    if len(attempts) >= 5:
        raise HTTPException(status_code=429, detail="Çok fazla başarısız giriş denemesi. Lütfen 5 dakika bekleyin.")

    admin_pw = get_admin_password()
    if not admin_pw:
        return {"ok": True, "token": "local"}

    if hmac.compare_digest(req.password.strip(), admin_pw):
        _failed_logins.pop(client_ip, None)
        token = make_auth_token(admin_pw)
        response.set_cookie(
            key="instatech_token",
            value=token,
            httponly=True,
            samesite="lax",
            max_age=86400 * 30
        )
        return {"ok": True, "token": token}

    attempts.append(now)
    _failed_logins[client_ip] = attempts
    raise HTTPException(status_code=401, detail="Hatalı yönetici şifresi!")


@app.get("/api/dashboard", dependencies=[Depends(verify_admin)])
def get_dashboard(status: str = "all", category: str = "all"):
    return {
        "stats": database.get_stats(),
        "scheduler": pipeline.get_scheduler_status(),
        "settings": database.get_public_settings(),
        "sources": database.get_sources(),
        "items": database.get_news_items(status=status, category=category, limit=60),
        "logs": database.get_logs(limit=60)
    }


@app.post("/api/fetch", dependencies=[Depends(verify_admin)])
def api_fetch_news(auto_prepare_count: int = 3):
    res = scraper.fetch_all_sources(max_per_source=5)
    prepared = 0
    for nid in res.get("new_ids", [])[:auto_prepare_count]:
        prep = pipeline.prepare_news_item(nid, force_ai=True)
        if prep.get("ok"):
            prepared += 1
    return {
        "ok": True,
        "added": res["added"],
        "scanned": res["scanned"],
        "prepared": prepared,
        "message": f"{res['scanned']} haber tarandı, {res['added']} yeni haber eklendi ve {prepared} tanesi görselleştirildi."
    }


@app.post("/api/news/{item_id}/prepare", dependencies=[Depends(verify_admin)])
def api_prepare_item(item_id: int):
    res = pipeline.prepare_news_item(item_id, force_ai=True)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message", "Hata oluştu"))
    return res


@app.post("/api/news/{item_id}/custom-render", dependencies=[Depends(verify_admin)])
def api_custom_render(item_id: int, req: CustomRenderRequest):
    item = database.get_news_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Haber bulunamadı")

    database.update_news_item(item_id, {
        "tr_category_badge": req.tr_category_badge.strip(),
        "tr_headline": req.tr_headline.strip(),
        "tr_subheadline": (req.tr_subheadline or "").strip(),
        "tr_caption": req.tr_caption.strip(),
        "image_url": (req.image_url or item.get("image_url") or "").strip(),
    })
    updated_item = database.get_news_item(item_id)
    img_path = image_generator.generate_instagram_card(
        updated_item,
        template_override=req.template_style,
        accent_override=req.accent_color
    )
    story_path = image_generator.generate_instagram_story(
        updated_item,
        template_override=req.template_style,
        accent_override=req.accent_color
    )
    ts = int(time.time())
    versioned_path = f"{img_path}?t={ts}"
    versioned_story = f"{story_path}?t={ts}"
    new_status = "published" if updated_item.get("status") == "published" else "ready"
    database.update_news_item(item_id, {
        "generated_image_path": versioned_path,
        "generated_story_path": versioned_story,
        "status": new_status
    })
    return {"ok": True, "item": database.get_news_item(item_id)}


@app.post("/api/news/{item_id}/publish", dependencies=[Depends(verify_admin)])
def api_publish_item(item_id: int):
    item = database.get_news_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Haber bulunamadı")
    if not item.get("generated_image_path"):
        prep = pipeline.prepare_news_item(item_id, force_ai=True)
        if not prep.get("ok"):
            raise HTTPException(status_code=400, detail=prep.get("message", "Görsel üretilemedi"))
    res = instagram_publisher.publish_news_item(item_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message", "Instagram paylaşım hatası"))
    return res


@app.post("/api/news/{item_id}/publish-story", dependencies=[Depends(verify_admin)])
def api_publish_story(item_id: int):
    item = database.get_news_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Haber bulunamadı")
    res = instagram_publisher.publish_story_item(item_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("message", "Story paylaşım hatası"))
    return res


@app.delete("/api/news/{item_id}", dependencies=[Depends(verify_admin)])
def api_delete_item(item_id: int):
    conn = database.get_conn()
    conn.execute("DELETE FROM news_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/news/manual", dependencies=[Depends(verify_admin)])
def api_add_manual_news(req: ManualNewsRequest):
    guid = hashlib.md5(f"{req.title}-{time.time()}".encode("utf-8")).hexdigest()
    new_id = database.insert_news_item({
        "guid": guid,
        "source_name": req.source_name or "Özel Haber",
        "source_category": "yerli",
        "original_title": req.title,
        "original_summary": req.summary or req.title,
        "original_url": "",
        "image_url": req.image_url or "",
        "score": 999
    })
    if new_id:
        prep = pipeline.prepare_news_item(new_id, force_ai=True)
        return prep
    raise HTTPException(status_code=400, detail="Haber eklenemedi")


@app.post("/api/settings", dependencies=[Depends(verify_admin)])
def api_update_settings(new_settings: dict):
    database.update_settings(new_settings)
    database.add_log("INFO", "Sistem ve otomasyon ayarları güncellendi.")
    return {"ok": True, "settings": database.get_public_settings()}


@app.post("/api/instagram/test", dependencies=[Depends(verify_admin)])
def api_test_instagram():
    return instagram_publisher.test_instagram_connection()


@app.get("/api/instagram/session-export", dependencies=[Depends(verify_admin)])
def api_export_ig_session():
    """Bulut sunucuya taşırken IG_SESSION_JSON ortam değişkenine yapıştırmak için oturum verisini döndürür."""
    if os.path.exists(instagram_publisher.SESSION_FILE):
        with open(instagram_publisher.SESSION_FILE, "r", encoding="utf-8") as f:
            return {"ok": True, "session_json": f.read().strip()}
    return {"ok": False, "message": "Henüz kayıtlı bir Instagram oturum dosyası bulunamadı."}


@app.post("/api/sources/{source_id}/toggle", dependencies=[Depends(verify_admin)])
def api_toggle_source(source_id: int, payload: dict):
    database.toggle_source(source_id, bool(payload.get("enabled", True)))
    return {"ok": True, "sources": database.get_sources()}


@app.post("/api/sources", dependencies=[Depends(verify_admin)])
def api_add_source(req: SourceCreateRequest):
    database.add_source(req.name.strip(), req.category, req.source_type, req.url.strip())
    database.add_log("INFO", f"Yeni haber kaynağı eklendi: {req.name}")
    return {"ok": True, "sources": database.get_sources()}


@app.delete("/api/sources/{source_id}", dependencies=[Depends(verify_admin)])
def api_delete_source(source_id: int):
    database.delete_source(source_id)
    return {"ok": True, "sources": database.get_sources()}
