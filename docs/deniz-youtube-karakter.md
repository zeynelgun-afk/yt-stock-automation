# YouTube projesindeki güncel durum — 13 Eylül 2026

Bu bölüm aşağıdaki aktarım belgesindeki belirsizlikleri güncel kod ve erişim kontrolüyle tamamlar.

- Kanal: US Stock Market Daily; yayın dili İngilizce. Shorts ve uzun video akışı mevcut.
- Referans portre değiştirilmeden `assets/characters/deniz/deniz-reference-v1.png` konumuna kopyalandı.
- Yerel ana ElevenLabs sesi Chris (`iP95p4xoKVk53GoZ742B`, American male) olarak hazırlandı; `ELEVENLABS_VOICE_ID` ile değiştirilebilir. Ana pipeline ElevenLabs hatasında başka sese geçmeden durur. Bağımsız VoiceGenerator için Edge-TTS yedeği isteğe bağlıdır: `en-US-ChristopherNeural`.
- Gerçek ElevenLabs çağrısıyla `temp/deniz-voice-test-v1.mp3` ve ölçülmüş kelime zamanlamalı `.srt` üretildi: 29 kelime, 8.638 saniye. Bu kısa tanıtım ölçümü bütün Shorts/uzun video hızını temsil etmez. Yeni ses için birkaç tam senaryoda süre ölçülmeli; eski Rachel hız kalibrasyonu doğrudan taşınmamalı.
- İlk konuşan avatar pilotu ElevenLabs web arayüzünde Creatify Aurora ile üretildi: `output/deniz-pilot-v1/deniz-pilot-v1.mp4`. Arayüz ayarı 720p; gerçek çıktı 832×1088, 25 fps, 8.72 saniye. Referans portreden oluşturulan Deniz / Headshot avatarı düz gri arka plan kullanıyor. Avatar kaydı öncesi arayüz 406 kredi gösterdi; video kredisi ayrıca ölçülmedi.
- Pilotun sesi mevcut Chris kaydıdır: 8.637823 saniye. Kaynak ses ile çıktı sesi sıfır kaymada 0.999996 korelasyon gösterdi. Dört örnek karede belirgin yüz bozulması görülmedi; tam dudak senkronu kalitesi oynatarak değerlendirilmelidir. Dosyalar, kaynak ses/altyazı ve üretim ayarları `output/deniz-pilot-v1/` altında.
- ElevenLabs Creator hesabı web arayüzünde pilot üretimini tamamladı. Görsel/video API erişimi için güncel resmi belgede Pro veya üzeri gerekiyor: https://elevenlabs.io/docs/overview/capabilities/image-video . Mevcut Higgsfield istemcisi arka plan üretir; ses güdümlü avatar entegrasyonu değildir.
- Canlı erişim kontrolü: bağlı Higgsfield MCP hesabı free / 0 kredi; trial pending. Yerel projede Higgsfield platform API anahtarları yok. MCP hesabı ile GitHub Actions API erişimi ayrı doğrulanmalıdır.
- Onaylanan yöntem: Creator planında kalınacak; tüm anlatım Chris, Deniz yalnızca kısa açılış/geçişlerde. Yerel uygulama: Shorts en fazla 6 saniye açılış; uzun en fazla 8 saniye açılış + uygun orta cümle sınırında 5 saniye geçiş. `main_scheduler.py --prepare-presenter` grafik videosu ve bölüme özel WAV dosyalarını çıkarır; `presenter_workflow.py finish` Creator arayüzünden indirilen klipleri birleştirir. Kullanım README içinde.
- Eksik klip yerinde grafik kalır; yanlış ses veya süre taşıyan klip reddedilir. Hazırlık/birleştirme komutları YouTube yayını yapmaz. Zamanlanmış yayınlar grafik akışını sürdürür; tarayıcıdan avatar hazırlama CI içine bağlanmadı.
- Bu sürüm ana pipeline varsayılan sesini Chris yapar. Yeni kodla zamanlanmış gerçek video üretimi henüz doğrulanmadı; yerel testler ve pilot canlı yayın kanıtı değildir. Yerel birleştirme `publication.json` içinde avatar kullanılan çıktıyı `contains_synthetic_media=true` olarak işaretler. Hazır çıktının yükleyiciye aktarılması ve canlı yayın ayrı adımdır.

## Aktarılan kaynak belge

# Deniz — YouTube Sanal Sunucu Proje Devri

Tarih: 13 Eylül 2026
Durum: İlk referans portresi oluşturuldu; ses ve video henüz üretilmedi.

## 1. Amaç ve mevcut kararlar

YouTube projesinde tekrar kullanılabilecek, gerçekçi görünümlü erkek bir sanal sunucu oluşturmak. Kullanıcı erkek karakter istedi, ilk portre üretildi ve bu karakteri YouTube projesinde kullanmak istediğini belirtti.

- **Deniz** çalışma adıdır; asistan tarafından önerilmiştir, kesin marka veya kanal adı değildir.
- Kanalın konusu, hedef kitlesi, yayın dili ve video süresi henüz belirtilmedi. Bunları mevcut YouTube projesinden öğren; finans veya teknoloji kanalı olduğunu varsayma.
- Karakter tamamen kurgusaldır. Gerçek bir kişinin kimliğine dayanmaz.
- Bu belge bir proje devridir; mevcut YouTube projesine entegrasyon yapıldığı anlamına gelmez.

## 2. Üretilen referans görsel

İlk denemede Higgsfield, “Requires basic plan or higher” hatası verdi ve üretim başlamadı. Kullanıcının onayıyla ChatGPT görsel oluşturma aracı kullanıldı ve portre başarıyla üretildi. Abonelik veya hesap durumu sonraki oturumda değişmiş olabilir.

Bu oturumda görselin kaynak yolu:

```text
/workspace/scratch/46f47f1e1d36/generated_images/exec-a461f9dd-97da-4459-9b6e-addaf3b615a4.png
```

**Taşınabilirlik:** Yukarıdaki yol başka bilgisayarda bulunmayabilir. Sohbetteki portreyi ayrıca indirip YouTube proje klasöründe şu adla sakla:

```text
assets/characters/deniz/deniz-reference-v1.png
```

Bu Markdown dosyası görselin kendisini içermez. Sonraki üretimlerde yalnız metin açıklaması yeterli değildir; referans görseli de modele ver. Görsele erişilemiyorsa kullanıcıdan portreyi eklemesini iste. Benzer bir yüzü sessizce yeni referans olarak kabul etme.

## 3. Karakter kimliği

| Özellik | Referans tanımı |
| --- | --- |
| Görünen yaş | Yaklaşık 30 |
| Genel görünüm | Akdeniz görünümü, sıcak buğday ten |
| Saç | Koyu kahverengi, kısa ve doğal dalgalı/tekstürlü |
| Göz | Kahverengi |
| Sakal | Kısa, bakımlı kirli sakal ve bıyık |
| Yüz | Doğal yüz hatları, belirgin kaşlar, hafif asimetri |
| Cilt | Gözenek ve ince çizgileri görünen gerçekçi doku |
| Yapı | Fit, doğal vücut oranları |
| İfade | Sakin, hafif gülümseyen, kameraya doğrudan bakan |
| İlk kıyafet | Krem renkli, yakalı kısa kollu örgü üst |
| İlk ortam | Gün ışığı alan kafe, arka plan yumuşak bulanık |

Yaş, yüz oranları, saç çizgisi, göz rengi ve sakal karakteri korunmalı. Kıyafet, mekân ve kadraj değişebilir. Kusursuz plastik cilt, aşırı kaslı vücut ve ağır güzellik filtresi karakterin yönüne uygun değildir.

## 4. Sunucu kişiliği ve ses yönü — başlangıç önerisi

Bunlar henüz uygulanmış veya kullanıcı tarafından kesinleştirilmiş seçimler değildir.

- Sakin, anlaşılır, bilgili ve ölçülü bir anlatım.
- Kısa cümleler; somut örnekler; gereksiz heyecan ve bağırma yok.
- Doğal yetişkin erkek sesi; orta perde, sıcak tını ve net telaffuz.
- Kanal dili belirlenince o dilde ses seçimi yapılmalı. Türkçe veya İngilizce peşinen sabitlenmemeli.
- İlk ses seçimi kısa örnekle değerlendirilmeli; seçilen sesin model ve ses kimliği kaydedilmeli.
- Gerçek hayatta yaşamadığı deneyimleri yaşamış gibi anlatan bir biyografi veya uzmanlık geçmişi yazılmamalı.

## 5. İlk portrenin üretim komutu

Aşağıdaki komut ilk görsel için kullanıldı. Tek başına tekrar kullanmak aynı yüzü garanti etmez.

```text
Create a photorealistic foundational portrait for an original fictional male virtual social media influencer named Deniz. Portrait orientation 4:5. Single man approximately 30 years old, Mediterranean appearance, warm olive skin with realistic pores and subtle imperfections, brown eyes, short textured dark brown hair, neatly groomed short stubble, distinctive natural facial features, fit average build. Approachable confident expression, slight relaxed smile, direct eye contact. Wearing a refined cream knit polo, no visible logos. Waist-up portrait, face clearly visible, relaxed shoulders, natural anatomy. Contemporary airy cafe interior softly blurred behind him, daylight from a large window, warm neutral color palette, candid premium lifestyle editorial photography, realistic 50mm lens, believable skin texture. A convincing everyday content creator, not an overly retouched fashion model. Suitable for Instagram and future consistent character references. No text, watermark, collage, or other people.
```

## 6. YouTube sunucu karesi üretim şablonu

**Girdi:** Referans portresi + aşağıdaki komut. Süslü parantez içindeki alanları üretimden önce doldur.

```text
Use the attached reference image as the identity reference for Deniz, the same fictional adult male host. Preserve his facial proportions, eye color, hairline, hairstyle, stubble, apparent age and natural skin texture. Do not redesign the person.

Create a photorealistic YouTube presenter frame in {16:9 for a standard video / 9:16 for a vertical video}. Deniz is seated in {setting}, wearing {outfit}. Medium chest-up composition, eye-level camera, relaxed shoulders, direct eye contact, calm attentive expression. Soft natural key light, uncluttered background, realistic anatomy and skin texture. Keep enough room above the head and keep the face clear of areas reserved for captions. No embedded text, logos or watermark.
```

Başlangıç sahnesi önerisi: sade, sıcak tonlu çalışma odası; krem veya koyu lacivert üst; sabit kamera. Önce tek sahnede yüz tutarlılığı doğrulanmalı.

## 7. Konuşan video için hareket şablonu

Bu şablon henüz denenmedi. Seçilecek aracın referans görsel, ses ve dudak senkronizasyonu desteği kontrol edilmeli.

```text
Animate the same fictional male host from the supplied reference frame. Maintain his facial identity throughout the shot. Locked eye-level camera, natural subtle blinking, gentle breathing, minimal head movement and restrained facial expressions. He speaks directly to the viewer with accurate lip synchronization to the supplied speech audio. Preserve the lighting, outfit and background. No camera orbit, abrupt gestures, facial morphing or extra people.
```

Konuşma metnini ayrı tut. Araç sesi ayrı kabul ediyorsa onaylı sesi kullan; yalnız yazılı komutun dudak senkronizasyonu sağlayacağını varsayma.

## 8. İlk pilot üretim akışı

1. Mevcut YouTube proje belgelerini oku; konu, dil ve hedef kitleyi belirle.
2. Kaynak portreyi önerilen proje yoluna yerleştir.
3. Referansla bir YouTube sunucu karesi üret.
4. Kanal dilinde kısa bir deneme metni yaz; yaklaşık 10–15 saniyelik ses hazırla.
5. Aracın desteklediği süreye uygun tek çekim pilot video üret.
6. Yüz tutarlılığı, dudak senkronizasyonu, telaffuz ve görüntü hatalarını kontrol et.
7. Kabul edilen görsel, ses ve üretim ayarlarını kaydet; ardından bölüm üretimine geç.

Örnek Türkçe ses testi — kanal dili Türkçeyse kullanılabilir:

> Merhaba, ben Deniz. Bu kanalda konuları açık ve anlaşılır biçimde ele alacağız. Gereksiz ayrıntılara boğulmadan, önemli noktaları somut örneklerle açıklayacağız. Hazırsanız başlayalım.

Bu metin bir testtir; kanalın gerçek açılışı konu belirlendikten sonra yazılmalı.

## 9. Kalite ölçütleri

- Farklı sahnelerde aynı kişi olarak tanınması.
- Göz, ağız, diş ve ellerde belirgin deformasyon olmaması.
- Cildin doğal görünmesi; yüzün çekim boyunca değişmemesi.
- Konuşmanın net, dudak hareketlerinin sesle uyumlu olması.
- Uzun videoda yalnız sunucu yüzüne dayanmak yerine konuya uygun ekran görüntüleri, görseller ve açıklayıcı grafikler kullanılması.
- Sanal sunucu olduğunun izleyiciye açık biçimde anlatılması.

Yayın aşamasında platformun güncel sentetik içerik açıklaması ve kullanılan araçların ticari kullanım koşulları ayrıca doğrulanmalı. Bu belgede güncel politika veya lisans incelemesi yapılmadı.

## 10. Önerilen proje düzeni

```text
youtube-project/
  docs/
    deniz-youtube-karakter.md
  assets/
    characters/
      deniz/
        deniz-reference-v1.png
        deniz-presenter-16x9-v1.png
        deniz-presenter-9x16-v1.png
  prompts/
    deniz-image.txt
    deniz-motion.txt
  audio/
    deniz-voice-test-v1.wav
  videos/
    deniz-pilot-v1.mp4
```

Bu düzen öneridir; yukarıdaki dosyaların tamamı oluşturulmuş değildir. Her kabul edilen üretim için araç, model, tarih, referans dosyası, komut, ses kimliği ve varsa seed/job ID bilgisi kaydedilmeli. Seed tek başına yüz tutarlılığı garantisi değildir.

## 11. Sonraki asistana / terminal oturumuna başlangıç talimatı

```text
Bu dosyayı YouTube projemizin sanal sunucu karakter belgesi olarak oku.
Deniz'in oluşturulmuş referans yüzünü koruyarak projeye entegre et.
Önce mevcut proje dosyalarını incele; kanalın konusunu, dilini ve video biçimini mevcut belgelerden öğren. Belgelerde olmayan kararları alınmış gibi sunma.
Referans portreyi assets/characters/deniz/deniz-reference-v1.png yolunda ara. Yoksa bu belgedeki eski oturum yolunun erişilebilirliğini kontrol et; görsele erişemiyorsan benden portreyi eklememi iste.
Henüz ses veya video oluşturulmadığını dikkate al. Önce kısa bir pilot hazırla; karakterin yüzünü her sahnede yeniden tasarlama.
Higgsfield'ın önceki üretim isteği abonelik nedeniyle başarısız oldu; ChatGPT ile tek portre üretildi. Yeni üretim öncesi mevcut erişim ve araç yeteneklerini kontrol et. Oluşturulmayan sonuçları tamamlandı diye raporlama.
```
