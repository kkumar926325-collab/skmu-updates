# SKMU Updates (v2)

SKMU Dumka ke students ke liye updates app: Admission, Result, Form, Exam, Notice, Scholarship.
Sirf **admin (aap)** post karte ho. Log padhte hain aur **sawal** puchh sakte hain.

```
skmu-updates/
├── backend/            Flask + SQLite server  (+ static/ = poori app ka design)
├── android/            Android app (WebView + notification)
├── store/              Play Store icon (512) aur feature graphic (1024x500)
└── .github/workflows/  APK / AAB build (GitHub Actions)
```

## Features

- Home, Dates (aane wali last dates), Guide (admission guide), Info (about/contact/privacy)
- Category + Course (BA, BSc, BCom...) + Semester filter, search
- Post me photo, last date (kitne din bache), link, pin, "NEW" tag
- Post **edit** karna, delete karna
- Sawal/jawab, galat sawal ka **Report** button, admin ke liye jawab/delete
- Dark mode, Hindi / English
- Offline: net na ho tab bhi purani posts dikhti hain
- Naye update par **notification** (Firebase ke bina; har ~15 min me check)
- Admin: stats (kitne users), roz ka auto **backup** (last 7 rakhe jate hain), result link / contact / guide ka text app se hi badalna
- Privacy Policy page: `/privacy`

## 1. Server (Termux)

```bash
pkg install python
cd ~/skmu-updates/backend
pip install -r requirements.txt   # (sirf flask chahiye: pip install flask)
python app.py
```

Pehli baar **ADMIN KEY** screen par aati hai (`admin_key.txt` me bhi). Browser me `127.0.0.1:5000` kholo.

Options (environment variables): `SKMU_ADMIN_KEY` (apni key), `SKMU_AUTO_DELETE_DAYS=7` (7 din se purani unpinned posts apne aap hatengi, photo bhi), `PORT`.

Purane version se update: nayi `app.py` aur `static/` folder copy karo. Purana `skmu.db` waise hi chalega (naye columns apne aap judte hain).

## 2. Admin kaise bano

"SKMU Updates" title par 5 baar jaldi tap karo, ya **Info** tab → Admin login. Phir:
- Home par **＋** → nayi post
- Post kholo → **Edit / Delete / Jawab dein**
- Info → **Result link, contact, guide text badlo** (yahan result website ka link daaloge to home par "Result dekhein" button aa jayega)

## 3. Online server (Play Store se pehle zaroori)

Termux server sirf aapke phone par chalta hai. Baaki students ke liye `backend/` ko kisi Python hosting par chalao jahan **https** ho aur file (skmu.db, uploads/) restart par na ude (persistent disk). Hosting ki current free-plan sharten khud check karo.

Phir `android/app/src/main/java/com/skmu/updates/Config.kt` me `BASE_URL` apne https address par badlo. (Testing ke liye `http://127.0.0.1:5000` hi rehne do. Android app ab sirf localhost par http allow karti hai, baaki sab https.)

Notification kaise kaam karta hai: app har ~15 minute me `/api/latest` dekhti hai. Nayi post mili to notification. Ye turant nahi aata (phone ki battery-saving ki wajah se kabhi der bhi ho sakti hai). Instant push chahiye to baad me Firebase jod sakte hain.

## 4. APK banana (GitHub Actions)

```bash
cd ~/skmu-updates
git init && git add . && git commit -m "SKMU Updates v2"
git branch -M main
git remote add origin https://github.com/<username>/skmu-updates.git
git push -u origin main
```

GitHub → Actions → **Build SKMU Updates** → artifact `SKMU-Updates` (debug APK, phone me install karke test karo).

## 5. Play Store ke liye signed AAB

```bash
pkg install openjdk-17
keytool -genkey -v -keystore release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias skmu
base64 -w0 release.jks
```

`release.jks` ka **backup** rakho (kho gayi to app update nahi kar paoge). GitHub → Settings → Secrets → Actions: `KEYSTORE_BASE64`, `KEYSTORE_PASSWORD`, `KEY_ALIAS` (= skmu), `KEY_PASSWORD`. Phir workflow dobara chalao, artifact me `.aab` milegi.

## 6. Play Console checklist

- Icon: `store/play-icon-512.png`, Feature graphic: `store/play-feature-graphic-1024x500.png`; screenshots khud phone se lo
- **Privacy Policy URL:** `https://<aapka-server>/privacy`
- Description me likho: "Unofficial student-run app" + official website ka naam; university ka naam/logo official dikhane wali koi cheez mat lagao
- User-generated content: app me Report button aur admin moderation hai; Play Console ke form me yahi batao
- Data safety form: naam + sawal ka text (user ke likhe), random device ID (count ke liye); koi ad nahi
- Developer account ki ek baar ki fee lagti hai; targetSdk ki current requirement `app/build.gradle` me check karte raho

## 7. Google Drive (15 GB)

Bade PDF / form Drive me upload karo → "Anyone with the link" → link post ke link box me. Photos server par jaati hain (app khud chhoti kar deti hai, ~200-400 KB). Har hafte purani posts hatao ya `SKMU_AUTO_DELETE_DAYS=7` lagao.
