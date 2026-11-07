# Blue Archive Viewer (Svelte)

Standalone SvelteKit port of the Blue Archive Memorial Lobby / Live2D viewer. Reads local game assets from the workspace data tree (`static/data/`).

## Features & Highlights

- **All 275+ Memorial Lobby Models**: Primary character skeletons prioritized over background props with multi-skeleton layering (`_home.skel`, `_bg.skel`, `_scene.skel`).
- **Unity Timeline & Visual Effects**: Opening fade-ins, keyframed timeline flashes, and color tints parsed directly from Unity animation tracks. Includes a one-click toggle to enable/disable visual effects.
- **Audio Engine (Howler.js & Web Audio)**:
  - Separate reactive volume sliders for **Voice** (0–100%), **BGM** (0–100%), and **SFX** (0–100%).
  - Independent SFX toggle checkbox.
  - Web Audio decoding with looping stream management and autoplay unlock recovery.
  - Complete Memorial Lobby BGM map (600+ keys) including event tracks and collaboration songs (e.g. Hatsune Miku *Tell Your World*).
- **Subtitles & Multilingual Voice**:
  - Subtitle display across 5 locales (EN, JP, KR, TW, TH) parsed from game dialog databases.
  - Multi-language voice packs (JP, KR).
- **Interactive Live2D Physics**:
  - Touch-bone hold/drag/release interactions (Pat, Pinch, Look, Cheek, Touch).
  - Scaled hit detection radii (`Math.max(140, 180 * scale)`) with automatic fallback to primary touch zones.
  - Screen blend mode for additive lighting layers to eliminate highlight blowouts.
- **Shareable URL Parameters**:
  - Full layout and audio state encoded into URL query parameters: `model`, `voice`, `voice_vol`, `bgm`, `bgm_vol`, `sfx`, `sfx_vol`, `effects`, `voice_lang`, `scale`, `x`, `y`, `sub`.
  - Parameters load strictly after model manifests and database tables are ready.
  - Built-in share link box with one-click clipboard copying.

## Development

```cmd
npm install
npm run check
npm run dev
```

The app uses Svelte 5 (runes), SvelteKit, PixiJS 7, Spine-Pixi 4.2, Howler.js, Tailwind CSS, and Bits UI.

During development, data is served from `static/data/`. Game data is ignored by Git.

## Production Build

```cmd
npm run build
```

Generates static site output in `build/`. Deploy alongside the game data directory mounted at `/data/`.
