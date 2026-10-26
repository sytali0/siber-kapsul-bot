import json
import os
import shutil
import database

DOCS_DIR = os.path.join(database.BASE_DIR, "docs")
DOCS_GEN_DIR = os.path.join(DOCS_DIR, "generated")


def build_static_site():
    os.makedirs(DOCS_GEN_DIR, exist_ok=True)

    # 1. Hazır ve paylaşılan haberleri al
    all_items = database.get_news_items(limit=40)
    export_items = []

    for item in all_items:
        item_copy = dict(item)
        # Görsel yollarını docs/generated içine kopyala ve göreceli yol yap
        if item_copy.get("generated_image_path"):
            raw_rel = item_copy["generated_image_path"].split("?")[0]
            fname = os.path.basename(raw_rel)
            src_path = os.path.join(database.GENERATED_DIR, fname)
            if os.path.exists(src_path):
                shutil.copyfile(src_path, os.path.join(DOCS_GEN_DIR, fname))
                item_copy["generated_image_path"] = f"generated/{fname}"

        if item_copy.get("generated_story_path"):
            raw_story = item_copy["generated_story_path"].split("?")[0]
            sfname = os.path.basename(raw_story)
            s_src = os.path.join(database.GENERATED_DIR, sfname)
            if os.path.exists(s_src):
                shutil.copyfile(s_src, os.path.join(DOCS_GEN_DIR, sfname))
                item_copy["generated_story_path"] = f"generated/{sfname}"

        export_items.append(item_copy)

    data = {
        "stats": database.get_stats(),
        "scheduler": {
            "auto_pilot_enabled": True,
            "mode": "GitHub Actions (Her 3 Saatte Bir Otomatik)"
        },
        "settings": {
            "brand_name": "SİBER KAPSÜL",
            "brand_handle": "@siberkapsul",
            "brand_footer_text": "Detaylar açıklamada • Kaydetmeyi unutma",
            "template_style": "modern_gradient",
            "accent_color": "#00E5FF",
            "auto_pilot_enabled": True,
            "post_interval_minutes": 180,
            "max_posts_per_day": 8
        },
        "sources": database.get_sources(),
        "items": export_items,
        "logs": database.get_logs(limit=40)
    }

    with open(os.path.join(DOCS_DIR, "dashboard_data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 2. static/index.html dosyasını docs/index.html olarak uyarla (Hem GitHub Pages hem Localhost uyumlu)
    src_html_path = os.path.join(database.BASE_DIR, "static", "index.html")
    with open(src_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # GitHub Pages üzerinde çalışırken statik JSON'dan okuma desteği
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

    # Jekyll'in dosyaları yoksaymaması için .nojekyll ekle
    with open(os.path.join(DOCS_DIR, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")


if __name__ == "__main__":
    build_static_site()
    print("GitHub Pages statik kontrol paneli (docs/) oluşturuldu!")
