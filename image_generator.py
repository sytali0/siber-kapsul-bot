import io
import math
import os
from typing import Dict, Any, List, Tuple, Optional
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import database

CANVAS_W = 1080
CANVAS_H = 1350


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    hex_color = (hex_color or "#00E5FF").lstrip("#")
    if len(hex_color) != 6:
        return (0, 229, 255)
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Hem Windows hem de Linux bulut sunucularda Türkçe karakter destekli font yükler."""
    win_fonts_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    win_candidates = (
        ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "verdanab.ttf", "bahnschrift.ttf"]
        if bold else
        ["segoeui.ttf", "arial.ttf", "calibri.ttf", "verdana.ttf"]
    )
    for fname in win_candidates:
        fpath = os.path.join(win_fonts_dir, fname)
        if os.path.exists(fpath):
            try:
                return ImageFont.truetype(fpath, size=size)
            except Exception:
                continue

    linux_candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]
        if bold else
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]
    )
    for lpath in linux_candidates:
        if os.path.exists(lpath):
            try:
                return ImageFont.truetype(lpath, size=size)
            except Exception:
                continue

    return ImageFont.load_default()


def create_fallback_tech_image(width: int, height: int, accent_rgb: Tuple[int, int, int]) -> Image.Image:
    """Haberde görsel yoksa yüksek kaliteli siber teknoloji arka planını kullanır."""
    default_bg_path = os.path.join(database.GENERATED_DIR, "welcome_bg.jpg")
    if os.path.exists(default_bg_path):
        try:
            raw_img = Image.open(default_bg_path).convert("RGB")
            src_w, src_h = raw_img.size
            target_ratio = width / height
            src_ratio = src_w / src_h
            if src_ratio > target_ratio:
                new_w = int(src_h * target_ratio)
                left = (src_w - new_w) // 2
                img = raw_img.crop((left, 0, left + new_w, src_h))
            else:
                new_h = int(src_w / target_ratio)
                top = (src_h - new_h) // 2
                img = raw_img.crop((0, top, src_w, top + new_h))
            return img.resize((width, height), Image.Resampling.LANCZOS)
        except Exception:
            pass

    img = Image.new("RGB", (width, height), (10, 14, 24))
    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = int(width * 0.5), int(height * 0.38)
    for r in range(520, 20, -25):
        alpha = int(38 * (1 - r / 520))
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], alpha)
        )
    return img


def find_topic_image_url(query: str) -> Optional[str]:
    """Görseli olmayan haberler için başlığa uygun gerçek haber fotoğrafı bulur."""
    if not query:
        return None
    try:
        import urllib.parse
        import re
        q = urllib.parse.quote(query[:80] + " technology")
        url = f"https://www.bing.com/images/search?q={q}&form=HDRSC2&first=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            matches = re.findall(r'murl&quot;:&quot;(https?://[^&]+?\.(?:jpg|jpeg|png|webp))&quot;', resp.text)
            for m in matches[:4]:
                if "bing.net" not in m:
                    return m
    except Exception:
        pass
    return None


def download_and_crop_photo(image_url: str, target_w: int, target_h: int, accent_rgb: Tuple[int, int, int], fallback_query: str = "") -> Image.Image:
    raw_img = None
    clean_url = (image_url or "").strip()

    # /generated/... şeklinde yerel web yolu ise dosya yoluna çevir
    if clean_url.startswith("/generated/"):
        fname = os.path.basename(clean_url.split("?")[0])
        clean_url = os.path.join(database.GENERATED_DIR, fname)

    if clean_url and os.path.exists(clean_url):
        try:
            raw_img = Image.open(clean_url).convert("RGB")
        except Exception:
            raw_img = None

    if raw_img is None and (not clean_url or not clean_url.startswith("http")) and fallback_query:
        found_url = find_topic_image_url(fallback_query)
        if found_url:
            clean_url = found_url

    if raw_img is None and clean_url and clean_url.startswith("http"):
        for attempt_url in [clean_url, find_topic_image_url(fallback_query) if fallback_query else None]:
            if not attempt_url:
                continue
            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(attempt_url)
                referer = f"{parsed.scheme}://{parsed.netloc}/"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Referer": referer,
                }
                resp = requests.get(attempt_url, headers=headers, timeout=12)
                if resp.status_code == 200 and len(resp.content) > 1500:
                    raw_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    break
            except Exception:
                continue

    if raw_img is not None:
        try:
            src_w, src_h = raw_img.size
            target_ratio = target_w / target_h
            src_ratio = src_w / src_h

            if src_ratio > target_ratio:
                new_w = int(src_h * target_ratio)
                left = (src_w - new_w) // 2
                img = raw_img.crop((left, 0, left + new_w, src_h))
            else:
                new_h = int(src_w / target_ratio)
                top = (src_h - new_h) // 2
                img = raw_img.crop((0, top, src_w, top + new_h))

            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
            img = ImageEnhance.Contrast(img).enhance(1.08)
            img = ImageEnhance.Color(img).enhance(1.10)
            return img
        except Exception:
            pass
    return create_fallback_tech_image(target_w, target_h, accent_rgb)


def wrap_text_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def draw_footer(draw: ImageDraw.ImageDraw, settings: Dict[str, Any], accent_rgb: Tuple[int, int, int], y_pos: int):
    brand_handle = settings.get("brand_handle", "@teknolojigundemi")
    footer_text = settings.get("brand_footer_text", "Detaylar açıklamada • Kaydetmeyi unutma")

    font_handle = load_font(28, bold=True)
    font_footer = load_font(23, bold=False)

    # Alt ayırıcı ince çizgi
    draw.line([(72, y_pos - 26), (CANVAS_W - 72, y_pos - 26)], fill=(255, 255, 255, 35), width=2)

    # Sol: Marka ikonu + @handle
    draw.rounded_rectangle((72, y_pos - 2, 110, y_pos + 36), radius=10, fill=accent_rgb)
    # Küçük şimşek / teknoloji nokta sembolü
    draw.ellipse((85, y_pos + 11, 97, y_pos + 23), fill=(10, 12, 18))

    draw.text((126, y_pos - 1), brand_handle, font=font_handle, fill=(255, 255, 255))

    # Sağ: Footer metni + Kaydet ikonu
    f_bbox = draw.textbbox((0, 0), footer_text, font=font_footer)
    f_w = f_bbox[2] - f_bbox[0]
    draw.text((CANVAS_W - 125 - f_w, y_pos + 3), footer_text, font=font_footer, fill=(180, 192, 210))

    # Kaydet (Bookmark) ikonu çizimi
    bx1, by1, bx2, by2 = CANVAS_W - 102, y_pos - 2, CANVAS_W - 72, y_pos + 36
    draw.polygon(
        [(bx1, by1), (bx2, by1), (bx2, by2), ((bx1 + bx2) // 2, by2 - 10), (bx1, by2)],
        outline=accent_rgb,
        width=3
    )


def render_modern_gradient(item: Dict[str, Any], settings: Dict[str, Any], accent_rgb: Tuple[int, int, int]) -> Image.Image:
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (9, 11, 16, 255))

    # Üst bölüm haber fotoğrafı (1080 x 960)
    photo_h = 960
    photo = download_and_crop_photo(item.get("image_url", ""), CANVAS_W, photo_h, accent_rgb, fallback_query=item.get("original_title", "")).convert("RGBA")
    canvas.paste(photo, (0, 0))

    # Çok aşamalı sinematik karanlık gradyan
    gradient = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient)

    # Üst vignette (Üst barın net okunması için)
    for y in range(0, 220):
        alpha = int(170 * (1 - y / 220) ** 1.6)
        g_draw.line([(0, y), (CANVAS_W, y)], fill=(8, 10, 15, alpha))

    # Alt geçiş gradyanı (y=360'tan y=960'a kadar yumuşak kararma)
    grad_start = 340
    for y in range(grad_start, CANVAS_H):
        if y < photo_h:
            progress = (y - grad_start) / (photo_h - grad_start)
            alpha = int(255 * (progress ** 1.45))
        else:
            alpha = 255
        g_draw.line([(0, y), (CANVAS_W, y)], fill=(9, 11, 16, alpha))

    canvas = Image.alpha_composite(canvas, gradient)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Üst Başlık Barı (Sol: Marka Adı, Sağ: Haber Kaynağı)
    brand_name = settings.get("brand_name", "TEKNOLOJİ GÜNDEMİ")
    font_top = load_font(24, bold=True)
    tb_bbox = draw.textbbox((0, 0), brand_name, font=font_top)
    tb_w = tb_bbox[2] - tb_bbox[0]

    draw.rounded_rectangle((68, 52, 136 + tb_w, 104), radius=26, fill=(12, 16, 24, 205), outline=(255, 255, 255, 45), width=2)
    draw.ellipse((86, 71, 100, 85), fill=accent_rgb)
    draw.text((112, 62), brand_name, font=font_top, fill=(255, 255, 255))

    if settings.get("show_source_credit", True) and item.get("source_name"):
        src_label = item["source_name"].upper()
        sb_bbox = draw.textbbox((0, 0), src_label, font=font_top)
        sb_w = sb_bbox[2] - sb_bbox[0]
        draw.rounded_rectangle(
            (CANVAS_W - 108 - sb_w, 52, CANVAS_W - 68, 104),
            radius=26,
            fill=(12, 16, 24, 195),
            outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 120),
            width=2
        )
        draw.text((CANVAS_W - 88 - sb_w, 62), src_label, font=font_top, fill=accent_rgb)

    # Manşet ve Alt Başlık Alanı
    headline = (item.get("tr_headline") or item.get("original_title") or "TEKNOLOJİ GÜNDEMİ").strip()
    subheadline = (item.get("tr_subheadline") or item.get("original_summary") or "").strip()
    if len(subheadline) > 140:
        subheadline = subheadline[:137] + "..."
    badge_text = (item.get("tr_category_badge") or "TEKNOLOJİ").strip()

    # Dinamik manşet font boyutu
    font_size = 58 if len(headline) < 55 else (50 if len(headline) < 85 else 44)
    font_headline = load_font(font_size, bold=True)
    headline_lines = wrap_text_lines(draw, headline, font_headline, max_width=CANVAS_W - 170)
    if len(headline_lines) > 4:
        headline_lines = headline_lines[:4]
        headline_lines[-1] = headline_lines[-1][:max(3, len(headline_lines[-1]) - 3)] + "..."

    line_h = int(font_size * 1.24)
    total_headline_h = len(headline_lines) * line_h

    font_sub = load_font(29, bold=False)
    sub_lines = wrap_text_lines(draw, subheadline, font_sub, max_width=CANVAS_W - 150)[:2] if subheadline else []
    sub_h = len(sub_lines) * 38

    # Dikey hizalama (Alt kısımdan yukarı doğru hesapla)
    bottom_anchor = 1190
    sub_y = bottom_anchor - sub_h
    headline_y = sub_y - total_headline_h - (24 if sub_lines else 0)
    badge_y = headline_y - 72

    # Kategori Rozeti (Badge)
    font_badge = load_font(25, bold=True)
    b_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    b_w = b_bbox[2] - b_bbox[0]
    draw.rounded_rectangle(
        (72, badge_y, 72 + b_w + 48, badge_y + 48),
        radius=12,
        fill=accent_rgb
    )
    draw.text((96, badge_y + 8), badge_text, font=font_badge, fill=(8, 10, 16))

    # Manşet Sol Vurgu Çubuğu
    draw.rounded_rectangle(
        (72, headline_y + 8, 84, headline_y + total_headline_h - 6),
        radius=6,
        fill=accent_rgb
    )

    # Manşet Metni
    curr_y = headline_y
    for line in headline_lines:
        # Gölge
        draw.text((106, curr_y + 3), line, font=font_headline, fill=(0, 0, 0, 190))
        draw.text((104, curr_y), line, font=font_headline, fill=(255, 255, 255))
        curr_y += line_h

    # Alt Başlık Metni
    curr_sub_y = headline_y + total_headline_h + 20
    for sline in sub_lines:
        draw.text((74, curr_sub_y), sline, font=font_sub, fill=(203, 213, 225))
        curr_sub_y += 38

    # Alt bilgi (Footer)
    draw_footer(draw, settings, accent_rgb, y_pos=1255)
    return canvas.convert("RGB")


def render_cyber_frame(item: Dict[str, Any], settings: Dict[str, Any], accent_rgb: Tuple[int, int, int]) -> Image.Image:
    canvas = create_fallback_tech_image(CANVAS_W, CANVAS_H, accent_rgb).convert("RGBA")
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (7, 10, 17, 215))
    canvas = Image.alpha_composite(canvas, overlay)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Dış siber çerçeve
    draw.rounded_rectangle(
        (36, 36, CANVAS_W - 36, CANVAS_H - 36),
        radius=28,
        outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 95),
        width=3
    )

    # Üst Bar
    brand_name = settings.get("brand_name", "TEKNOLOJİ GÜNDEMİ")
    font_top = load_font(26, bold=True)
    draw.ellipse((72, 74, 90, 92), fill=accent_rgb)
    draw.text((104, 66), brand_name, font=font_top, fill=(255, 255, 255))

    badge_text = (item.get("tr_category_badge") or "TEKNOLOJİ").strip()
    b_bbox = draw.textbbox((0, 0), badge_text, font=font_top)
    b_w = b_bbox[2] - b_bbox[0]
    draw.rounded_rectangle((CANVAS_W - 112 - b_w, 60, CANVAS_W - 72, 108), radius=12, fill=accent_rgb)
    draw.text((CANVAS_W - 92 - b_w, 68), badge_text, font=font_top, fill=(8, 10, 16))

    # Çerçeveli Haber Görseli
    img_w, img_h = CANVAS_W - 144, 650
    photo = download_and_crop_photo(item.get("image_url", ""), img_w, img_h, accent_rgb, fallback_query=item.get("original_title", "")).convert("RGBA")

    mask = Image.new("L", (img_w, img_h), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle((0, 0, img_w, img_h), radius=24, fill=255)

    canvas.paste(photo, (72, 132), mask)
    draw.rounded_rectangle((72, 132, 72 + img_w, 132 + img_h), radius=24, outline=accent_rgb, width=3)

    # Manşet
    headline = (item.get("tr_headline") or item.get("original_title") or "TEKNOLOJİ GÜNDEMİ").strip()
    subheadline = (item.get("tr_subheadline") or item.get("original_summary") or "").strip()

    font_size = 52 if len(headline) < 65 else 44
    font_headline = load_font(font_size, bold=True)
    lines = wrap_text_lines(draw, headline, font_headline, max_width=CANVAS_W - 144)[:4]

    curr_y = 820
    for line in lines:
        draw.text((72, curr_y), line, font=font_headline, fill=(255, 255, 255))
        curr_y += int(font_size * 1.24)

    if subheadline:
        font_sub = load_font(27, bold=False)
        sub_lines = wrap_text_lines(draw, subheadline, font_sub, max_width=CANVAS_W - 144)[:2]
        curr_y += 14
        for sline in sub_lines:
            draw.text((72, curr_y), sline, font=font_sub, fill=(185, 198, 218))
            curr_y += 36

    draw_footer(draw, settings, accent_rgb, y_pos=1250)
    return canvas.convert("RGB")


def render_minimal_magazine(item: Dict[str, Any], settings: Dict[str, Any], accent_rgb: Tuple[int, int, int]) -> Image.Image:
    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (14, 17, 23, 255))

    # Üst fotoğraf (1080 x 790)
    photo = download_and_crop_photo(item.get("image_url", ""), CANVAS_W, 790, accent_rgb, fallback_query=item.get("original_title", "")).convert("RGBA")
    canvas.paste(photo, (0, 0))

    draw = ImageDraw.Draw(canvas, "RGBA")
    # Alt Editorial Kart
    draw.rounded_rectangle((44, 710, CANVAS_W - 44, CANVAS_H - 40), radius=34, fill=(16, 20, 28, 250), outline=(255, 255, 255, 30), width=2)

    badge_text = (item.get("tr_category_badge") or "TEKNOLOJİ").strip()
    font_badge = load_font(24, bold=True)
    b_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    b_w = b_bbox[2] - b_bbox[0]
    draw.rounded_rectangle((84, 684, 84 + b_w + 48, 736), radius=14, fill=accent_rgb)
    draw.text((108, 694), badge_text, font=font_badge, fill=(10, 12, 18))

    headline = (item.get("tr_headline") or item.get("original_title") or "TEKNOLOJİ GÜNDEMİ").strip()
    subheadline = (item.get("tr_subheadline") or item.get("original_summary") or "").strip()

    font_size = 52 if len(headline) < 65 else 44
    font_headline = load_font(font_size, bold=True)
    lines = wrap_text_lines(draw, headline, font_headline, max_width=CANVAS_W - 170)[:4]

    curr_y = 768
    for line in lines:
        draw.text((84, curr_y), line, font=font_headline, fill=(255, 255, 255))
        curr_y += int(font_size * 1.24)

    if subheadline:
        font_sub = load_font(27, bold=False)
        sub_lines = wrap_text_lines(draw, subheadline, font_sub, max_width=CANVAS_W - 170)[:2]
        curr_y += 14
        for sline in sub_lines:
            draw.text((84, curr_y), sline, font=font_sub, fill=(185, 198, 218))
            curr_y += 36

    draw_footer(draw, settings, accent_rgb, y_pos=1242)
    return canvas.convert("RGB")


def generate_instagram_story(
    item: Dict[str, Any],
    template_override: Optional[str] = None,
    accent_override: Optional[str] = None
) -> str:
    """1080x1920 (9:16) boyutunda Instagram Hikaye (Story) görseli üretir."""
    settings = database.get_settings()
    accent_hex = accent_override or settings.get("accent_color", "#00E5FF")
    accent_rgb = hex_to_rgb(accent_hex)

    story_w, story_h = 1080, 1920
    canvas = Image.new("RGBA", (story_w, story_h), (8, 10, 16, 255))

    # Arka planda haber fotoğrafının bulanıklaştırılmış ve karartılmış atmosferik hali
    bg_photo = download_and_crop_photo(
        item.get("image_url", ""),
        story_w,
        story_h,
        accent_rgb,
        fallback_query=item.get("original_title", "")
    ).resize((story_w, story_h), Image.Resampling.LANCZOS)
    bg_blurred = bg_photo.filter(ImageFilter.GaussianBlur(radius=28)).convert("RGBA")
    dark_overlay = Image.new("RGBA", (story_w, story_h), (7, 10, 16, 218))
    canvas = Image.alpha_composite(bg_blurred, dark_overlay)
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Dış ince siber çerçeve
    draw.rounded_rectangle(
        (42, 130, story_w - 42, story_h - 140),
        radius=36,
        outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 75),
        width=2
    )

    # Üst Bar (Instagram Story üst profil alanının hemen altında: y=165)
    brand_name = settings.get("brand_name", "SİBER KAPSÜL")
    font_top = load_font(25, bold=True)
    tb_bbox = draw.textbbox((0, 0), brand_name, font=font_top)
    tb_w = tb_bbox[2] - tb_bbox[0]

    draw.rounded_rectangle((76, 166, 146 + tb_w, 218), radius=26, fill=(12, 16, 24, 220), outline=(255, 255, 255, 50), width=2)
    draw.ellipse((96, 185, 110, 199), fill=accent_rgb)
    draw.text((122, 176), brand_name, font=font_top, fill=(255, 255, 255))

    if item.get("source_name"):
        src_label = item["source_name"].upper()
        sb_bbox = draw.textbbox((0, 0), src_label, font=font_top)
        sb_w = sb_bbox[2] - sb_bbox[0]
        draw.rounded_rectangle(
            (story_w - 116 - sb_w, 166, story_w - 76, 218),
            radius=26,
            fill=(12, 16, 24, 220),
            outline=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 140),
            width=2
        )
        draw.text((story_w - 96 - sb_w, 176), src_label, font=font_top, fill=accent_rgb)

    # Ana Haber Fotoğrafı (Çerçeveli: 928 x 680)
    img_w, img_h = story_w - 152, 680
    main_photo = download_and_crop_photo(
        item.get("image_url", ""),
        img_w,
        img_h,
        accent_rgb,
        fallback_query=item.get("original_title", "")
    ).convert("RGBA")

    mask = Image.new("L", (img_w, img_h), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle((0, 0, img_w, img_h), radius=28, fill=255)

    canvas.paste(main_photo, (76, 250), mask)
    draw.rounded_rectangle((76, 250, 76 + img_w, 250 + img_h), radius=28, outline=accent_rgb, width=3)

    # Kategori Rozeti
    badge_text = (item.get("tr_category_badge") or "TEKNOLOJİ").strip()
    font_badge = load_font(26, bold=True)
    b_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    b_w = b_bbox[2] - b_bbox[0]
    badge_y = 968
    draw.rounded_rectangle((76, badge_y, 76 + b_w + 52, badge_y + 50), radius=14, fill=accent_rgb)
    draw.text((102, badge_y + 9), badge_text, font=font_badge, fill=(8, 10, 16))

    # Manşet
    headline = (item.get("tr_headline") or item.get("original_title") or "SİBER KAPSÜL").strip()
    font_size = 54 if len(headline) < 60 else 46
    font_headline = load_font(font_size, bold=True)
    h_lines = wrap_text_lines(draw, headline, font_headline, max_width=story_w - 184)[:4]
    line_h = int(font_size * 1.24)
    total_h = len(h_lines) * line_h

    headline_y = 1044
    draw.rounded_rectangle((76, headline_y + 8, 88, headline_y + total_h - 6), radius=6, fill=accent_rgb)

    curr_y = headline_y
    for line in h_lines:
        draw.text((110, curr_y + 3), line, font=font_headline, fill=(0, 0, 0, 190))
        draw.text((108, curr_y), line, font=font_headline, fill=(255, 255, 255))
        curr_y += line_h

    # Alt Başlık Özeti
    subheadline = (item.get("tr_subheadline") or item.get("original_summary") or "").strip()
    if subheadline:
        font_sub = load_font(28, bold=False)
        sub_lines = wrap_text_lines(draw, subheadline, font_sub, max_width=story_w - 160)[:2]
        curr_y += 18
        for sline in sub_lines:
            draw.text((78, curr_y), sline, font=font_sub, fill=(203, 213, 225))
            curr_y += 38

    # Kaynak Link Kutusu (Instagram Tıklanabilir Link Sticker Alanı: y=1480..1605, merkez y=1542 -> 0.80)
    import urllib.parse
    orig_url = (item.get("original_url") or "").strip()
    domain = urllib.parse.urlparse(orig_url).netloc.replace("www.", "") if orig_url else "siberkapsul"
    link_box_y1, link_box_y2 = 1475, 1605
    draw.rounded_rectangle(
        (130, link_box_y1, story_w - 130, link_box_y2),
        radius=32,
        fill=(14, 22, 36, 240),
        outline=accent_rgb,
        width=3
    )
    font_link_title = load_font(26, bold=True)
    font_link_sub = load_font(22, bold=False)
    cta_title = "HABERİN KAYNAĞINA GİTMEK İÇİN TIKLA  >"
    cta_sub = f"Kaynak: {domain} • Detaylar son gönderide"

    ct_bbox = draw.textbbox((0, 0), cta_title, font=font_link_title)
    ct_w = ct_bbox[2] - ct_bbox[0]
    draw.text(((story_w - ct_w) // 2, link_box_y1 + 26), cta_title, font=font_link_title, fill=accent_rgb)

    cs_bbox = draw.textbbox((0, 0), cta_sub, font=font_link_sub)
    cs_w = cs_bbox[2] - cs_bbox[0]
    draw.text(((story_w - cs_w) // 2, link_box_y1 + 72), cta_sub, font=font_link_sub, fill=(210, 220, 235))

    # En Alt Marka İmzası
    brand_handle = settings.get("brand_handle", "@siberkapsul")
    font_footer = load_font(26, bold=True)
    fh_bbox = draw.textbbox((0, 0), brand_handle, font=font_footer)
    fh_w = fh_bbox[2] - fh_bbox[0]
    draw.text(((story_w - fh_w) // 2, 1685), brand_handle, font=font_footer, fill=(255, 255, 255))

    filename = f"story_{item['id']}.jpg"
    filepath = os.path.join(database.GENERATED_DIR, filename)
    canvas.convert("RGB").save(filepath, "JPEG", quality=95, optimize=True)
    return f"/generated/{filename}"


def generate_instagram_card(
    item: Dict[str, Any],
    template_override: Optional[str] = None,
    accent_override: Optional[str] = None
) -> str:
    settings = database.get_settings()
    style = template_override or settings.get("template_style", "modern_gradient")
    accent_hex = accent_override or settings.get("accent_color", "#00E5FF")
    accent_rgb = hex_to_rgb(accent_hex)

    if style == "cyber_frame":
        img = render_cyber_frame(item, settings, accent_rgb)
    elif style == "minimal_magazine":
        img = render_minimal_magazine(item, settings, accent_rgb)
    else:
        img = render_modern_gradient(item, settings, accent_rgb)

    filename = f"post_{item['id']}.jpg"
    filepath = os.path.join(database.GENERATED_DIR, filename)
    img.save(filepath, "JPEG", quality=95, optimize=True)
    return f"/generated/{filename}"
