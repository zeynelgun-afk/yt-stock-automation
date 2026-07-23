# 🎯 YOL HARİTASI — Milyonlarca İzleyiciye Ulaşma Planı

> Temmuz 2026'da yapılan kod incelemesi + 3 derin web araştırmasının (YouTube algoritması,
> başarılı finans kanalları, FMP/API veri stratejisi) birleştirilmiş sonucu.
> Öncelik sırasına göre fazlara ayrılmıştır.

---

## 🧭 Stratejik Konum: Neden Bu Kanal Kazanabilir?

Araştırmanın en önemli bulgusu: **"Piyasa kapanışını 60 saniyede özetleyen, tanınabilir
görsel kimlikli faceless Shorts markası" nişi sahipsiz.** Büyük medya (CNBC, Bloomberg, IBD)
yavaş ve TV formatında; bağımsız kanallar (Meet Kevin, Maverick of Wall Street) 20-60
dakikalık kişilik odaklı içerik üretiyor. İkisinin arasındaki boşluk — hızlı, veri odaklı,
hype'sız, otomatik — tam olarak bu sistemin üretebileceği içerik.

Üç yapısal avantaj:
1. **Hız = hendek (moat).** CPI 8:31'de açıklanır, borsa 16:00'da kapanır, NVDA bilançosu
   16:21'de gelir. İlk yayınlayan kazanır; insan editör dakikalar içinde video çıkaramaz,
   otomatik pipeline çıkarır. Hedef: kapanıştan ≤15 dk sonra video yayında.
2. **Finansta faceless içerik, yüz gösteren içerikten ~%30 daha iyi performans gösteriyor**
   (YouTube 2025 verisi) — grafik ve rakamlar yıldızdır. AI avatara gerek yok.
3. **Kongre/insider işlemleri içeriği TikTok'ta patlamış, YouTube Shorts'ta az işlenmiş**
   ("Pelosi tracker" fenomeni) — ve FMP Premium planında `senate-trading` endpoint'i zaten var.

Gelir gerçeği (plan buna göre kurulmalı):
- Shorts RPM finansta bile **$0.04–0.32** (1M izlenme ≈ $100–350). Shorts = abone/erişim hunisi.
- Uzun video (8+ dk, mid-roll) RPM **$13–36**. Gerçek gelir burada.
- Q4 RPM, Q1'in ~2 katı. İlk 6-12 ay zarar normal; ortalama faceless kanal 4-10. ayda
  para kazanmaya başlıyor.

---

## 🚨 FAZ 0 — ACİL ONARIM (sistem şu an bozuk çalışıyor)

> Bunlar "geliştirme" değil; sistem şu anda muhtemelen her çalıştığında sahte veri yayınlıyor.

### 0.1 FMP `/api/v3` → `/stable` geçişi (KRİTİK)
`data_fetcher.py:9` hâlâ `api/v3` kullanıyor; FMP bu rotaları **tamamen engelledi**
(403 "Legacy Endpoint"). Yani gainers/losers/news çağrıları hep başarısız olup fallback'e
düşüyor. `FMP_SKILL.md`'deki doğru isimlerle değiştir:
- `stock_market/gainers` → `biggest-gainers`
- `stock_market/losers` → `biggest-losers`
- `stock_news` → `news/stock` (genel için `fmp-articles`)

### 0.2 Sahte fallback verilerini kaldır (KRİTİK)
`data_fetcher.py` API başarısız olursa sabit "NVDA +6.85%" verisiyle devam ediyor.
**Yanlış rakamla yayınlanan tek bir video kanal güvenilirliğini bitirir.**
Doğrusu: veri çekilemezse pipeline DURMALI ve Telegram'a hata mesajı gitmeli.
Asla uydurma piyasa verisiyle video üretilmemeli.

### 0.3 Gerçek grafik çiz (KRİTİK)
`video_engine.py:31-32` grafik olarak `np.sin` + rastgele gürültü çiziyor — videodaki
"NVDA günlük hareketi" tamamen kurgu. `historical-chart/5min?symbol=X` ile gerçek
intraday veri çek, gerçek grafiği çiz. Bu hem güven hem YouTube "inauthentic content"
politikası açısından zorunlu.

### 0.4 Sabit NVDA kartı bug'ı
`video_engine.py:86-93` render sırasında overlay kartını `ticker="NVDA",
change_pct="6.85"` sabitleriyle YENİDEN üretiyor; `main_scheduler.py`'nin doğru
verilerle ürettiği kart hiç kullanılmıyor. Hangi hisse anlatılırsa anlatılsın ekrana
NVDA çıkıyor. `render_video()` gerçek ticker/change parametrelerini almalı.

### 0.5 `cellauto` arka planını değiştir
Rastgele hücresel otomat deseni finans hissi vermiyor. Alternatifler: tam ekran animasyonlu
gerçek fiyat grafiği (çizgi soldan sağa çizilir), yavaş kayan ticker şeridi, koyu gradyan +
grid. En etkilisi: grafiğin kendisi arka plan olsun (CapCut/TradingView estetiği).

---

## 📊 FAZ 1 — VERİ KATMANI: "Günün Hikaye Havuzu"

> Premium plan: 2.500 çağrı/gün, 750/dk. Aşağıdaki tam tarama ~40-60 çağrı — bol bol yer var.
> Mimari: FMP birincil → Finnhub (60 çağrı/dk, ücretsiz) yedek → ücretsiz viral kaynaklar katman.

Her video üretiminden önce tek bir `StoryPoolCollector` şunları toplamalı:

### FMP'den (hepsi mevcut planda var — FMP_SKILL.md isimleriyle):
| Veri | Endpoint | Hikaye değeri |
|---|---|---|
| Endeksler + VIX | `batch-quote` (`^GSPC,^IXIC,^DJI,^VIX`) | Her recap'in omurgası; VIX>25 = korku hikayesi |
| Gainers/Losers/Most active | `biggest-gainers`, `biggest-losers`, `most-actives` (limit 20) | Günün ham malzemesi |
| Sektör performansı | `sector-performance-snapshot?date=today` | "Bugün neden düştük/çıktık" bağlamı |
| **Senato/Kongre işlemleri** | `senate-trading` | ⭐ EN VİRAL veri. "Senatör X, NVDA aldı" |
| **Insider işlemleri** | `insider-trading`, `insider-trading-statistics` | "CEO kendi hissesinden $50M sattı" |
| Analist not değişimleri | `upgrades-downgrades`, `grades-consensus`, `price-target-summary` | "Goldman hedefi %50 kesti" |
| Earnings takvimi | `earnings-calendar?from=today&to=+7d` | Bilanço günü içerik planlaması |
| After-hours tepkiler | `aftermarket-quote` (bilanço açıklayanlar için) | "Saat 17:00 ve hisse -%18" — ana akımdan önce yayın |
| Ekonomik takvim | `economic-calendar` | "Yarın 8:30'da CPI" geri sayım videoları |
| Haber eşleştirme | `news/stock?symbols=...`, `fmp-articles` | Her hareketin "neden"i — sebepsiz rakam hikaye değildir |
| Intraday grafik verisi | `historical-chart/5min?symbol=X` | Gerçek grafik render'ı |
| Hafta içi bağlam | `stock-price-change?symbol=X` | "Bu hafta +%40" perspektifi |

Not: `earnings-surprises` Premium'da yok (Ultimate) → beat/miss tespiti için
`analyst-estimates` tahminleri ile gerçekleşen sonucu karşılaştır veya Finnhub'ın
ücretsiz earnings-surprise endpoint'ini kullan.

### Ücretsiz kaynaklardan:
| Veri | Kaynak | Hikaye değeri |
|---|---|---|
| WSB/Reddit trend hisseleri | ApeWisdom API (ücretsiz, anahtarsız): `apewisdom.io/api/v1.0/filter/wallstreetbets` | "Reddit'in konuştuğu hisse" + meme stock açısı |
| CNN Fear & Greed | Mevcut (User-Agent header ekle) | "EXTREME FEAR" bölgesi = hazır Shorts serisi |
| Kripto F&G + trend coinler | alternative.me/fng + CoinGecko Demo (ücretsiz) | Kripto günleri için |
| Short interest | FINRA (ücretsiz, resmi) | "Hissenin %30'u açığa satılmış" squeeze hikayeleri |
| Put/Call oranı | CBOE günlük istatistik (ücretsiz) | Aşırı korku/açgözlülük sinyali |
| Options chain / max pain | yfinance (yedek, kırılgan — tek dayanak yapma) | İleri seviye içerik |

---

## 🧠 FAZ 2 — HİKAYE SEÇİM MOTORU (en önemli yeni bileşen)

> Şu anki sistemin en büyük içerik zayıflığı: her gün aynı şablonla "top gainer" videosu.
> Bu hem sıkıcı hem de YouTube'un Temmuz 2025 "inauthentic content" politikasına takılma
> riski (şablonik, videodan videoya az değişen içerik = kanal bazında YPP'den atılma).

### Nasıl çalışmalı:
1. Story pool'daki her adaya **viralite skoru** ver (kural tabanlı + LLM):
   - Kongre işlemi: tutar aralığı büyük + ALIM + gündemdeki hisse → çok yüksek skor
   - Insider: $10M+ satış veya aynı hafta 3+ insider alımı (cluster buy)
   - **Earnings paradoksu**: "beklentiyi AŞTI ama %20 düştü" → düz "beat etti"den çok daha viral
   - %15+ hareket + haberde somut sebep + ApeWisdom'da yükseliş
   - F&G uç bölgeye girdi/çıktı; VIX sıçraması
   - Analist şok kararı (çift kademe not değişimi, %40+ hedef revizyonu)
2. LLM en yüksek skorlu 2-3 hikayeyi alıp **günün açısını** seçsin (sadece "ne oldu" değil
   "neden önemli, izleyici için ne anlama geliyor").
3. Seçilen hikaye tipi, video **formatını** belirlesin (aşağıdaki franchise'lardan).

### Tekrarlayan Shorts serileri (franchise'lar — tanınabilirlik + çeşitlilik):
- 🏛️ **"Congress Trade Alert"** — yeni senato/temsilciler meclisi açıklaması düştüğünde
- 📉 **"Market Close in 60 Seconds"** — her kapanış, sabit görsel dil
- 💥 **"Earnings Shock"** — beklenti vs gerçekleşme + after-hours tepki
- 😱 **"Fear Gauge"** — F&G/VIX uç değerlere geldiğinde
- 🔍 **"Insider Watch"** — büyük insider alım/satımları
- 🚀 **"Reddit Radar"** — ApeWisdom'da patlayan hisse

Her serinin farklı yapısı ve görsel varyasyonu = hem izleyici sadakati hem politika uyumu.

---

## 🔭 FAZ 2.5 — OUTLIER TARAYICI (kanıtlanmış formatları modelleme)

> "En çok izlenen finans videolarını taklit et" işinin otomatikleştirilmiş, güvenli hali:
> formatı ve paketlemeyi modelle, içeriği kopyalama (birebir kopya = 1 numaralı
> başarısızlık nedeni + "inauthentic content" politikası hedefi).

1. **Haftalık tarama:** YouTube Data API (ücretsiz okuma kotası) ile finans nişinde son
   30 günün videolarını ara; kanal ortalamasının 3+ katı izlenme alan "outlier" videoları bul.
2. **Kalıp çıkarımı:** Başlık, süre, yayın saati, hook cümlesi (transcript varsa) →
   DeepSeek'e analiz ettir → "bu hafta çalışan kalıplar" listesi (JSON) üret.
3. **Geri besleme:** Kalıpları hikaye seçim motorunun skorlama ağırlıklarına ve
   `script_generator.py` prompt'undaki few-shot örneklere otomatik besle.
4. **Korunacak sınırlar:** Korku-clickbait kalıplarını kopyalama ("hype yok, sadece
   rakamlar" konumlandırması kanalın farklılaşması); kalıp = yapı/paketleme, asla
   birebir başlık veya senaryo kopyası değil.

Kanıtlanmış başlık kalıpları (başlangıç few-shot seti): yuvarlanmamış spesifik rakamlar
("$4.7M", "%23"), tarihli aciliyet ("in 2026"), karşıt görüş ("Everyone is wrong about..."),
sonuç-önce anlatım, paradoks kurgusu ("Beat earnings... and crashed 20%").

---

## 🎬 FAZ 3 — VİDEO KALİTESİ (swipe-away savaşı)

> Shorts'ta tek belirleyici metrik: **swipe-away.** <%30 kaydırma = 4x dağıtım.
> İlk kare + ilk 2 saniye her şeyi belirler.

1. **İlk kare mühendisliği:** Video, konuşma başlamadan önce ekranda büyük punto şok
   rakam/iddia ile açılmalı ("NVDA -%12" / "$5M NVDA BUY"). Logo/intro asla.
2. **Hook kütüphanesi** (script_generator prompt'una ekle):
   - Cesur iddia: "NVIDIA just did something no company has ever done."
   - Merak boşluğu: "This chart predicted the last 3 crashes — it just flashed again."
   - Doğrudan soru: "Why is a US senator suddenly buying this stock?"
3. **Loop tasarımı:** Son cümle başa bağlansın (tekrar izleme >%100 APV = güçlü sinyal).
   CTA'yı "subscribe" yerine loop'a hizmet edecek şekilde kısalt — Shorts'ta uzun outro ölümdür.
4. **Gerçek animasyonlu grafik:** 5 dakikalık gerçek mumlar/çizgi, soldan sağa çizilerek
   ilerlesin (matplotlib frame'leri → ffmpeg). Kritik ana zoom.
5. **Altyazı:** Hormozi tarzı doğru tercih (85% sessiz izliyor, +%42 tamamlama) —
   kelime-ses senkronu hassas olsun; 2026'da biraz daha temiz varyantlar öne çıkıyor.
6. **Uzun video 3 dk → 8+ dk:** Mid-roll reklamlar 8 dk'da açılıyor ($13-26 vs $9-16 RPM).
   450-550 kelime → 1.100-1.300 kelimeye çıkar. Yapı: Endeksler+sektörler → günün 3 büyük
   hikayesi (sebepleriyle) → kongre/insider köşesi → earnings sonuçları+takvim → yarın ne var.
7. **Uzun video için thumbnail üreticisi:** Büyük rakam odaklı ("-%3.2?" / "$5M"),
   yeşil/kırmızı yön oku, 3-5 kelime, yüksek kontrast. YouTube "Test & Compare" A/B aç.
8. **Ses:** Edge-TTS başlangıç için yeterli; büyüme başlayınca ElevenLabs'e geç
   (ses kalitesi retention'ı doğrudan etkiliyor). TTS yasak değil — özgün senaryo şart.

---

## 📅 FAZ 4 — YAYIN STRATEJİSİ + GERİ BESLEME DÖNGÜSÜ

1. **Zamanlama revizyonu:**
   - Uzun kapanış videosu: kapanıştan hemen sonra, **≤15 dk içinde** (hız hendeği).
   - Shorts: günde 1-2 (max), **4-6 saat arayla** — mevcut 15:30/20:00 TSI planı uygun,
     akşam ABD saatlerine (scroll saatleri) bir deneme slotu eklenebilir.
   - Sabit saat > "optimal" saat: tutarlılık algoritmada kazanıyor.
2. **Event günleri = turbo mod:** `economic-calendar` + `earnings-calendar`'a göre CPI,
   FOMC, NFP, büyük bilanço günlerinde ekstra video (önizleme sabah + tepki akşam).
   Küçük kanal, event'in arama hacmini ödünç alır.
3. **Analitik geri besleme (milyon izlenmenin asıl motoru):**
   YouTube Analytics API entegrasyonu → her video için swipe-away/APV/CTR çek →
   hangi franchise/hook/format çalışıyor ölç → hikaye seçim motorunun ağırlıklarını
   otomatik güncelle. Haftalık Telegram performans raporu.
4. **Politika uyum listesi (her video):** gerçek veri + gerçek grafik, videodan videoya
   yapısal varyasyon, özgün analiz cümleleri (haber özeti değil yorum), açıklamada veri
   kaynağı şeffaflığı. Hedef: incelemeci "her videoda özgün emek var" demeli.
5. **Metadata:** Başlık 40-60 karakter, anahtar kelime başta, spesifik yuvarlanmamış
   rakamlar ("$4.7M" > "milyonlarca"). Başlık+thumbnail tek ünite — aynı kelimeyi tekrarlama.

---

## 💰 FAZ 5 — GELİR VE ÖLÇEK (kanal büyüyünce)

- **Huni:** Shorts (erişim) → uzun kapanış videosu (RPM) → ileride newsletter (Finimize
  modeli, $100/yıl) + broker affiliate'leri (finansta en yüksek sponsor CPM'leri).
- YPP eşiği: 1.000 abone + (4.000 saat izlenme VEYA 90 günde 10M Shorts izlenmesi).
- İkinci dil kanalı (İspanyolca finans talebi kanıtlı) ve "premarket movers Shorts"
  (Benzinga bunu sadece 1 saatlik canlı yayın olarak yapıyor — boşluk) ölçek seçenekleri.
- Portföy modeli (Noah Morris: 20 faceless kanal, $30K+/ay) uzun vade vizyonu.

---

## ✅ ÖNCELİK SIRASI (özet)

| # | İş | Neden |
|---|---|---|
| 1 | Faz 0: `/stable` geçişi + sahte veri/grafik temizliği | Sistem şu an bozuk; güven + politika riski |
| 2 | Faz 1: Story pool collector (senato+insider+earnings+analist) | Viral hammadde olmadan gerisi anlamsız |
| 3 | Faz 2: Hikaye seçim motoru + franchise'lar | Çeşitlilik = viralite + demonetizasyon koruması |
| 4 | Faz 3: İlk kare/hook + gerçek animasyonlu grafik + 8dk uzun video | Swipe-away savaşı + RPM |
| 5 | Faz 4: Hız (kapanış+15dk) + analitik geri besleme | Ölçekleme motoru |
| 6 | Faz 5: Gelir hunisi | Kanal büyüyünce |

**Başarı hedefleri (her video ölçülmeli):**
Shorts → %75+ "viewed", <%30 swipe-away, %80+ APV, loop.
Uzun → 0:30'da %50+ retention, %50+ APV, %3-5 CTR, 8+ dk.
