import json
import re
from typing import Dict, Any
import requests
import database
import scraper


def tr_upper(text: str) -> str:
    """Türkçe karakter duyarlı büyük harfe çevirme (i -> İ, ı -> I)."""
    if not text:
        return ""
    mapping = str.maketrans({"i": "İ", "ı": "I", "ğ": "Ğ", "ü": "Ü", "ş": "Ş", "ö": "Ö", "ç": "Ç"})
    return text.translate(mapping).upper()


def guess_category(title: str, summary: str) -> str:
    combined = (title + " " + summary).lower()
    rules = [
        (["openai", "chatgpt", "gemini", "claude", "yapay zeka", "ai ", "llm", "nvidia", "deepmind", "copilot"], "YAPAY ZEKA"),
        (["iphone", "apple", "macbook", "ios", "ipad", "tim cook"], "APPLE"),
        (["samsung", "galaxy", "android", "xiaomi", "pixel", "akıllı telefon"], "MOBİL"),
        (["tesla", "elektrikli", "otonom", "togg", "byd", "otomobil"], "OTOMOTİV"),
        (["nasa", "spacex", "uzay", "mars", "uydu", "roket", "james webb", "starlink"], "UZAY & BİLİM"),
        (["hack", "siber", "güvenlik", "veri sızıntısı", "fidye", "malware"], "SİBER GÜVENLİK"),
        (["oyun", "playstation", "xbox", "steam", "gta", "nintendo", "gpu", "rtx", "casper", "excalibur"], "OYUN & DONANIM"),
        (["instagram", "whatsapp", "tiktok", "youtube", "x ", "twitter", "meta"], "SOSYAL MEDYA"),
        (["bitcoin", "kripto", "blockchain", "ethereum"], "FİNANS & KRİPTO"),
    ]
    for keywords, badge in rules:
        if any(k in combined for k in keywords):
            return badge
    return "TEKNOLOJİ"


def free_translate_to_tr(text: str) -> str:
    """Yabancı metinleri paragraf bütünlüğünü koruyarak Türkçeye çevirir."""
    if not text:
        return ""
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = [
            ("client", "gtx"),
            ("sl", "auto"),
            ("tl", "tr"),
            ("dt", "t"),
            ("q", text[:1800]),
        ]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data and isinstance(data[0], list):
                parts = []
                for seg in data[0]:
                    if isinstance(seg, list) and seg and isinstance(seg[0], str):
                        parts.append(seg[0])
                if parts:
                    return "".join(parts).strip()
    except Exception:
        pass
    return text


def fallback_process_news(item: Dict[str, Any], settings: Dict[str, Any], full_article_text: str = "") -> Dict[str, str]:
    title = item.get("original_title", "").strip()
    summary = (full_article_text or item.get("original_summary") or "").strip()
    is_foreign = item.get("source_category") in ("yabanci", "sosyal")

    if is_foreign:
        tr_title = free_translate_to_tr(title)
        tr_body = free_translate_to_tr(summary[:1600]) if summary else ""
    else:
        tr_title = title
        tr_body = summary[:1600]

    badge = guess_category(tr_title + " " + title, tr_body + " " + summary)

    clean_headline = re.sub(r"\s*[-|–]\s*(TechCrunch|The Verge|Webtekno|ShiftDelete|DonanımHaber|Technopat).*$", "", tr_title, flags=re.I)
    words = clean_headline.split()
    if len(words) > 12:
        clean_headline = " ".join(words[:12]) + "..."

    # Cümleleri ayırıp detaylı maddeler oluştur
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", tr_body) if len(s.strip()) > 25]
    subheadline = sentences[0] if sentences else "Teknoloji dünyasında önemli gelişme yaşandı."
    if len(subheadline) > 135:
        subheadline = subheadline[:132] + "..."

    if len(sentences) >= 2:
        intro_para = sentences[0]
        bullet_lines = "\n".join([f"🔹 {s}" for s in sentences[1:6]])
        details_block = f"{intro_para}\n\n📌 Öne Çıkan Detaylar:\n{bullet_lines}"
    else:
        details_block = f"📌 {tr_body or clean_headline}"

    hashtags = settings.get("custom_hashtags", "#siberkapsul #teknoloji #yapayzeka #gündem #keşfet")
    brand_handle = settings.get("brand_handle", "@siberkapsul")

    caption = (
        f"🚨 {clean_headline}\n\n"
        f"{details_block}\n\n"
        f"💬 Siz bu gelişme hakkında ne düşünüyorsunuz? Fikirlerinizi yorumlarda paylaşmayı unutmayın! 👇\n\n"
        f"📰 Kaynak: {item.get('source_name', 'Siber Kapsül')}\n"
        f"🔔 Güncel teknoloji haberleri için {brand_handle} hesabını takip edin!\n\n"
        f"{hashtags}"
    )

    return {
        "tr_category_badge": tr_upper(badge),
        "tr_headline": tr_upper(clean_headline),
        "tr_subheadline": subheadline,
        "tr_caption": caption
    }


def process_news_with_gemini(item: Dict[str, Any]) -> Dict[str, str]:
    settings = database.get_settings()
    api_key = (settings.get("gemini_api_key") or "").strip()
    model = (settings.get("gemini_model") or "gemini-3-flash-preview").strip()
    if model in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.8-flash"):
        model = "gemini-3-flash-preview"

    tone = settings.get("ai_tone", "Merak uyandıran, akıcı, profesyonel teknoloji habercisi dili")
    hashtags = settings.get("custom_hashtags", "#siberkapsul #teknoloji #yapayzeka #gündem #bilim #keşfet")
    brand_handle = settings.get("brand_handle", "@siberkapsul")

    # Haberin orijinal linkinden tam metni çek (1 cümlelik RSS özetine bağlı kalmamak için)
    full_article = ""
    if item.get("original_url"):
        full_article = scraper.fetch_article_full_text(item["original_url"])

    combined_context = item.get("original_summary", "")
    if full_article and len(full_article) > len(combined_context):
        combined_context = full_article

    if not api_key:
        return fallback_process_news(item, settings, full_article_text=combined_context)

    prompt = f"""Sen Türkiye'nin en popüler teknoloji Instagram sayfası olan SİBER KAPSÜL ({brand_handle}) baş editörüsün.
Dil tonun: {tone}.

Aşağıdaki teknoloji haberini analiz et ve Instagram gönderisi için ÇOK DETAYLI, doyurucu ve profesyonel Türkçe içeriğe dönüştür:
Kaynak: {item.get('source_name')}
Orijinal Başlık: {item.get('original_title')}
Haberin Tam Metni / Detayları:
{combined_context[:2600]}

Lütfen SADECE geçerli bir JSON objesi döndür (markdown bloğu veya ekstra açıklama yazma). JSON şeması şu şekilde olmalı:
{{
  "tr_category_badge": "Kısa kategori etiketi (Örn: YAPAY ZEKA, APPLE, MOBİL, DONANIM, SİBER GÜVENLİK, UZAY & BİLİM, OYUN & DONANIM, OTOMOTİV, SOSYAL MEDYA)",
  "tr_headline": "Görselin üzerine büyük harflerle yazılacak, maksimum 7-10 kelimelik, çok çarpıcı ve merak uyandıran Türkçe manşet",
  "tr_subheadline": "Görselde manşetin hemen altında yer alacak, maksimum 14-18 kelimelik tek cümlelik net özet",
  "tr_caption": "Instagram için UZUN VE DETAYLI açıklama metni. Asla tek cümle yazıp bırakma! Şu yapıyı birebir uygula:\\n1) 🚨 ile başlayan çarpıcı giriş başlığı\\n2) Haberin ne olduğunu ve perde arkasını anlatan 2-3 cümlelik akıcı giriş paragrafı\\n3) '📌 Öne Çıkan Detaylar:' başlığı altında en az 4 adet '🔹' ile başlayan detaylı madde (teknik özellikler, rakamlar, neden olduğu, kimleri etkilediği)\\n4) '🔍 Neden Önemli?' başlığı altında bu gelişmenin geleceğe etkisini anlatan 2 cümlelik analiz\\n5) '💬 Siz bu gelişme hakkında ne düşünüyorsunuz? Yorumlarda buluşalım! 👇'\\n6) '📰 Kaynak: {item.get('source_name')} | 🔔 Takip: {brand_handle}' ve en altta şu etiketler: {hashtags}"
}}"""

    for target_model in [model, "gemini-3.1-flash-lite-preview", "gemini-flash-latest"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "responseMimeType": "application/json"
            }
        }
        try:
            resp = requests.post(url, json=payload, timeout=45)
            if resp.status_code != 200:
                continue

            data = resp.json()
            parts = data["candidates"][0]["content"]["parts"]
            raw_text = ""
            for p in parts:
                if "text" in p:
                    raw_text += p["text"]
            raw_text = raw_text.strip()
            raw_text = re.sub(r"^```json\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text)
            parsed = json.loads(raw_text)

            return {
                "tr_category_badge": tr_upper(parsed.get("tr_category_badge", "TEKNOLOJİ")),
                "tr_headline": tr_upper(parsed.get("tr_headline", item.get("original_title", ""))),
                "tr_subheadline": parsed.get("tr_subheadline", "").strip(),
                "tr_caption": parsed.get("tr_caption", "").strip()
            }
        except Exception as e:
            database.add_log("WARN", f"Gemini ({target_model}) denemesi: {str(e)[:90]}")
            continue

    database.add_log("WARN", "Gemini API yanıt vermedi, tam metin çeviri özetleyicisi kullanıldı.")
    return fallback_process_news(item, settings, full_article_text=combined_context)
