import hashlib
import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
import requests
from bs4 import BeautifulSoup
import database

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 InstaTechBot/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_img_from_html_snippet(raw_html: str) -> Optional[str]:
    if not raw_html:
        return None
    soup = BeautifulSoup(raw_html, "html.parser")
    img = soup.find("img")
    if img:
        for attr in ("src", "data-src", "data-lazy-src", "data-original"):
            val = img.get(attr)
            if val and val.startswith("http") and not val.endswith(".svg"):
                return val
    return None


def fetch_article_full_text(article_url: str) -> str:
    """Haberin orijinal sayfasına gidip makalenin detaylı paragraflarını çeker."""
    if not article_url or not article_url.startswith("http"):
        return ""
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text[:150000], "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        paragraphs = []
        container = soup.find("article") or soup.find("main") or soup.body
        if not container:
            return ""

        for p in container.find_all("p"):
            txt = clean_html(p.get_text(" ", strip=True))
            if len(txt) >= 55 and not any(skip in txt.lower() for skip in ["cookie", "subscribe", "newsletter", "all rights reserved", "çerez"]):
                paragraphs.append(txt)
            if sum(len(x) for x in paragraphs) > 2600:
                break

        return "\n\n".join(paragraphs)[:2800]
    except Exception:
        return ""


def fetch_og_image(article_url: str) -> Optional[str]:
    if not article_url or not article_url.startswith("http"):
        return None
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text[:60000], "html.parser")
        for prop in ("og:image", "twitter:image", "og:image:secure_url"):
            meta = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if meta and meta.get("content"):
                img_url = meta["content"].strip()
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    parsed = urllib.parse.urlparse(article_url)
                    img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
                if img_url.startswith("http"):
                    return img_url
    except Exception:
        pass
    return None


def parse_rss_feed(source: Dict[str, Any], max_items: int = 8) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "xml")

        entries = soup.find_all("item")
        if not entries:
            entries = soup.find_all("entry")

        for entry in entries[:max_items]:
            title_tag = entry.find("title")
            if not title_tag or not title_tag.text:
                continue
            title = clean_html(title_tag.text)

            # Link bul
            link = ""
            link_tag = entry.find("link")
            if link_tag:
                link = link_tag.get("href") or link_tag.text or ""
            link = link.strip()

            # Özet bul
            desc_tag = entry.find("description") or entry.find("summary") or entry.find("content:encoded") or entry.find("content")
            raw_desc = desc_tag.text if desc_tag else ""
            summary = clean_html(raw_desc)[:600]

            # Görsel bul
            image_url = None
            media_content = entry.find("media:content") or entry.find("content", attrs={"medium": "image"})
            if media_content and media_content.get("url"):
                image_url = media_content.get("url")

            if not image_url:
                media_thumb = entry.find("media:thumbnail") or entry.find("thumbnail")
                if media_thumb and media_thumb.get("url"):
                    image_url = media_thumb.get("url")

            if not image_url:
                enclosure = entry.find("enclosure")
                if enclosure and enclosure.get("url") and "image" in (enclosure.get("type") or "image"):
                    image_url = enclosure.get("url")

            if not image_url:
                content_encoded = entry.find("content:encoded")
                if content_encoded and content_encoded.text:
                    image_url = extract_img_from_html_snippet(content_encoded.text)

            if not image_url and raw_desc:
                image_url = extract_img_from_html_snippet(raw_desc)

            if not image_url and link:
                image_url = fetch_og_image(link)

            guid_raw = link or title
            guid = hashlib.md5(guid_raw.encode("utf-8")).hexdigest()

            items.append({
                "guid": guid,
                "source_name": source["name"],
                "source_category": source["category"],
                "original_title": title,
                "original_summary": summary,
                "original_url": link,
                "image_url": image_url or "",
                "score": 100
            })
    except Exception as e:
        database.add_log("WARN", f"{source['name']} RSS çekilirken hata: {str(e)[:120]}")
    return items


def parse_reddit_feed(source: Dict[str, Any], max_items: int = 8) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    try:
        reddit_headers = dict(HEADERS)
        reddit_headers["User-Agent"] = "windows:com.instatech.bot:v1.0 (by /u/technews_curator)"
        resp = requests.get(source["url"], headers=reddit_headers, timeout=12)
        if resp.status_code != 200:
            # JSON engellenirse otomatik olarak Reddit RSS yedek adresini dene
            rss_url = source["url"].replace("/hot.json?limit=15", "/hot/.rss").replace(".json", ".rss")
            fallback_src = dict(source)
            fallback_src["url"] = rss_url
            return parse_rss_feed(fallback_src, max_items=max_items)

        data = resp.json()
        children = data.get("data", {}).get("children", [])
        count = 0
        for child in children:
            post = child.get("data", {})
            if post.get("stickied") or post.get("over_18"):
                continue
            title = html.unescape(post.get("title", "")).strip()
            if not title:
                continue

            ext_url = post.get("url_overridden_by_dest") or post.get("url") or ""
            permalink = "https://www.reddit.com" + post.get("permalink", "")
            selftext = clean_html(post.get("selftext", ""))[:500]
            score = int(post.get("score", 0))

            # Görsel çıkarımı
            image_url = None
            preview = post.get("preview", {})
            images = preview.get("images", [])
            if images:
                src_info = images[0].get("source", {})
                if src_info.get("url"):
                    image_url = html.unescape(src_info["url"])

            if not image_url and ext_url.endswith((".jpg", ".jpeg", ".png", ".webp")):
                image_url = ext_url

            if not image_url and ext_url and "reddit.com" not in ext_url:
                image_url = fetch_og_image(ext_url)

            guid = hashlib.md5((ext_url or permalink or title).encode("utf-8")).hexdigest()
            items.append({
                "guid": guid,
                "source_name": source["name"],
                "source_category": source["category"],
                "original_title": title,
                "original_summary": selftext or f"Reddit Gündemi ({score} upvote) - Kaynak: {ext_url}",
                "original_url": ext_url or permalink,
                "image_url": image_url or "",
                "score": score
            })
            count += 1
            if count >= max_items:
                break
    except Exception as e:
        database.add_log("WARN", f"{source['name']} çekilirken hata: {str(e)[:120]}")
    return items


def fetch_all_sources(max_per_source: int = 5) -> Dict[str, Any]:
    sources = database.get_sources()
    enabled_sources = [s for s in sources if s.get("enabled") == 1]

    added_count = 0
    total_scanned = 0
    new_ids: List[int] = []

    for src in enabled_sources:
        if src["source_type"] == "reddit" or "reddit.com" in src["url"]:
            fetched = parse_reddit_feed(src, max_items=max_per_source)
        else:
            fetched = parse_rss_feed(src, max_items=max_per_source)

        total_scanned += len(fetched)
        for item in fetched:
            new_id = database.insert_news_item(item)
            if new_id:
                added_count += 1
                new_ids.append(new_id)

    database.add_log("INFO", f"Haber taraması tamamlandı: {len(enabled_sources)} kaynaktan {total_scanned} haber incelendi, {added_count} yeni haber eklendi.")
    return {
        "sources_count": len(enabled_sources),
        "scanned": total_scanned,
        "added": added_count,
        "new_ids": new_ids
    }
