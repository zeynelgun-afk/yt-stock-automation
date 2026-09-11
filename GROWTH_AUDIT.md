# Kanal incelemesi ve büyüme deneyi — 11 Eylül 2026

Kanal: [US Stock Market Daily](https://www.youtube.com/@usstockmarketdaily), `UCuIeHEWGJoDhiGLNBrwscZw`.
Ölçüm: yetkili YouTube Data/Analytics API'lerinden salt okunur sorgular. Kanal anlık toplamları: **15 abone, 154 video, 4.674 izlenme**. Rapor penceresi 13 Ağustos–9 Eylül 2026; günlük yanıtta son dolu tarih 8 Eylül. Son günlerin verisi henüz tamamlanmamış olabilir.

## Başlangıç ölçümleri

| Format | Pencerede izlenen video | İzlenme | Engaged izlenme | Kazanılan abone |
|---|---:|---:|---:|---:|
| Shorts | 98 | 3.267 | 1.322 | 9 |
| Uzun | 15 | 194 | 153 | 0 |

Buradaki video sayıları bu dönemde yüklenenleri değil, dönemde izlenme alanları sayar. Video başına medyan izlenme Shorts'ta 16, uzunlarda 10. Uzun formatın API toplamında ortalama izleme 76 saniye, APV %18,37.

| Trafik kaynağı | İzlenme | Engaged izlenme | İzlenme payı |
|---|---:|---:|---:|
| YouTube arama | 2.113 | 1.132 | %61,1 |
| Shorts akışı | 1.102 | 205 | %31,8 |
| Diğer | 246 | 138 | %7,1 |

Engaged/views oranı, Studio'nun “stayed to watch / viewed vs swiped away” oranı değildir. APV de bu oran değildir. Shorts toplam APV %90,15 olsa da bir video yalnızca 5 engaged izlenmeyle %6.118,8 APV göstermiştir; tek başına toplam APV sağlıklı büyüme kanıtı değildir. Bu nedenle ağırlıklandırmada küçük örneklem dışlanır ve APV katkısı %100'de sınırlandırılır; ham rapor değerleri değiştirilmez.

Aramada başlıca sorgular: `bloom energy` 158, `bloom energy stock` 149, `capr stock` 52, `biaf stock` 44, `coreweave stock` 35 izlenme. Arama terimi raporu gizlilik eşikleri nedeniyle toplam trafiğin tamamını açıklamaz.

Öne çıkan içerikler:

- [Pelosi Bought Bloom Energy. Then Waited a Month to Say So.](https://www.youtube.com/watch?v=_bwBeVnlqgE): 244 izlenme; 33 saniye; APV %84,7; +1 abone.
- [Pasqal Closed at $19.11 on Its First Day Public](https://www.youtube.com/watch?v=A6a7aRMWQvg): 227 izlenme; 39 saniye; APV %65,5; +1 abone.
- [CAPR Ripped 52% While Three Law Firms Filed](https://www.youtube.com/watch?v=lUQTQ09uuyY): 161 izlenme; 38 saniye; APV %61,5; +1 abone.

Şirket/kişi adı ve tek somut olay içeren içerikler, test edilecek bir başlangıç sağlar. Bu küçük örneklemden başlığın izlenmeye neden olduğu veya belirli bir konunun kesin büyüme getireceği sonucu çıkarılamaz.

## Uygulanan değişiklikler

1. YouTube yükleme hatası artık başarısız işlem koduyla sonuçlanır. Telegram önizlemesi yayından sonra gönderilir.
2. Büyük kart sayısı, LLM metninden değil kaynak veri alanlarından kontrol edilir; tutar, büyüklük birimi ve yön dikkate alınır. Bu sayısal kontrol aktör/olay atfını veya tüm senaryoyu doğrulamaz.
3. FMP hata mesajları anahtar içerebilen istek URL'sini taşımaz; bozuk mum fiyatları reddedilir. Ekrandaki yüzde, “SINCE SESSION OPEN” etiketiyle açıklanır.
4. Shorts ilk cümlesinde şirket/aktör ve olay; ilk 8 saniyede somut açıklama hedeflenir. Zorlama soru, ilgisiz endeks karşılaştırması ve doğrulanmamış gizli bilgi iması kaldırılır.
5. Uzun format 150–210 saniyelik tek hikâye deneyine geçer. 65 etiketli videodan ölçülen medyan ses hızı 2,132 kelime/saniye; başlangıç bütçeleri Shorts 68–81, uzun 320–448 kelime.
6. Öğrenme motoru en az 20 engaged izlenmeli Shorts'ları karşılaştırır. Güncel ağırlıklar: congress_trade 1,30; insider_watch 0,71; market_close 0,70. Bunlar 28 günlük örnekleme dayalı sınırlı çarpanlardır, evrensel içerik puanları değildir. Yeni formatlar nötr kalır.
7. Öğrenme bölümlerinin güncelliği ayrı tutulur; bir bölüm yenilendiğinde eski anlatım önerileri güncel sayılmaz.
8. Son üç gündeki popüler finans videoları günlük taranır. Ortalama saatlik izlenme, anlık hız değil yayınlanmadan beri ortalamadır. Aynı şirket/konu için bağımsız kaynaklı aday varsa en çok 10 puan bonus verilir. Başlıklar kanıt veya kopyalanacak metin değildir. Trend olmaması üretimi engellemez.
9. Bu projede 19 alakasız Codex eklentisi devre dışı bırakıldı; etkin yerel beceri taraması 90 beceri, sıfır hata döndürdü. Global eklenti kurulumları korundu. Yeni oturumda bu kapsam kullanılır.

## 14 günlük değerlendirme

Başlangıç, değişikliklerin üretime geçtiği tarihtir; raporun yazıldığı gün otomatik başlangıç sayılmaz. Yeni abonelik veya yayın sıklığı artışı bu deneyin parçası değildir.

- İki öncelikli konu: kaynaklı şirket katalizörleri ve kamuya açıklanmış kongre/insider işlemleri. Konu seçimi gerçek güncel veriye bağlı kalır; popüler video başlığı tek başına üretim nedeni değildir.
- Her videoyu aynı yaşta, yayınından 72 saat sonra ölç: izlenme, engaged izlenme, ortalama izleme, APV, abone kazanımı ve trafik kaynağı. Shorts ve uzun videolar ayrı karşılaştırılır.
- Studio'dan Shorts “stayed to watch” ve uzun video gösterim/CTR ölçümlerini ayrıca değerlendir. Bu incelemede bu iki metrik alınmadı; arama payı veya APV'den türetilmez.
- İlk değerlendirme en az 10 yeni Shorts ve format başına yeterli engaged örneklem oluşunca yapılır. 14 günde örneklem yetersizse sonuç kesinleştirilmez.
- Başarı ölçütü: eşit yaşlı videoların medyan engaged izlenmesinde ve abone dönüşümünde artış; aynı zamanda izleme süresinin korunması. Viral video veya belirli izlenme sayısı garantisi verilmez.
- Tek bir aşırı tekrar izleme sonucu üzerinden içerik yönü değiştirilmez. Konu, dağıtım kaynağı ve video yaşının etkileri ayrı incelenir.

## Doğrulama ve sınırlar

Yerel regresyon testleri; yükleme hata kodu, yayın/önizleme sırası, sayı ölçeği/yönü, anahtarın hata mesajından çıkarılması, bozuk mum verisi, senaryo şeması ve örneklem/trend sınırlarını kapsar. Canlı Analytics erişimi ve güncel trend araması doğrulandı. 1080×1920, üç saniyelik test video FFmpeg ile üretildi; kartlar görsel kontrol edildi. Test videosu yayınlanmadı.

İnceleme ham yanıtları yerelde `output/channel_audit_raw.json` ve `output/channel_stats_28d.json` içindedir; bu dosyalar Git'e dahil edilmez. Test önizlemesi `output/review_preview/test_short.mp4` içindedir.

Kaynaklar: [YouTube Shorts keşif sinyalleri](https://support.google.com/youtube/answer/11914225?hl=en), [YouTube Analytics metrik tanımları](https://developers.google.com/youtube/analytics/metrics), [Shorts içerik analizi](https://support.google.com/youtube/answer/12942217?hl=en). Bu kaynaklar platform davranışını açıklar; kanal sayıları doğrudan yetkili API sorgularından alınmıştır.
