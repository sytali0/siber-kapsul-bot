import os
import threading
from datetime import datetime
from typing import Dict, Any, Optional
import database

SESSION_FILE = os.path.join(database.DATA_DIR, "ig_session.json")

_client_lock = threading.Lock()
_cached_client = None
_cached_username = None


def get_instagram_client(force_relogin: bool = False):
    """instagrapi oturumunu bellekte ve diskte tutar; her paylaşımda tekrar login yaparak engele takılmaz."""
    global _cached_client, _cached_username
    try:
        from instagrapi import Client
    except ImportError:
        raise RuntimeError("instagrapi kütüphanesi yüklü değil.")

    settings = database.get_settings()
    username = (settings.get("ig_username") or "").strip()
    password = (settings.get("ig_password") or "").strip()
    verification_code = (settings.get("ig_verification_code") or "").strip()

    if not username or not password:
        raise ValueError("Instagram kullanıcı adı ve şifresi henüz Ayarlar sekmesinden girilmemiş.")

    with _client_lock:
        if _cached_client is not None and _cached_username == username and not force_relogin:
            return _cached_client

        cl = Client()
        cl.delay_range = [1, 2]
        cl.request_timeout = 25

        # Terminalde input() bekleyerek sunucuyu dondurmasını engelle
        def _non_blocking_challenge_handler(uname, choice=None):
            code = (database.get_settings().get("ig_verification_code") or "").strip()
            if code:
                return code
            raise RuntimeError(
                "Instagram güvenlik doğrulama kodu istedi. Lütfen telefonunuza/e-postanıza gelen kodu Ayarlar sekmesindeki '2 Adımlı Doğrulama Kodu' kutusuna yazıp tekrar deneyin."
            )

        cl.challenge_code_handler = _non_blocking_challenge_handler

        # Bulut sunucuda IG_SESSION_JSON ortam değişkeni tanımlıysa oturum dosyasını otomatik oluştur
        env_session_json = (os.environ.get("IG_SESSION_JSON") or "").strip()
        if env_session_json and not os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "w", encoding="utf-8") as sf:
                    sf.write(env_session_json)
            except Exception:
                pass

        if os.path.exists(SESSION_FILE) and not force_relogin:
            try:
                cl.load_settings(SESSION_FILE)
                sessionid = cl.settings.get("authorization_data", {}).get("sessionid")
                if sessionid:
                    _cached_client = cl
                    _cached_username = username
                    return cl
            except Exception as e:
                database.add_log("INFO", f"Kayıtlı oturum yenileniyor ({str(e)[:60]})...")

        if verification_code:
            cl.login(username, password, verification_code=verification_code)
        else:
            cl.login(username, password)

        cl.dump_settings(SESSION_FILE)
        _cached_client = cl
        _cached_username = username
        return cl


def test_instagram_connection() -> Dict[str, Any]:
    try:
        cl = get_instagram_client(force_relogin=False)
        info = cl.account_info()
        msg = f"Instagram bağlantısı aktif! Hesap: @{info.username} ({info.full_name})"
        database.add_log("SUCCESS", msg)
        return {"ok": True, "username": info.username, "full_name": info.full_name, "message": msg}
    except Exception as e:
        err_msg = f"Instagram giriş hatası: {str(e)}"
        database.add_log("ERROR", err_msg)
        return {"ok": False, "message": err_msg}


def publish_story_item(item_id: int, cl=None) -> Dict[str, Any]:
    """Haberi 1080x1920 Instagram Hikaye (Story) olarak ve üzerine tıklanabilir kaynak linki ekleyerek paylaşır."""
    item = database.get_news_item(item_id)
    if not item:
        return {"ok": False, "message": "Haber bulunamadı."}

    import image_generator
    story_rel_path = item.get("generated_story_path")
    if not story_rel_path:
        story_rel_path = image_generator.generate_instagram_story(item)
        database.update_news_item(item_id, {"generated_story_path": story_rel_path})

    filename = os.path.basename(story_rel_path.split("?")[0])
    abs_story_path = os.path.join(database.GENERATED_DIR, filename)

    if not os.path.exists(abs_story_path):
        story_rel_path = image_generator.generate_instagram_story(item)
        filename = os.path.basename(story_rel_path.split("?")[0])
        abs_story_path = os.path.join(database.GENERATED_DIR, filename)

    source_url = (item.get("original_url") or "").strip()

    try:
        database.add_log("INFO", f"Instagram Story + Link yükleniyor: #{item_id} ({source_url[:50] or 'Siber Kapsül'})...")
        if cl is None:
            cl = get_instagram_client()

        story_links = []
        if source_url and source_url.startswith("http"):
            try:
                from instagrapi.types import StoryLink
                story_links = [StoryLink(webUri=source_url, x=0.5, y=0.80, width=0.68, height=0.09)]
            except Exception:
                story_links = []

        media = None
        if story_links:
            try:
                media = cl.photo_upload_to_story(path=abs_story_path, links=story_links)
            except Exception as link_err:
                database.add_log("WARN", f"Story link çıkartması eklenemedi ({str(link_err)[:80]}), görsel olarak paylaşılıyor...")
                media = cl.photo_upload_to_story(path=abs_story_path)
        else:
            media = cl.photo_upload_to_story(path=abs_story_path)

        code = getattr(media, "code", "") or str(getattr(media, "pk", ""))
        database.add_log("SUCCESS", f"Instagram Story (+ Kaynak Linki) başarıyla paylaşıldı! (#{item_id})")
        return {"ok": True, "code": code, "message": "Story ve kaynak linki başarıyla paylaşıldı!"}
    except Exception as e:
        err_str = str(e)
        database.add_log("ERROR", f"Story paylaşım hatası (#{item_id}): {err_str[:200]}")
        return {"ok": False, "message": err_str}


def publish_news_item(item_id: int) -> Dict[str, Any]:
    item = database.get_news_item(item_id)
    if not item:
        return {"ok": False, "message": "Haber bulunamadı."}

    img_rel_path = item.get("generated_image_path")
    if not img_rel_path:
        return {"ok": False, "message": "Bu haber için henüz görsel üretilmemiş."}

    filename = os.path.basename(img_rel_path.split("?")[0])
    abs_img_path = os.path.join(database.GENERATED_DIR, filename)

    if not os.path.exists(abs_img_path):
        return {"ok": False, "message": f"Görsel dosyası bulunamadı: {abs_img_path}"}

    caption = item.get("tr_caption") or item.get("tr_headline") or item.get("original_title")
    settings = database.get_settings()

    try:
        database.add_log("INFO", f"Instagram'a yükleniyor: '{item.get('tr_headline') or item.get('original_title')[:45]}'...")
        cl = get_instagram_client()
        try:
            media = cl.photo_upload(path=abs_img_path, caption=caption)
        except Exception as first_err:
            if "login" in str(first_err).lower() or "session" in str(first_err).lower():
                database.add_log("INFO", "Oturum süresi dolmuş, yeniden giriş yapılıp paylaşılıyor...")
                cl = get_instagram_client(force_relogin=True)
                media = cl.photo_upload(path=abs_img_path, caption=caption)
            else:
                raise first_err

        code = getattr(media, "code", "") or str(getattr(media, "pk", ""))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        database.update_news_item(item_id, {
            "status": "published",
            "instagram_code": code,
            "published_at": now,
            "error_message": ""
        })
        permalink = f"https://www.instagram.com/p/{code}/" if code else ""
        database.add_log("SUCCESS", f"Instagram Post başarıyla paylaşıldı! {permalink}")

        story_msg = ""
        if settings.get("auto_share_story", True):
            st_res = publish_story_item(item_id, cl=cl)
            if st_res.get("ok"):
                story_msg = " + Story & Kaynak Linki paylaşıldı!"

        return {
            "ok": True,
            "code": code,
            "permalink": permalink,
            "message": f"Gönderi Instagram'da paylaşıldı!{story_msg}"
        }
    except Exception as e:
        err_str = str(e)
        database.update_news_item(item_id, {
            "status": "failed",
            "error_message": err_str[:250]
        })
        database.add_log("ERROR", f"Paylaşım başarısız (#{item_id}): {err_str[:200]}")
        return {"ok": False, "message": err_str}
