# Blue Archive Memorial Lobby (Live2D) Viewer

base on [this](https://github.com/respectZ/blue-archive-viewer)

preview at [https://ba-viewer.yurixahri.net](https://ba-viewer.yurixahri.net)

---
## Disclaimer & Legal Notice

This project and documentation are strictly for educational, security research, and personal archive purposes.

> **DISCLAIMER:** The authors, contributors, and maintainers of this project are **NOT** responsible for any game bans, account suspensions, damages, legal actions, or lawsuits resulting from the use of Frida, memory inspection, asset extraction, or any tools mentioned in this guide. Use at your own risk — do it yourself and take full personal responsibility. All game assets, characters, and trademarks belong to their respective copyright holders (NEXON Games, Yostar, etc.).
> 
## 1. Get DB key and Game data
Grab a compatible frida with your os [https://github.com/frida/frida](https://github.com/frida/frida).
To decrypt `ExcelDB.db`, a 32-byte hexadecimal SQLCipher encryption key is required. If you need to dump this key from the game client:

```cmd
frida -n "BlueArchive.exe" -l key_finder.js
```

1. Launch Blue Archive on your PC or emulator.
2. In a command prompt, run the command above while the game process is running.
3. The hook script intercepts the SQLCipher opening call and outputs the 64-character hex key.
4. Copy this key for use with the extraction pipeline in Step 2 (`-k <SQLCIPHER_HEX_KEY>`).

For game data use this tool [https://github.com/Deathemonic/BA-AD](https://github.com/Deathemonic/BA-AD)
Run this command to get global assets (only support global for this project)
```cmd
baad download global --output where/you/want/to/save
```

## 2. Prerequisites

### Software
- **Node.js**: v18+ (v20+ recommended)
- **Python**: 3.10+
- **Git**

### Python Dependencies
Install required packages for game asset extraction:

```cmd
pip install UnityPy sqlcipher3-binary Pillow
```

### Node.js Dependencies
Install dependencies for the Svelte viewer:

```cmd
cd svelte
npm install
```

---

## 3. Asset Extraction Pipeline

Use `extract_all.py` under `tools/` to extract all models, textures, animations, voice packs, BGM tracks, and dialog databases from raw Blue Archive client data.

### Command

```cmd
python "tools/extract_all.py" -k <SQLCIPHER_HEX_KEY> -i <RAW_GAME_DATA_DIR> -o "svelte/static"
```

### Parameters
- `-k, --key`: 32-byte hexadecimal SQLCipher key for `ExcelDB.db` (64 hex characters, `0x` prefix optional).
- `-i, --input`: Directory holding raw game data (`AssetBundles/`, `TableBundles/`, `MediaResources/`).
- `-o, --output`: Destination directory for extracted static assets (`svelte/static`).
- `-c, --character`: (Optional) Extract a single character (e.g. `-c aru_home` or `-c ch0070_home`).
- `--force`: (Optional) Overwrite existing `.skel`, `.atlas`, `.png`, and audio files.
- `--skip-tables`: (Optional) Skip database table extraction if tables are already exported.
- `--skip-voices`: (Optional) Skip voice archive extraction if voices are already extracted.

### Example Run

```cmd
python "tools/extract_all.py" -k keyxxxxx -i "E:/Games/AssetStudio/output/data" -o "svelte/static"
```

### What Gets Generated
1. **Live2D Models** (`svelte/static/data/en/GameData/Android/<character>/`):
   - `.skel` binary skeleton hierarchy.
   - `.atlas` texture atlas with matched naming.
   - `.png` RGBA textures.
   - `effects.json` keyframed timeline curves for opening transitions and screen flashes.
   - `interactions.json` touch bone IK limits and animation bindings.
2. **Model Manifests**:
   - `info.json` mapping all 275+ characters with primary skeletons prioritized over background props.
3. **Audio**:
   - `BGM/`: Memorial Lobby themes (`Theme_*.ogg`) and collaboration songs (`BGM_TellYourWorld_Short.ogg`).
   - `bgm_map.json`: Mappings from every character to their respective lobby theme.
   - `VOC_JP/` and `VOC_KR/`: Extracted voice clips.
   - `voice_sources.json`: Multi-language voice manifest.
4. **Localization & Databases**:
   - `CharacterExcelTable.json`: Student metadata.
   - `CharacterDialogExcelTable.json`: Subtitles across EN, JP, KR, TW, TH.
   - `MemoryLobbyExcelTable.json`: Lobby-to-BGM and character associations.

---

## 4. Running the Web Viewer

### Development Mode

```cmd
cd svelte
npm run dev
```

Open your browser at `http://localhost:5173/`.

### Type Checking

```cmd
cd svelte
npm run check
```

---

## 5. Build & Deployment

```cmd
cd svelte
npm run build
```

The compiled application will be generated in `svelte/build/`.

### Deployment Notes
The extracted game assets in `svelte/static/data/` are served at `/data/`. When hosting with a static web server (such as Nginx, Caddy, or Python HTTP server), ensure requests to `/data/*` are mapped to your extracted asset directory.

---

## 6. Viewer Controls & Features

- **Character Selection**: Select any of the 275+ Memorial Lobby models from the settings sidebar (`⚙`).
- **Audio Sliders**:
  - Independent volume controls for **Voice**, **BGM**, and **SFX** (0–100%).
  - Audio toggles for Voice, BGM, and SFX.
- **Visual Effects Toggle**:
  - Checkbox to toggle screen fades, flashes, and light washes.
  - Skeletons load first before opening transition effects play.
- **Interactions**:
  - Tap character to play talk lines with subtitles.
  - Click and drag interactive areas (head pat, cheek pinch, eyes/look, touch).
- **Subtitles & Voice**:
  - Subtitle languages: English, Japanese, Korean, Traditional Chinese, Thai.
  - Voice audio locales: Japanese (JP), Korean (KR).
- **Shareable Layout Links**:
  - Copy layout URL containing current model, scale, offsets, audio states, and subtitle settings via the share box in the sidebar.

## 7. Todo
- Particle effect support (for now I dont have logic to play correct particle effect, so I remove it, only keep the flash, white fade out...)

