# ⬇️ TurboDown - Ultimate Download Manager

**TurboDown** هو برنامج مدير تحميل متكامل، قوي، ومفتوح المصدر مكتوب بلغة بايثون. تم تصميمه ليكون أقوى وأسرع مدير تحميل مجاني، مع واجهة مستخدم رسومية حديثة ومظلمة (Dark-Themed GUI) ونظام تحميل متوازي فائق السرعة.

---

## 🚀 الميزات الخارقة (Key Features)

1. **التحميل متعدد القنوات فائق السرعة (64-128 Multi-threaded Downloading):**
   * يقوم المحرك بتقسيم الملف تلقائيًا إلى **64 اتصالاً متزامنًا** (وقابل للزيادة حتى **128 اتصالاً**) لتحقيق السرعة القصوى لخط الإنترنت لديك.
2. **استقرار تام ونظام إيقاف/استئناف ذكي (Cooperative Resume/Pause):**
   * إعادة تصميم كاملة لمحرك التحميل ليدعم إيقاف التحميل واستئنافه بشكل فوري وبدون أي مشاكل أو تلف للملفات.
3. **نظام إعادة المحاولة التلقائي (Auto-Retry with Backoff):**
   * عند حدوث أي انقطاع في الاتصال، يقوم التطبيق بإعادة المحاولة تلقائيًا حتى **10 مرات** مع زيادة ذكية في زمن الانتظار (Exponential Backoff) لضمان اكتمال التحميل.
4. **جالب فيديوهات يوتيوب الاحترافي (YouTube Video Grabber):**
   * يتيح لك تحميل الفيديوهات بأي جودة (4K, 1080p, 720p) أو تحميل الصوت فقط (MP3, M4A) بضغطة زر واحدة.
5. **مراقب الحافظة الذكي (Clipboard Monitor):**
   * يراقب الحافظة تلقائيًا ويلتقط روابط التحميل المباشرة وفيديوهات يوتيوب وروابط التورنت فور نسخها.
6. **دعم روابط التورنت المغناطيسية (Magnet Links Helper):**
   * عند نسخ أو إدخال رابط تورنت (Magnet Link)، يكتشفه التطبيق تلقائيًا ويعرض عليك فتحه فوراً في برنامج التورنت الافتراضي لديك (مثل qBittorrent).
7. **إدماج كامل بالمتصفحات (Chrome / Edge / Brave / Firefox Integration):**
   * اعتراض التحميلات تلقائياً من المتصفح وإرسالها للتطبيق مع نافذة منبثقة عائمة (Floating Widget) على صفحات اليوتيوب فوق مشغل الفيديو.
8. **محدد السرعة والجدولة الزمنية (Speed Limiter & Scheduler):**
   * تحكم كامل في سرعة التحميل، مع إمكانية جدولة التحميلات للبدء والإيقاف في أوقات محددة تلقائياً.
9. **العمل في الخلفية ونافذة الاكتمال (Background Tray & Completion Dialog):**
   * أيقونة مصغرة في شريط المهام (System Tray)، مع إشعارات ويندوز وتنبيهات صوتية ونافذة "اكتمل التحميل" الاحترافية لفتح الملف أو مكانه مباشرة.

---

## 📸 لقطات الشاشة (Screenshots)

> سيتم إضافة لقطات الشاشة قريباً

---

## 🛠️ متطلبات التشغيل والتثبيت (Installation)

### 1. تثبيت Python
تأكد من تثبيت [Python 3.10+](https://www.python.org/downloads/) (أو أحدث).

### 2. تثبيت المكتبات المطلوبة (Install Python Requirements)
افتح Terminal في مجلد المشروع وشغل الأمر التالي:

```bash
pip install -r requirements.txt
```

### 3. تثبيت FFMPEG (اختياري - لدمج فيديوهات اليوتيوب عالية الدقة)
لتحميل فيديوهات اليوتيوب بجودة عالية (مثل 1080p أو 4K)، يقوم يوتيوب بفصل الصوت عن الفيديو. يحتاج البرنامج إلى أداة **FFMPEG** لدمجهما تلقائيًا.

> **ملاحظة:** البرنامج يحاول تحميل ffmpeg تلقائياً عبر مكتبة `imageio-ffmpeg`. إذا لم يعمل تلقائياً:

**طريقة التثبيت اليدوي على Windows:**
1. قم بتحميل FFMPEG من الرابط الرسمي: [ffmpeg.org/download](https://ffmpeg.org/download.html)
2. فك الضغط عن الملف وانقل المجلد الناتج إلى مكان مناسب.
3. أضف مسار المجلد `bin` إلى متغيرات البيئة للويندوز (**System Environment Variables → PATH**).
4. تأكد من التثبيت بفتح cmd وكتابة: `ffmpeg -version`

---

## 🔌 طريقة تثبيت إضافات المتصفح (Browser Extension Setup)

### لمتصفحات Google Chrome / Edge / Brave:
1. افتح صفحة الإضافات في متصفحك: `chrome://extensions` (أو `edge://extensions`).
2. قم بتفعيل **وضع المطور (Developer Mode)** من الزاوية العلوية.
3. اضغط على زر **تحميل حزمة غير مضغوطة (Load unpacked)**.
4. اختر المجلد المسمى **`extension`** الموجود داخل مجلد المشروع.

### لمتصفح Firefox:
1. افتح صفحة المطورين في فايرفوكس: `about:debugging#/runtime/this-firefox`.
2. اضغط على زر **Load Temporary Add-on**.
3. اختر ملف `manifest.json` من المجلد المسمى **`extension_firefox`**.

---

## 🚀 طريقة التشغيل (How to Run)

### الطريقة 1: عبر سطر الأوامر
```bash
python app.py
```

### الطريقة 2: عبر ملف التشغيل (Windows)
انقر مرتين على ملف `start.bat` الموجود في مجلد المشروع.

> تأكد من بقاء البرنامج مفتوحاً أو يعمل في الخلفية (في شريط المهام بجانب الساعة) لتستمر إضافات المتصفح في اعتراض التحميلات وإرسالها إليه.

---

## 📂 هيكل المشروع (Project Structure)

```
TurboDown/
├── app.py                  # واجهة المستخدم الرسومية (GUI)
├── downloader.py            # محرك التحميل غير المتزامن (Async Engine)
├── video_grabber.py         # جالب فيديوهات يوتيوب (yt-dlp wrapper)
├── integration_server.py    # خادم API للمتصفح (Flask API)
├── start.bat               # ملف تشغيل سريع (Windows)
├── requirements.txt         # التبعيات المطلوبة
├── README.md               # هذا الملف
├── LICENSE                  # رخصة MIT
├── .gitignore              # ملفات مستثناة من Git
├── extension/              # إضافة Chrome/Edge/Brave (Manifest V3)
│   ├── manifest.json
│   ├── background.js
│   ├── content.js
│   ├── popup.html
│   ├── popup.js
│   └── icon.png
└── extension_firefox/       # إضافة Firefox (Manifest V2)
    ├── manifest.json
    ├── background.js
    ├── content.js
    ├── popup.html
    ├── popup.js
    └── icon.png
```

---

## 🤝 المساهمة (Contributing)

المساهمات مرحب بها! يرجى فتح Issue أو Pull Request لأي تحسين أو إصلاح.

---

## 📄 الترخيص (License)

هذا المشروع متوفر تحت رخصة **MIT** - تصفح ملف `LICENSE` لمزيد من التفاصيل.

---

# TurboDown - Ultimate Download Manager

**TurboDown** is a multi-threaded, highly optimized, open-source download manager built in Python. Designed to be a powerful, free download accelerator with a state-of-the-art dark-themed GUI and an ultra-fast download engine.

### Highlights
* **64-128 Concurrent Connections:** Turbocharges downloads by opening up to 128 parts concurrently.
* **Smart Cooperative Stop:** Completely robust pause/resume without file corruption or locks.
* **Auto-retry with Exponential Backoff:** 10 retries per part with smart wait times on network drops.
* **FFMPEG Integration:** Auto-merges high-definition YouTube video streams (1080p, 4K) with audio.
* **Browser Extension:** Advanced Manifest V3 extension for Chrome/Edge/Brave and MV2 for Firefox. Injects a floating download panel on YouTube players and intercepts standard browser downloads.
* **Magnet Link & Torrent Helper:** Auto-detects and forwards magnet/torrent links to your default Torrent client.
