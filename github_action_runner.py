import json
import os
import sys
from datetime import datetime
import database
import scraper
import pipeline
import instagram_publisher

HISTORY_FILE = os.path.join(database.DATA_DIR, "published_history.json")


def load_published_guids() -> set:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data.get("published_guids", []))
        except Exception:
            pass
    return set()


def save_published_guid(guid: str, title: str, permalink: str):
    guids = list(load_published_guids())
    if guid not in guids:
        guids.append(guid)
    # Son 500 haberin kaydını tut
    guids = guids[-500:]
    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_published_title": title,
        "last_permalink": permalink,
        "published_guids": guids
    }
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def main():
    print("====================================================")
    print("🚀 SİBER KAPSÜL — GitHub Actions Otomatik Paylaşım")
    print("====================================================")

    database.init_db()
    published_guids = load_published_guids()
    print(f"ℹ️ Daha önce paylaşılan haber sayısı: {len(published_guids)}")

    # 1. Haber kaynaklarını tara
    res = scraper.fetch_all_sources(max_per_source=5)
    print(f"📡 {res['scanned']} haber tarandı.")

    # 2. Daha önce paylaşılmamış en güncel haberi seç
    all_items = database.get_news_items(status="pending", limit=50)
    target_item = None
    for item in all_items:
        if item["guid"] not in published_guids:
            # Fotoğrafı olan haberlere öncelik ver
            if item.get("image_url"):
                target_item = item
                break

    if not target_item:
        for item in all_items:
            if item["guid"] not in published_guids:
                target_item = item
                break

    if not target_item:
        print("✅ Tüm güncel haberler zaten paylaşılmış, yeni haber bekleniyor.")
        return

    print(f"🎯 Seçilen Haber: [{target_item['source_name']}] {target_item['original_title']}")

    # 3. Gemini AI ile Türkçe detaylı içerik + 1080x1350 Post + 1080x1920 Story üret
    prep = pipeline.prepare_news_item(target_item["id"], force_ai=True)
    if not prep.get("ok"):
        print(f"❌ Haber hazırlanamadı: {prep.get('message')}")
        sys.exit(1)

    prepared_item = prep["item"]
    print(f"✨ Hazırlanan Manşet: {prepared_item.get('tr_headline')}")

    # 4. Instagram'da Post + Story (Linkli) olarak paylaş
    pub_res = instagram_publisher.publish_news_item(target_item["id"])
    if not pub_res.get("ok"):
        print(f"❌ Instagram paylaşım hatası: {pub_res.get('message')}")
        sys.exit(1)

    permalink = pub_res.get("permalink", "")
    print(f"🎉 BAŞARIYLA PAYLAŞILDI! Link: {permalink}")

    # 5. Aynı haberin tekrar paylaşılmaması için geçmiş dosyasına kaydet
    save_published_guid(
        target_item["guid"],
        prepared_item.get("tr_headline") or target_item["original_title"],
        permalink
    )


if __name__ == "__main__":
    main()
