# US Stock Market Daily

İngilizce finans videoları üreten Python otomasyonu. FMP verisiyle hikâye seçer, senaryo ve ses üretir, gerçek grafiklerle render alır ve **insan onayı beklemeden YouTube'a yükler**. Telegram yayın sonrası önizleme ve hata bildirimleri içindir.

Akış: FMP → kaynaklı hikâye adayları + güncel YouTube konu ilgisi → LLM → ElevenLabs/Edge-TTS → FFmpeg → YouTube → Telegram.

## Güncel içerik deneyi

- Shorts: yaklaşık 32–38 saniye, ilk cümlede şirket/kişi ve olay; açıklama ilk 8 saniyede başlar.
- Uzun video: yaklaşık 150–210 saniye, tek ana hikâye ve ilgili piyasa bağlamı. Süreler ölçülen ses hızına göre haftalık kalibre edilir; kesin render süresi garantisi değildir.
- Trendler: son 3 gündeki popüler finans videoları günde bir önbelleğe alınır. Aynı şirket hakkında zaten kaynaklı ve yeterince güçlü bir aday varsa küçük seçim bonusu uygulanır. Dış video başlıkları finansal veri veya kopyalanacak senaryo sayılmaz.
- Öğrenme: Shorts ve uzun videolar ayrılır; format ağırlıkları en az 20 engaged izlenmeli Shorts'lardan hesaplanır. Aşırı tekrar izleme değerlerinin etkisi sınırlandırılır.
- İnceleme ve başlangıç ölçümleri: [GROWTH_AUDIT.md](GROWTH_AUDIT.md).

## Yerel kullanım

Python 3.12, FFmpeg/ffprobe ve Liberation/DejaVu fontları gerekir.

```bash
python -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python -m unittest discover -s tests -v
```

`.env.example` değişkenlerini kendi `.env` dosyanıza ekleyin. FMP anahtarı, en az bir LLM sağlayıcısı ve geçerli YouTube OAuth yetkileri gerekir. Ücretli sağlayıcı kullanımı ve GitHub Actions maliyeti hesabınızın planına bağlıdır; sistem için koşulsuz ücretsiz çalışma garantisi yoktur.

Aşağıdaki komutlar **gerçek üretim ve otomatik yayın** başlatır:

```bash
./venv/bin/python main_scheduler.py shorts
./venv/bin/python main_scheduler.py long
```

Salt okunur performans raporu:

```bash
./venv/bin/python analytics_reporter.py
```

`event-check` makro/bilanço gününü kontrol eder; 0=etkinlik var, 1=sakin gün, 2=kontrol hatası. Pipeline hataları, YouTube yükleme hatası dahil, başarısız çıkış kodu üretir.

## GitHub Actions

`.github/workflows/youtube_auto.yml` çalışma saatlerinin asıl kaynağıdır:

- Hafta içi Shorts: 15:30 ve 20:00 Türkiye saati; ABD akşam slotu ertesi gün 03:30.
- Etkinlik günü ek Shorts: 16:35 Türkiye saati.
- Uzun video: New York 16:05 için iki yaz/kış saati adayı; uygun olan çalışır.
- Haftalık analiz ve öğrenme: pazar 18:00 Türkiye saati.

Cron gecikmeleri mümkündür; tam dakikasında veya kapanıştan 15 dakika içinde yayın garantisi yoktur. Mevcut takvim borsa tatillerini ayrıca filtrelemez.

Workflow'da listelenen API değişkenlerini GitHub Secrets'a ekleyin. YouTube için `YOUTUBE_CLIENT_SECRET_JSON` ve `YOUTUBE_TOKEN_JSON` gerekir. Token; `youtube.upload`, `youtube.readonly`, `yt-analytics.readonly` izinlerini içermelidir. Yetkilendirme yerelde tamamlanır; CI etkileşimli tarayıcı açmaz.

PR kontrolleri video yayınlamaz. Üretim workflow'u yayından önce aynı testleri çalıştırır. Günlük trend önbelleği Actions cache, haftalık öğrenme dosyası Git ile korunur.

## Veri doğruluğu ve sınırlar

Temel piyasa verisi yoksa yayın durur. Karttaki büyük sayı kaynak alanlarıyla tutar ve birim düzeyinde karşılaştırılır; LLM metni kanıt sayılmaz. Bu kontrol tüm senaryonun semantik doğruluğunu garanti etmez. Kart/grafik yüzdesi ilk mum açılışına göre hesaplanır ve **SINCE SESSION OPEN** olarak etiketlenir; önceki kapanışa göre günlük değişim değildir.

`ROADMAP.md` ve `FMP_SKILL.md` geçmiş plan/referans belgeleridir; güncel davranış için kod ve bu README esas alınmalıdır.
