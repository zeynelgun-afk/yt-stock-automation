# US Stock Market Daily - Cloud Automated Engine (%100 Ücretsiz Bulut Sunucusu)

Bu proje, bilgisayarınız kapalıyken bile **%100 ücretsiz bulut sunucusunda (GitHub Actions)** çalışarak günde 3 kez otomatik borsa videosu üretir, Telegram onayınıza sunar ve YouTube'a yükler.

---

## ☁️ Bulutta Ücretsiz Çalıştırma Kurulumu (GitHub Actions)

Bilgisayarınızda hiçbir işlem yapmanıza veya bilgisayarı açık bırakmanıza gerek yoktur.

### Adım 1: Projeyi GitHub'a Yükleyin
1. GitHub'da yeni bir **Private (Gizli)** repository oluşturun (örn: `yt-stock-automation`).
2. Proje kodlarını GitHub'a push edin:
   ```bash
   cd /home/zeynel/.gemini/antigravity-ide/scratch/yt-stock-automation
   git init
   git add .
   git commit -m "Initial commit - Youtube Automation"
   git branch -M main
   git remote add origin https://github.com/KULLANICI_ADI/yt-stock-automation.git
   git push -u origin main
   ```

### Adım 2: API Anahtarlarını GitHub Secrets'a Ekleyin
GitHub deponuzda: **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret** adımlarını izleyerek şu gizli anahtarları ekleyin:

- `FMP_API_KEY`: FMP API Anahtarınız
- `GEMINI_API_KEY`: Gemini API Anahtarınız
- `PEXELS_API_KEY`: Pexels API Anahtarınız (İsteğe bağlı)
- `TELEGRAM_BOT_TOKEN`: Telegram Bot Token
- `TELEGRAM_CHAT_ID`: Telegram Chat ID

---

## ⏰ Otomatik Zamanlayıcı (GitHub Cron)

GitHub sunucuları otomatik olarak şu saatlerde tetiklenir:
- 🟢 **15:30 TSI** (Pre-Market Shorts)
- 🟢 **20:00 TSI** (Mid-Day Shorts)
- 🟢 **23:30 TSI** (Post-Market Long Video)

Ayrıca GitHub repository'nizdeki **Actions** sekmesinden istediğiniz zaman **"Run workflow"** butonuna basarak manuel olarak da video ürettirebilirsiniz.

---

## 💡 Alternatif Ücretsiz Bulut Seçenekleri

1. **GitHub Actions (Önerilen):** Aylık 2.000 dakika ücretsiz işlem süresi sunar (bu sistem için fazlasıyla yeterlidir).
2. **Hugging Face Spaces (Free CPU Docker):** 7/24 kesintisiz ücretsiz Docker konteynırı.
3. **Modal.com:** Her ay $30 ücretsiz sunucu kredisi.
