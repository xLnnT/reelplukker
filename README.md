# ReelPlukker

Simpele desktop app om video's en foto's te downloaden van YouTube, Instagram en TikTok. Werkt op macOS en Windows.

Made by [Lennert Nuyttens](https://www.instagram.com/xLnnT/)

## Installeren

### macOS

1. Download `ReelPlukker-macos-arm64.zip` van de [Releases pagina](../../releases).
2. Dubbelklik de zip om uit te pakken.
3. Sleep `ReelPlukker.app` naar je `Programma's` (Applications) map.
4. **Eerste keer openen**: rechtsklik op de app → klik **Open** → in de popup klik nogmaals **Open**. Daarna kan je altijd dubbelklikken.

### Windows

1. Download `ReelPlukker-windows-x64.zip` van de [Releases pagina](../../releases).
2. Klik rechts op de zip → "Alles uitpakken" → kies een locatie.
3. Open de uitgepakte map en dubbelklik `ReelPlukker.exe`.
4. Bij de eerste keer kan Windows SmartScreen waarschuwen. Klik **Meer info** → **Toch uitvoeren**.

## Eerste keer Instagram of TikTok downloaden

De app heeft cookies nodig van Chrome om Instagram en TikTok posts te lezen. Bij je eerste IG of TikTok download:

- **macOS**: er verschijnt een Keychain-popup die vraagt om je computerwachtwoord. Klik **Altijd Toestaan** (`Always Allow`). Daarna vraagt het nooit meer.
- **Windows**: geen popup, werkt meteen.

> Let op: klik echt op **Altijd Toestaan** en niet alleen op **Toestaan**, anders krijg je de popup bij elke download opnieuw.

Zorg dat je in Chrome ingelogd bent op Instagram en TikTok voor je de app gebruikt.

## Hoe gebruiken

1. Open de app.
2. Plak een URL in het invoerveld.
3. Kies het gewenste format uit het dropdown (MP4 / MP3 / JPG / Original).
4. Klik op de ↓ knop of druk Enter.

Voor Instagram, TikTok en YouTube Shorts hoef je je niet druk te maken over het format — de app kiest automatisch het beste resultaat (carousel zip met alle slides, of volledig HD video).

Downloads gaan altijd naar je `Downloads` map. Klik op een voltooide tegel om het bestand te tonen in Finder/Explorer.

## Veiligheid en privacy

ReelPlukker is **volledig veilig en privé**:

- **Geen data verzameld.** De app verstuurt geen analytics, telemetrie of usage data.
- **Geen account nodig.** Je hoeft je nergens te registreren.
- **Geen derden.** Er gaat niks naar externe servers behalve de directe verbindingen met YouTube/Instagram/TikTok om de content te downloaden — net zoals je browser doet.
- **Lokaal.** Alle bestanden blijven op je eigen computer, niks wordt naar de cloud gestuurd.
- **Open source.** De code staat hier op GitHub, iedereen kan controleren wat de app doet.
- **Cookies blijven privé.** Je Chrome cookies worden alleen lokaal gelezen om in te loggen bij IG/TikTok — ze worden nooit ergens naartoe gestuurd.

## Geen Keychain popup? (optioneel)

Als je liever helemaal geen popup wil:

1. Installeer de Chrome extensie [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc).
2. Log in op Instagram in Chrome → open een instagram.com pagina → klik de extensie → "Export As → Netscape" → save als `cookies.txt`.
3. Plaats het bestand op:
   - **macOS**: `~/.reelplukker/cookies.txt`
   - **Windows**: `%USERPROFILE%\.reelplukker\cookies.txt`
4. Voor TikTok hetzelfde doen en de regels onder de IG cookies plakken in dezelfde file.

Cookies verlopen na enkele weken/maanden — exporteer opnieuw als downloads stoppen met werken.

## Wat de app kan

- **YouTube**: MP4 in 1080p, 1440p, 4K of 8K. Of audio als MP3.
- **YouTube Shorts**: automatisch 1080p MP4.
- **Instagram**: foto's, video's, carousels (mixed photo+video komt als zip met `slide 1.jpg`, `slide 2.mp4`, ...).
- **TikTok**: video's en photo slideshows.
- **Directe file URLs**: alles wat eindigt op `.mp4`, `.jpg`, `.pdf`, ...

Video's worden automatisch geconverteerd naar H.264/HEVC mp4 zodat ze direct werken in Premiere, Final Cut en QuickTime.

## Lokaal ontwikkelen

Vereist Python 3.12+ en ffmpeg.

```bash
pip install -r requirements.txt
# macOS:
brew install ffmpeg
# Windows:
choco install ffmpeg
python3 main.py
```

## Zelf builden

Builds gebeuren automatisch via GitHub Actions bij elke push en bij tags die starten met `v` (bv. `v0.1.0`).

Lokaal builden:

```bash
pip install pyinstaller
# Plaats ffmpeg en ffprobe binaries in ./bin/
pyinstaller --noconfirm ReelPlukker.spec
```

Output verschijnt in `dist/`.
