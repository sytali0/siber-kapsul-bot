# 🚀 SİBER KAPSÜL — Otomatik Teknoloji Haber & Instagram Stüdyosu

Yerli ve yabancı teknoloji haberlerini (TechCrunch, The Verge, Ars Technica, Webtekno, ShiftDelete, DonanımHaber, Technopat, Reddit) otomatik olarak tarayan, **Google Gemini 3 Flash** ile detaylı Türkçe makaleye dönüştüren, **1080x1350 Post** ve **1080x1920 Tıklanabilir Linkli Story** görsellerini üreten tam otomatik Instagram otomasyon sistemi.

## 🔒 Güvenlik Mimarisi
- **Sıfır Açık Anahtar:** Kaynak kodda hiçbir API anahtarı, Instagram şifresi veya oturum dosyası (`ig_session.json`, `instatech.db`, `.env`) yer almaz; tamamı `.gitignore` ile korunur.
- **Yönetici Şifre Koruması (`ADMIN_PASSWORD`):** Web ortamında tüm API uç noktaları HMAC-SHA256 imzalı oturum doğrulaması ve Brute-Force koruması (5 hatalı denemede IP kilidi) ile korunur.
- **Maskelenmiş Ayarlar:** Arayüz üzerinden hiçbir zaman açık şifre veya API anahtarı (`********`) okunamaz.

---

## ☁️ GitHub Üzerinden Web'e (Render / Railway / Koyeb) Ücretsiz Kurulum

### 1. Projeyi GitHub'a Yükleyin
Proje dizininde Git hazırdır. Kendi GitHub hesabınızda yeni bir repo (Private veya Public) oluşturup yükleyin:
```bash
git remote add origin https://github.com/KULLANICI_ADINIZ/siber-kapsul-bot.git
git push -u origin main
```

### 2. Render.com veya Railway.app Üzerinde Yayına Alın
1. **[Render.com](https://render.com)** (veya Railway.app) hesabınıza girip **New + -> Web Service** seçin ve GitHub reponuzu bağlayın.
2. **Environment Variables (Ortam Değişkenleri)** bölümüne şu 5 değeri ekleyin:
   - `ADMIN_PASSWORD`: Web panelinize girerken kullanacağınız güçlü yönetici şifreniz
   - `GEMINI_API_KEY`: Google AI Studio (`aistudio.google.com`) API anahtarınız
   - `IG_USERNAME`: `siberkapsul`
   - `IG_PASSWORD`: Instagram şifreniz
   - `IG_SESSION_JSON`: *(Önerilen)* Yerel panelinizdeki **Ayarlar -> 📋 Bulut Oturum Anahtarını Kopyala** butonuna basarak kopyaladığınız oturum metni (Bulut sunucunun Instagram tarafından "yeni cihaz" engeline takılmasını %100 önler).
3. **Deploy** butonuna basın!

### 3. 7/24 Kesintisiz Çalışma (UptimeRobot)
Ücretsiz bulut sunucuların 15 dakika hareketsizlik sonrası uyku moduna geçmemesi için ücretsiz **[UptimeRobot.com](https://uptimerobot.com)** hesabınızdan her 5 dakikada bir `https://SIZIN-SITENIZ.onrender.com/api/health` adresine HTTP(s) ping tanımlamanız yeterlidir.
