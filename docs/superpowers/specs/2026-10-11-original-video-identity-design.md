# US Stock Market Daily: özgün video kimliği tasarımı

Tarih: 2026-10-11

## Amaç ve mevcut durum

Kapaklar, anlatıcı sesi, Deniz karakteri ve video kurgusu birlikte tanınan bir kanal kimliği oluşturacak. Her bölüm doğrulanmış finans verisine dayanan kendine özgü bir yorum taşıyacak. Hedef, izleyicinin videoyu seçmesi, izlemesi ve yararlı bulmasıdır; YouTube'da öne çıkma garantisi yoktur.

Bugün uzun videonun kapağı `video_engine.py:create_thumbnail` ile aynı koyu zemin, ticker, yüzde ve grafik düzeninde üretiliyor. Shorts için ayrı kapak üretilmiyor. Ana anlatım hazır ElevenLabs Chris sesini kullanıyor. Deniz'in referans portresi ve kısa konuşan avatar pilotu var; avatar zamanlanmış yayına bağlı değil. Üretim Pexels görüntülerini ve grafik kartlarını kullanabiliyor. Bu parçalar yeni tasarıma geçerken kaynak ve güvenilirlik kontrolleriyle birlikte ele alınacak.

## Seçilen yön

**Editoryal finans afişi:** Sabit bir şablon yerine haberin türüne göre kompozisyon değişir. Ortak imza; belirgin tipografi, sınırlı renk ailesi, Deniz'in tutarlı yüzü ve kaynaklı bir görsel kanıttır. Her kapakta tek bir fikir ve en fazla bir ana sayı bulunur. Başlık ile kapak birbirini tamamlar; aynı cümleyi tekrarlamaz. Kurgusal bir görüntü gerçek olay fotoğrafı gibi sunulmaz.

Deniz, mevcut kurgusal yüz referansıyla korunur. Onun için daha ayırt edici bir kıyafet, renk ve sahne dili tasarlanır; yeni görseller referans portresiyle üretilir ve yüz tutarlılığı gözle kontrol edilir. Karakter kısa sunucu anlarında ve uygun kapaklarda görünür. Haber verisi ve açıklayıcı grafikler videonun ana görsel yükünü taşır. Görsel avatar üretimi yapılamayan bir çalışmada yanlış yüz veya uyumsuz dudak hareketi kullanılmaz.

Ana ses, hazır katalog sesinden yeni bir **Voice Design** sesiyle değiştirilir. İngilizce, net Amerikan telaffuzu, sıcak orta-alt tını, hafif kuru mizah ve ölçülü tempo hedeflenir. Aynı finans metniyle birkaç önizleme dinlenir; ticker, sayı ve özel isim telaffuzu, uzun anlatım tutarlılığı ve Deniz'in görünümüyle uyumu karşılaştırılır. Seçilen sesin kimliği ve ayarları kaydedilir. Dünya çapında tekillik iddia edilmez. Sentez veya ölçülmüş altyazı başarısız olursa yayın durur; sessizce başka sese geçilmez.

## Üretim akışı

1. Hikâye seçimi kaynak, tarih ve tekrar denetiminden geçer. Senaryo haberi yeniden okumakla yetinmez: doğrulanmış olay, neden önemli olduğu, karşı görüş veya belirsizlik ve izleyicinin izlemesi gereken sonraki veri noktası bulunur. Sayısal iddia kaynakla eşleşmelidir.
2. Senaryodan kapak için **tek vaat**, video için **ilk saniyelerde karşılığı verilen açılış**, Deniz'in kısa sahne metni ve görsel kanıt listesi çıkarılır. Merak unsuru olayın sonucunu abartmaz.
3. Uzun video kapağı üç konu ailesinden birini kullanır: şirket/ürün, para akışı/işlem, makro karar. Yerleşim aileye ve konuya göre değişir; aynı ticker-yüzde-grafik düzeni art arda kullanılmaz. Küçük ekranda okunabilirlik ve veri doğruluğu kontrol edilir.
4. Shorts'un ilk karesi aynı kimliği taşır; ilk birkaç saniye kapaktaki vaadi doğrudan açıklar. Uzun videoda görsel ritim; Deniz, veri animasyonu, kaynaklı belge/olay grafiği ve gerektiğinde lisanslı görüntü arasında değişir. Lisanslı stok görüntü tek başına videonun anlatısı haline gelmez.
5. Seçilen ses tüm anlatımda ve Deniz'in konuşan sahnelerinde aynı kalır. Avatar sahneleri mevcut ses dosyasına eşlenir; `presenter_workflow.py` içindeki süre ve ses eşleşmesi kontrolleri korunur. Yeni sesle tam senaryolarda süre/altyazı yeniden ölçülür.
6. Üretim çıktısı yayın öncesi görsel, ses ve bilgi doğruluğu denetiminden geçer. Değişiklik önce yayınlanmamış örneklerde doğrulanır; otomatik akışa ancak bu örnekler kabul edilebilir olduğunda bağlanır.

## Bileşen sınırları

- **Senaryo paketi:** Mevcut `script_generator.py` veri ve kaynaklarını kullanır; kapak vaadi, özgün yorum ve görsel kanıt alanlarını sağlar. Yayıncıya bağımlı değildir.
- **Kapak üreticisi:** `video_engine.py` içindeki kapak kodundan ayrılabilir bir modülde tasarım ailesini ve doğrulanmış metni görüntüye dönüştürür. Ses veya YouTube API çağrısı yapmaz.
- **Karakter varlıkları:** Deniz referansı, kabul edilen stil görselleri ve üretim kaydı tek yerde tutulur. Video birleştirici yalnız kabul edilen varlıkları kullanır.
- **Ses seçimi:** Önizlemeler ayrı bir yerel hazırlık adımıdır. Yayın akışı yalnız seçilen ses kimliğini kullanır; çıktı ve kelime zamanlamasını mevcut arayüzle sağlar.
- **Kalite kapısı:** Kaynak, sayı, kapak metni, ses/altyazı ve karakter eşleşmesini denetler. Hata, yayın öncesi açık neden olarak kaydedilir.

## Doğrulama ve başarı ölçüsü

İlk teslimde en az bir uzun video kapağı ve bir Shorts açılış karesi, aynı haber için ses örnekleri, Deniz'in kabul edilen stil karesi ve yayınlanmamış kısa video önizlemesi bulunur. Küçük boyutlu kapak okunur; sayı ve yön kaynakla uyumludur; ses özel isimleri anlaşılır söyler; avatar sesi ve dudak hareketi eşleşir. Üç farklı haber örneğinde kompozisyon ve yorumun gerçekten değiştiği gözle kontrol edilir.

Yayın sonrası değerlendirme aynı yaşta videolar ve uygun format karşılaştırmalarıyla yapılır: uzun videoda gösterimden izlemeye geçiş ve ilk 30 saniye tutulumu; Shorts'ta izledi/kaydırdı ve ortalama izleme oranı. Az gösterimli sonuçlardan kesin hüküm verilmez. İzlenme veya önerilme artışı tasarımın kabul şartı değildir.

## Sınırlar

Deniz'in adı çalışma adı olarak kalır. Karakter gerçek bir finans uzmanı veya yaşanmış deneyimleri olan biri gibi tanıtılmaz. Gerekli sentetik medya işareti mevcut yayın akışında korunur. Özgün üretim, başka yaratıcıların fikirlerini ya da görsellerini aynen kopyalamak anlamına gelmez. Üçüncü taraf hizmetlerin erişimi, maliyeti ve çıktı kalitesi uygulama aşamasında yeniden doğrulanır.
