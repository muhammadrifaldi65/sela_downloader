

# Sela Downloader

Aplikasi desktop sederhana untuk mengunduh video, audio, dan gambar dari internet.

- Video & Audio: menggunakan yt-dlp (mendukung YouTube, TikTok, Instagram, X/Twitter,
  Facebook, dan ratusan situs lain).
- Foto halaman: mengambil gambar yang tercantum di HTML (img/srcset/metadata).
- File langsung: menggunakan requests dengan URL langsung ke file.

Cara pakai:
    pip install requests yt-dlp
    python downloader_app.py

Tempel URL, pilih jenis unduhan dan folder tujuan, lalu klik Unduh sekarang.
Video: Terbaik atau batas tinggi 360–2160 piksel; tidak melakukan upscale.
Audio: bitrate keluaran MP3 96–320 kbps; tidak meningkatkan kualitas sumber.
Foto halaman tidak memuat gambar yang hanya muncul setelah interaksi JavaScript.
Dukungan situs mengikuti yt-dlp; tidak menjamin semua situs atau bebas deteksi bot.

Catatan: untuk ekstrak audio (mp3) dibutuhkan ffmpeg terpasang di sistem.
Gunakan aplikasi ini hanya untuk konten yang memang boleh/berhak Anda unduh.
