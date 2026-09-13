# US Stock Market Daily

İngilizce finans videoları üreten Python otomasyonu. FMP verisiyle hikâye seçer, senaryo ve ses üretir, gerçek grafiklerle render alır ve **insan onayı beklemeden YouTube'a yükler**. Telegram yayın sonrası önizleme ve hata bildirimleri içindir.

Akış: FMP → kaynaklı hikâye adayları + güncel YouTube konu ilgisi → LLM → ElevenLabs Chris → FFmpeg → YouTube → Telegram. Ana pipeline, ElevenLabs ses üretimi başarısızsa farklı sese geçmeden durur. Bağımsız `VoiceGenerator` kullanımında Edge-TTS yedeği hâlâ isteğe bağlıdır.

Yeni YouTube yüklemelerinde başlık/açıklama dili (`defaultLanguage`) ve ses dili (`defaultAudioLanguage`) açıkça `en` olarak gönderilir. Kanalın varsayılan açıklaması İngilizcedir; 12 Eylül 2026'da Türkçe arayüzde eski açıklamayı gösteren `tr_TR` kanal çevirisi kaldırıldı. Bu tarihte taranan 160 videonun metin dili `en`; 138 eski videonun ses dili alanı boştu. Bu eski video alanları değiştirilmedi.

## Güncel içerik deneyi

- Shorts: yaklaşık 32–38 saniye, ilk cümlede şirket/kişi ve olay; açıklama ilk 8 saniyede başlar.
- Uzun video: yaklaşık 150–210 saniye, tek ana hikâye ve ilgili piyasa bağlamı. Süreler ölçülen ses hızına göre haftalık kalibre edilir; kesin render süresi garantisi değildir.
- Trendler: son 3 gündeki popüler finans videoları günde bir önbelleğe alınır. Aynı şirket hakkında zaten kaynaklı ve yeterince güçlü bir aday varsa küçük seçim bonusu uygulanır. Dış video başlıkları finansal veri veya kopyalanacak senaryo sayılmaz.
- Öğrenme: Shorts ve uzun videolar ayrılır; format ağırlıkları en az 20 engaged izlenmeli Shorts'lardan hesaplanır. Aşırı tekrar izleme değerlerinin etkisi sınırlandırılır. Analytics kesintisinde önceki ağırlıklar ve ölçüm tarihleri korunur; başarıyla alınmış boş rapor nötr ağırlıklara geçer.
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

## Deniz: Creator planıyla kısa sunucu sahneleri

Tüm anlatım varsayılan olarak Chris (`iP95p4xoKVk53GoZ742B`); `ELEVENLABS_VOICE_ID` ile değiştirilebilir. Deniz Shorts'ta en fazla 6 saniyelik açılışta, uzun videoda en fazla 8 saniyelik açılış ve 5 saniyelik tek geçişte kullanılır. Uzun geçiş yalnızca en az 45 saniyelik anlatımda, orta bölümde uygun cümle sınırı varsa seçilir. Kalan görüntü mevcut grafik videosudur. Ses tek kayıt olarak kesintisiz kalır.

Creator video klipleri web arayüzünde hazırlanır; bu yerel çalışma akışı otomatik video API çağrısı veya ek abonelik gerektirmez. Şu komutlar gerçek veri/senaryo/ses üretimi yapar ve sağlayıcı kredisi kullanabilir; **YouTube'a yüklemeden** hazırlık paketi çıkarır:

```bash
./venv/bin/python main_scheduler.py shorts --prepare-presenter
./venv/bin/python main_scheduler.py long --prepare-presenter
```

Başarılı çalışmada `output/presenter_<format>_<tarih>/` altında grafik videosu, tam anlatım, altyazılar, referans portre ve `intro.wav` / varsa `transition.wav` oluşur. Paket geçici klasörden bağımsızdır. Hatalar mevcut pipeline hata bildirimi yolunu kullanır.

ElevenLabs Image & Video → Lip sync ekranında Deniz'i ve paketin WAV dosyasını seçin; sesi yeniden üretmeyin veya hızını değiştirmeyin. Shorts için 9:16, uzun video için 16:9 kadraj kullanın. İndirilen klipleri pakete `intro.mp4` / `transition.mp4` adlarıyla koyun. Ardından:

```bash
./venv/bin/python presenter_workflow.py finish output/presenter_shorts_<tarih>
```

`final.mp4` ve `publication.json` oluşur. Sadece mevcut klipler ilgili saniyelere yerleştirilir; eksik klibin yerinde grafik kalır. Kaynak ses, altyazı veya klip sesi değişmişse işlem durur. Yanlış sesli eski pilotun kullanılması, klibin uzatılması veya döngüye alınması kabul edilmez. Bu dalga biçimi kontrolü yanlış/senkronu kaymış sesi yakalar; dudak hareketlerinin görsel kalitesini ölçmez. Yüksek sıkıştırma veya sağlayıcının sesi işlemesi doğru klibin de reddedilmesine yol açabilir.

Birleştirme ana videonun sesini aynen kopyalar, avatar sahnelerinde zamanlamalı altyazıyı korur. Avatar kullanıldığında `publication.json` içindeki `contains_synthetic_media` true olur; bu komut yayın yapmaz. Hazır video YouTube'a yüklenirken bu işaret kullanılmalıdır.

Zamanlanmış GitHub Actions akışı avatar beklemeden grafiklerle yayın yapar; `--prepare-presenter` yerel ve ayrı bir moddur. Değişiklikleri GitHub'a göndermek, Creator kliplerini hazırlamak ve avatarı canlı yayına dahil etmek ayrı adımlardır. İlk pilot ve kararlar: [Deniz karakter belgesi](docs/deniz-youtube-karakter.md).

`event-check` makro/bilanço gününü kontrol eder; 0=etkinlik var, 1=sakin gün, 2=kontrol hatası. Pipeline hataları, YouTube yükleme hatası dahil, başarısız çıkış kodu üretir.

## GitHub Actions

`.github/workflows/youtube_auto.yml` çalışma saatlerinin asıl kaynağıdır:

- Hafta içi Shorts: 15:30 ve 20:00 Türkiye saati; ABD akşam slotu ertesi gün 03:30.
- Etkinlik günü ek Shorts: 16:35 Türkiye saati.
- Uzun video: New York 16:05 için iki yaz/kış saati adayı; uygun olan çalışır.
- Haftalık analiz ve öğrenme: pazar 18:00 Türkiye saati.

Cron gecikmeleri mümkündür; tam dakikasında veya kapanıştan 15 dakika içinde yayın garantisi yoktur. Mevcut takvim borsa tatillerini ayrıca filtrelemez.

Kapanış modu, işin başladığı saate göre değil cron ve ilk çalıştırmanın GitHub `created_at` zamanına göre seçilir. Gecikme veya yeniden çalıştırma, doğru yaz/kış saati slotunu elemez. Bu seçim için workflow'un `actions: read` izni gerekir.

Workflow'da listelenen API değişkenlerini GitHub Secrets'a ekleyin. YouTube için `YOUTUBE_CLIENT_SECRET_JSON` ve `YOUTUBE_TOKEN_JSON` gerekir. Token; `youtube.upload`, `youtube.readonly`, `yt-analytics.readonly` ve otomatik yorum yanıtları için `youtube.force-ssl` izinlerini içermelidir. Yetkilendirme yerelde tamamlanır; CI etkileşimli tarayıcı açmaz. Koda izin eklemek mevcut token'a yeni yetki kazandırmaz; eksikse yerelde yeniden yetkilendirip secret'ı güncelleyin.

## Otomatik İngilizce yorum yanıtları

GitHub Actions, her normal Shorts çalışmasında ve etkinlik doğrulanan turbo slotunda video üretiminden önce `comment_responder.py --publish` çalıştırır. Mevcut hafta içi Shorts takvimini kullanır; ayrıca hafta sonu yorum cron'u yoktur. Doğrudan `main_scheduler.py shorts` çalıştırmak yorum göndermez.

- Son 14 gündeki yayınlanmış üst düzey yorumlar taranır: en fazla 300 yorum, 6 yanıt üretme denemesi ve çalıştırma başına 3 yanıt. Kontrol tüm kanal videolarını kapsar; yanıtların altına yeni sohbet zinciri başlatılmaz.
- Yanıtlar kısa, İngilizce, nazik ve yoruma özeldir. Uygun yerde hafif espri veya doğal bir soru kullanılabilir; etkileşim artışı garanti değildir. Spam, reklam ve kişisel yatırım önerisi talepleri atlanır. Yorumlar modele talimat olarak değil güvenilmeyen veri olarak verilir.
- Kanalın mevcut cevapları YouTube'dan tüm sayfalarıyla okunur; model yanıtından sonra göndermeden önce tekrar kontrol edilir. Çok büyük veya okunamayan yanıt dizisinde gönderim yapılmaz. Aynı çalışmada tekrar eden metinler atlanır. YouTube'dan silinen kanal yanıtları için ayrı kalıcı kayıt tutulmaz.
- Yayın isteği otomatik yeniden denenmez; belirsiz hata o yorum turunu durdurur. Workflow eşzamanlı çalışmaları sıraya alır. Kontrol 240 saniyeyle sınırlıdır; hatası veya eksik yorum izni video üretimini engellemez ve Actions uyarısına yazılır.
- Metin biçimi, uzunluk, bağlantı ve yabancı alfabe kontrolleri vardır; dilin anlamı, nezaket ve uygunluk değerlendirmesi model kalitesine bağlıdır.

Yerel önizleme (yorum göndermez): `./venv/bin/python comment_responder.py`. Gerçek gönderim: `./venv/bin/python comment_responder.py --publish`. Actions'ta yalnızca yorumları çalıştırmak için manuel `comments` modu seçilebilir; bu mod video üretmez. Yerel gönderimi Actions çalışmasıyla aynı anda başlatmayın; yerel süreç workflow kilidine dahil değildir.

PR kontrolleri video yayınlamaz. Üretim workflow'u yayından önce aynı testleri çalıştırır. Günlük trend önbelleği Actions cache, haftalık öğrenme dosyası Git ile korunur.

## Veri doğruluğu ve sınırlar

Temel piyasa verisi yoksa yayın durur. Karttaki büyük sayı kaynak alanlarıyla tutar ve birim düzeyinde karşılaştırılır; LLM metni kanıt sayılmaz. Bu kontrol tüm senaryonun semantik doğruluğunu garanti etmez. Kart/grafik yüzdesi ilk mum açılışına göre hesaplanır ve **SINCE SESSION OPEN** olarak etiketlenir; önceki kapanışa göre günlük değişim değildir.

Insider işlemleri kişi, hisse, yön **ve işlem tarihi** bazında gruplanır; farklı günler tek işlem gibi sunulmaz. Toplu alım sinyali son yedi gündeki en az üç farklı, adı bilinen alıcıdan hesaplanır. Trend taramasının OAuth yedeği, henüz `token.json` olmayan CI ortamında `YOUTUBE_TOKEN_JSON` üzerinden de çalışır. Telegram bağlantı hataları token içerebilen URL veya yanıt gövdesini loglamaz.

`ROADMAP.md` ve `FMP_SKILL.md` geçmiş plan/referans belgeleridir; güncel davranış için kod ve bu README esas alınmalıdır.
