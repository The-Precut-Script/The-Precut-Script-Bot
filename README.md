<h1 align="center">
  <img src="https://media.discordapp.net/attachments/977518313217347604/1469341638986956931/TPS-Transparent.png?ex=69874e89&is=6985fd09&hm=7166255ffcbdc100486be9dde038eb25edcd7a34bd66cb7150de263c3ec304aa&=&format=webp&quality=lossless&width=972&height=972" width="120" alt="The Precut Script Bot"/>
  <br />
  The Precut Script Bot
</h1>

<p align="center">
  <b>Discord bot for automated media tools, with features ported and improved from the original After Effects extension.</b><br>
  <i>Queue-based Remove Background, Duplicate Deadframes Remover, and YouTube Downloader (Video/WebM + MP3) all features from the extension, now in bot form!</i>
</p>

<hr>

## 🎬 About

**The Precut Script Bot** is a Discord bot that helps editors by automating common AE extension tasks.  
The bot began as an After Effects extension, and its features were transferred and expanded for Discord:

- **Remove Background** (RMBG / `rembg` CPU) for a single image
- **Remove Duplicate/Dead Frames** for short videos (Discord upload-limit friendly)
- **YouTube Downloader** (separate Video/WebM + MP3 channels)

---

## 🚀 Features

- **Queue system (MySQL):** runs jobs one-at-a-time for Remove BG / Dedup / YouTube
- **System channels:** users can only submit the correct content (auto-deletes free chat)
- **Results channels:** optionally post output into a separate channel, show “Requested by @user”
- **Component Containers (V2):** Dedup + YouTube video use enhanced, interactive layouts (as in the extension)
- **Discord limits aware:** checks file sizes vs server boost limits (Ryujin-style 8MB / 50MB)

---

## ⚙️ How Does It Work?

1. Admin runs **`/managesystem`** inside a channel to set it as a submit channel:
   - Remove Background submit channel (image uploads)
   - Dedup submit channel (video uploads)
   - YouTube Download (MP4) channel (YouTube links, delivered as WebM for speed)
   - YouTube Download (MP3) channel (YouTube links)
2. Users drop an attachment/link in the configured channel.
3. The bot enqueues it in MySQL and processes jobs **sequentially**.
4. The result is posted in the same or in a results channel (mimicking the extension's workflow).

---

## 🛠️ Requirements

- **Python** 3.10+
- **FFmpeg** available on the machine (required for YouTube merge/copy + MP3 conversion)
- **MySQL** (required for channel config + queue)

<sub>*Runs on CPU; heavy workloads (e.g., background removal) should be throttled via `.env` limits.*</sub>

---

## 📦 Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure `.env`:
- Copy `.env.example` → `.env`
- Set `DISCORD_TOKEN`
- Set MySQL:
  - `MYSQL_HOST`
  - `MYSQL_USER`
  - `MYSQL_PASSWORD`
  - `MYSQL_DATABASE`

3. Run the bot:

```bash
python bot.py
```

---

## 🔗 Adding the bot to a server

1. Open [Discord Developer Portal](https://discord.com/developers/applications) → your app → **OAuth2 → URL Generator**
2. **Scopes:** `bot`, `applications.commands`
3. **Required permissions** (recommended):
   - View Channels, Send Messages, Read Message History
   - Attach Files, Embed Links
   - Manage Messages (pin setup messages + delete invalid submissions)
4. In **Bot → Privileged Gateway Intents**, enable **Message Content Intent** (needed for channel-based submission workflows as in the extension)

---

## 🎯 Commands / Setup

### Slash commands
- `/help` command list
- `/ping` status / latency
- `/info` about
- `/removebg` one-off remove background (attachment)
- `/dedup` one-off dedup (attachment)
- `/managesystem` configure submit channels (admin)

### Channel systems (submission)
- **Remove BG submit channel:** upload 1 image → bot returns PNG
- **Dedup submit channel:** upload 1 video → bot returns processed clip
- **YouTube video channel (labeled “MP4” in setup):** post a YouTube URL → bot returns WebM video (fast method)
- **YouTube MP3 channel:** post a YouTube URL → bot returns MP3 (320 kbps)
  
*All major extension features are supported as channels or commands.*

---

## 📸 Screenshots

**Duplicate Deadframes Remover** (feature originally from the extension)

![Duplicate Deadframes Remover setup](https://media.discordapp.net/attachments/977518313217347604/1469172364527800562/DDR-Setup.png?ex=6986b0e3&is=69855f63&hm=4adfb8e5a74bd2efd5e9b3b27a0f0c69ef1d80efcf188c9aa10b452ecee6733e&=&format=webp&quality=lossless&width=678&height=728)

**YouTube Audio Downloader**

![YouTube Audio Downloader setup](https://media.discordapp.net/attachments/977518313217347604/1469316584664338544/YTADL_Setup.png?ex=69873734&is=6985e5b4&hm=d9ae95bf745e3edbcb6fb3cb11c5201c2c2a98cc5686dff07e74aaba07b47c66&=&format=webp&quality=lossless&width=658&height=584)

**YouTube Video Downloader**

![YouTube Video Downloader setup](https://media.discordapp.net/attachments/977518313217347604/1469316584999747837/YTVDL_Setup.png?ex=69873734&is=6985e5b4&hm=496cccbce77cdeb802570cf07de0ed88f425ff4fb8969f888a39fa643999493c&=&format=webp&quality=lossless&width=606&height=814)

**Help Command**

![Help command output](https://media.discordapp.net/attachments/977518313217347604/1469342217796849849/image.png?ex=69874f13&is=6985fd93&hm=f1a37278c3ede6420f225184ae76273d992d7255e6ee85d285c71a63a61295e7&=&format=webp&quality=lossless&width=539&height=422)

---

<p align="center">
  <img src="https://badgen.net/badge/Built%20with/discord.py/blue" alt="discord.py" />
  <img src="https://badgen.net/badge/Queue/MySQL/green" alt="MySQL" />
  <img src="https://badgen.net/badge/Media/FFmpeg/red" alt="FFmpeg" />
</p>

## 📜 License
This project is licensed under the MIT License with Commons Clause.
Commercial sale or monetized distribution of this software is not allowed.
See the LICENSE file for details.