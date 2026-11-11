# Blue Archive Data Extraction Tools

Unified extraction pipeline to unpack Blue Archive game data, Live2D assets, timelines, audio cues, databases, and localization tables for the viewer.

## Main Pipeline: `extract_all.py`

Single unified script handling the end-to-end extraction workflow.

### Features
- **Database Tables**: Decrypts SQLCipher `ExcelDB.db` and exports FlatBuffer binary records into JSON tables (`CharacterExcelTable.json`, `CharacterDialogExcelTable.json`, `MemoryLobbyExcelTable.json`, `BGMExcelTable.json`).
- **Live2D Assets**: Extracts `.skel`, `.atlas`, and `.png` textures for all 275+ Memorial Lobby characters with skeleton priority scoring (main characters sorted ahead of background/scene props) and automatic atlas name/casing matching.
- **Timelines & Effects**: Parses Unity `TimelineClip` and `Animation Track` curves into `effects.json` (SpriteRenderer color fade/flash keyframes, GameObject active toggles, and audio cues).
- **Interactions**: Extracts bone IK bindings (`SpineDragIK`), interaction zones (pat, pinch, look, touch, cheek), and animation clips from `uilobbyelement` bundles into `live2d-interactions.json` and per-character `interactions.json`.
- **Audio & SFX**:
  - Automatically indexes AudioClips across `Preload/Android` and `GameData/Android` bundles.
  - Dynamically resolves external Unity CAB asset dependencies (`sf.externals`) to extract character, shared, and NPC sound effects into `.wav` audio cues.
  - Extracts voice packs (`JP_*.zip`, `KR_*.zip`) into `VOC_JP` / `VOC_KR` and generates `voice_sources.json`.
  - Table-driven BGM extraction: reads `BGMDBSchema` to resolve all 275+ Memorial Lobby tracks (including `Theme_*.ogg`, `AMB_*.ogg`, `BlueNewWorld_*.ogg`, and collaboration tracks like `BGM_TellYourWorld_Short.ogg`) without hardcoding, generating a comprehensive `bgm_map.json`.
- **Model Manifests**: Automatically generates sorted `info.json` manifests for both `en` and `jp` data routes.

### Requirements

```cmd
pip install UnityPy sqlcipher3-binary Pillow
```

### Usage

```cmd
python extract_all.py -k <SQLCIPHER_HEX_KEY> -i <GAME_DATA_INPUT_DIR> -o <VIEWER_OUTPUT_DIR> [OPTIONS]
```

#### Arguments
- `-k, --key`: SQLCipher 32-byte hexadecimal database key (64 characters, `0x` prefix optional).
- `-i, --input`: Game data input root directory (containing `AssetBundles/`, `TableBundles/`, `MediaResources/`).
- `-o, --output`: Viewer destination directory (typically `c++ port/svelte/static`).
- `-c, --character`: (Optional) Extract a single character key (e.g. `-c aru_home` or `-c ch0070_home`).
- `--force`: (Optional) Overwrite existing `.skel`, `.atlas`, `.png`, and audio files.
- `--skip-tables`: (Optional) Skip SQLCipher database extraction.
- `--skip-voices`: (Optional) Skip voice archive extraction.

#### Example

```cmd
python extract_all.py -k keyxxxx -i "game/data/location" -o "svelte/static"
```
