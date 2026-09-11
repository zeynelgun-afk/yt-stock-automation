# Proje özeti

Güncel kurulum, yayın takvimi ve davranış: [README.md](README.md).
Kanal verileri, hata düzeltmeleri ve büyüme deneyi: [GROWTH_AUDIT.md](GROWTH_AUDIT.md).

Bu sistem YouTube'a **otomatik yayın** yapar; Telegram onay kapısı değildir.

- Veri: FMP, isteğe bağlı CNN Fear & Greed ve Reddit bağlamı.
- İçerik: kaynaklı hikâye seçimi, güncel finans videosu konu ilgisi, LLM senaryosu.
- Üretim: ElevenLabs → Edge-TTS; gerçek mum verisi, ASS altyazı, FFmpeg.
- Görseller: yapılandırılmışsa Higgsfield, ardından Pexels/yerel grafik yedekleri.
- Yayın: YouTube OAuth; yayın sonrası Telegram önizlemesi.
- Öğrenme: YouTube Analytics, örneklem sınırı olan Shorts ağırlıkları, ölçülen ses hızı.
- Çalıştırma: GitHub Actions; saatlerin asıl kaynağı workflow dosyasıdır.

Eski özetin ücretsiz çalışma, insan onayı, sabit süre ve saat ifadeleri güncel kodla çeliştiği için kaldırıldı.
