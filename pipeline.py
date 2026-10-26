import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional
import database
import scraper
import ai_processor
import image_generator
import instagram_publisher

_scheduler_lock = threading.Lock()
_last_fetch_ts: float = 0.0
_last_post_ts: float = 0.0
_worker_running: bool = False


def prepare_news_item(
    item_id: int,
    force_ai: bool = True,
    template_override: Optional[str] = None,
    accent_override: Optional[str] = None
) -> Dict[str, Any]:
    """Haberi Gemini AI ile Türkçeleştirir/özetler ve 1080x1350 Instagram görselini üretir."""
    item = database.get_news_item(item_id)
    if not item:
        return {"ok": False, "message": "Haber bulunamadı."}

    try:
        if force_ai or not item.get("tr_headline"):
            ai_result = ai_processor.process_news_with_gemini(item)
            database.update_news_item(item_id, {
                "tr_category_badge": ai_result["tr_category_badge"],
                "tr_headline": ai_result["tr_headline"],
                "tr_subheadline": ai_result["tr_subheadline"],
                "tr_caption": ai_result["tr_caption"],
            })
            item = database.get_news_item(item_id)

        # Eğer haberin görseli yoksa makaleden og:image çekmeyi tekrar dene
        if not item.get("image_url") and item.get("original_url"):
            og_img = scraper.fetch_og_image(item["original_url"])
            if og_img:
                database.update_news_item(item_id, {"image_url": og_img})
                item["image_url"] = og_img

        img_path = image_generator.generate_instagram_card(
            item,
            template_override=template_override,
            accent_override=accent_override
        )
        story_path = image_generator.generate_instagram_story(
            item,
            template_override=template_override,
            accent_override=accent_override
        )
        ts_suffix = int(time.time())
        versioned_path = f"{img_path}?t={ts_suffix}"
        versioned_story_path = f"{story_path}?t={ts_suffix}"

        new_status = "published" if item.get("status") == "published" else "ready"
        database.update_news_item(item_id, {
            "generated_image_path": versioned_path,
            "generated_story_path": versioned_story_path,
            "status": new_status
        })
        updated = database.get_news_item(item_id)
        database.add_log("SUCCESS", f"Görsel ve içerik hazırlandı: #{item_id} - {updated.get('tr_headline', '')[:50]}")
        return {"ok": True, "item": updated}
    except Exception as e:
        err = str(e)
        database.add_log("ERROR", f"Haber işleme hatası (#{item_id}): {err[:160]}")
        return {"ok": False, "message": err}


def run_auto_cycle_once() -> Dict[str, Any]:
    """Tam otomatik bir döngü çalıştırır: Haber çek -> Hazırla -> Paylaş."""
    global _last_fetch_ts, _last_post_ts
    settings = database.get_settings()
    now_ts = time.time()
    summary = {"fetched": 0, "prepared": 0, "published": False}

    # 1. Haber Çekme Zamanı Kontrolü
    fetch_interval_sec = max(5, int(settings.get("fetch_interval_minutes", 45))) * 60
    if now_ts - _last_fetch_ts >= fetch_interval_sec:
        res = scraper.fetch_all_sources(max_per_source=4)
        _last_fetch_ts = now_ts
        summary["fetched"] = res.get("added", 0)

        # Yeni çekilenlerden ilk 3 tanesini otomatik görselleştir
        if settings.get("auto_translate_and_render", True):
            pending_items = database.get_news_items(status="pending", limit=3)
            for p_item in pending_items:
                prep = prepare_news_item(p_item["id"], force_ai=True)
                if prep.get("ok"):
                    summary["prepared"] += 1

    # 2. Otomatik Instagram Paylaşım Zamanı Kontrolü
    post_interval_sec = max(10, int(settings.get("post_interval_minutes", 180))) * 60
    max_per_day = int(settings.get("max_posts_per_day", 6))
    stats = database.get_stats()

    if stats["published_today"] < max_per_day and (now_ts - _last_post_ts >= post_interval_sec):
        ready_items = database.get_news_items(status="ready", limit=1)
        if not ready_items:
            # Hazırda yoksa bekleyen 1 haberi hemen hazırla
            pending = database.get_news_items(status="pending", limit=1)
            if pending:
                prep = prepare_news_item(pending[0]["id"], force_ai=True)
                if prep.get("ok"):
                    ready_items = [prep["item"]]

        if ready_items and settings.get("ig_username") and settings.get("ig_password"):
            target = ready_items[0]
            pub_res = instagram_publisher.publish_news_item(target["id"])
            _last_post_ts = now_ts
            summary["published"] = pub_res.get("ok", False)

    return summary


def _background_loop():
    global _worker_running
    _worker_running = True
    while _worker_running:
        try:
            settings = database.get_settings()
            if settings.get("auto_pilot_enabled", False):
                with _scheduler_lock:
                    run_auto_cycle_once()
        except Exception as e:
            database.add_log("ERROR", f"Otomatik zamanlayıcı döngü hatası: {str(e)[:120]}")
        time.sleep(20)


def start_background_worker():
    t = threading.Thread(target=_background_loop, daemon=True)
    t.start()


def get_scheduler_status() -> Dict[str, Any]:
    settings = database.get_settings()
    now_ts = time.time()
    fetch_int = max(5, int(settings.get("fetch_interval_minutes", 45))) * 60
    post_int = max(10, int(settings.get("post_interval_minutes", 180))) * 60

    next_fetch_sec = max(0, int(fetch_int - (now_ts - _last_fetch_ts))) if _last_fetch_ts > 0 else 0
    next_post_sec = max(0, int(post_int - (now_ts - _last_post_ts))) if _last_post_ts > 0 else 0

    return {
        "auto_pilot_enabled": bool(settings.get("auto_pilot_enabled", False)),
        "last_fetch_ago_min": int((now_ts - _last_fetch_ts) // 60) if _last_fetch_ts > 0 else None,
        "next_fetch_in_min": next_fetch_sec // 60,
        "next_post_in_min": next_post_sec // 60,
    }
