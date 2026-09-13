# Deniz: Creator ile kısa sunucu sahneleri

Kullanıcı Creator planında kalmayı, Deniz'i kısa açılış/geçişlerde kullanmayı ve bütün anlatımın Chris olması yönünü onayladı.

- Shorts: en fazla 6 saniyelik açılış. Uzun: en fazla 8 saniyelik açılış, en fazla 5 saniyelik tek orta geçiş (45 saniyeden uzun anlatımlarda). Sınırlar kelime zamanlamasından seçilir; mümkünse cümle sonunda kesilir.
- Yerel `--prepare-presenter` modu grafik videosu, kesintisiz anlatım, altyazılar ve kısa WAV parçalarını kalıcı bir klasöre çıkarır; başarılı hazırlıkta YouTube veya Telegram'a göndermez; hatalar mevcut bildirim yolunu kullanır.
- Creator arayüzünde her WAV, Deniz ile bir kez canlandırılır. İndirilen klipler pakette belirtilen adlarla eklenir. Bölüme özel ses yerine eski pilotun kullanılması kabul edilmez.
- Birleştirme, klip sesini kaynak WAV ile karşılaştırır ve süresini doğrular. Avatar sahneleri dışında mevcut grafik videosu kalır. Çıktının sesi grafik videosundan doğrudan kopyalanır; klip sesleri son videoya karıştırılmaz. Avatar sahnelerinde aynı zaman çizelgesindeki altyazılar uygulanır.
- Eksik avatar kliplerinin yerinde grafikler kalır. Bozuk/yanlış sesli klip varsa birleştirme hata verir; sessizce yanlış dudak hareketi yayımlamaz.
- Chris sürekliliği için ana pipeline ElevenLabs hatasında alternatif sese geçmez; üretimi durdurur. Bağımsız VoiceGenerator'ın Edge yedeği isteğe bağlı kullanılabilir.
- Varsayılan zamanlanmış yayın grafik akışını sürdürür. Avatar hazırlığı ayrı yerel moddur; tarayıcı oturumu CI'a taşınmaz, Pro API/başka ücretli servis eklenmez.
- Birleştirilmiş videonun metadata dosyası avatar kullanılmışsa `contains_synthetic_media=true` taşır. Bu komut yayın yapmaz; hazırlanmış dosyanın yüklenmesi ayrı iştir.

Doğrulama: sınır/kelime seçimi, yanlış klip sesi ve değiştirilmiş kaynak reddi, eksik klip yedeği, Chris hatası davranışı; gerçek FFmpeg ile kısa sentetik video testi. Canlı haber/video yayını yapılmadan test edilir.
