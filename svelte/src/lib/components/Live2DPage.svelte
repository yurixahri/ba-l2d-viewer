<script lang="ts">
  import { onMount } from "svelte";
  import { Howl } from "howler";
  import Navbar from "$lib/components/Navbar.svelte";
  import Button from "$lib/components/ui/button.svelte";
  import Select from "$lib/components/ui/select.svelte";
  import Live2DStage from "$lib/components/Live2DStage.svelte";
  import {
    fetchModelIndex,
    fetchViewerTables,
    subtitlesFor,
    type Dialog,
    type MemoryLobbyRecord,
    type Region,
    type VoiceLocale,
    type SubtitleLocale,
    type VoiceSource,
    resolveCharacterId
  } from "$lib/live2d-data";

  let { region }: { region: Region } = $props();

  let models = $state<Record<string, string[]>>({});
  let modelIds = $state<string[]>([]);
  let selectedModel = $state("");
  let animations = $state<string[]>([]);
  let selectedAnimation = $state("");
  let specialAnimation = $state("");
  let dialogs = $state<Dialog[]>([]);
  let characters = $state<Awaited<ReturnType<typeof fetchViewerTables>>["characters"]>([]);
  let memoryLobbies = $state<MemoryLobbyRecord[]>([]);
  let voiceSources = $state<Record<string, VoiceSource>>({});
  let bgmMap = $state<Record<string, { CharacterId?: number; PrefabName?: string; BGMId: number; filename: string; path: string }>>({});
  let voiceLocale = $state<VoiceLocale>("JP");
  let subtitleLocale = $state<SubtitleLocale>("JP");
  let playVoice = $state(true);
  let playBGM = $state(true);
  let playSfx = $state(true);
  let playEffects = $state(true);
  let voiceVolume = $state(.35);
  let bgmVolume = $state(0.05);
  let sfxVolume = $state(0.25);
  let loopAnimation = $state(false);
  let scale = $state(1);
  let offsetX = $state(0);
  let offsetY = $state(0);
  let customScaleSet = false;
  let customOffsetSet = false;
  let bgm = $state<Howl>();
  let activeBgmTrack = $state("");
  let showSubtitles = $state(false);
  let error = $state("");
  let loading = $state(true);
  let stage = $state<Live2DStage>();
  let settingsOpen = $state(false);
  let copied = $state(false);

  let shareableUrl = $derived.by(() => {
    if (typeof window === "undefined") return "";
    const p = new URLSearchParams();
    if (selectedModel) p.set("model", selectedModel);
    p.set("voice", playVoice ? "1" : "0");
    p.set("voice_vol", voiceVolume.toFixed(2));
    p.set("bgm", playBGM ? "1" : "0");
    p.set("bgm_vol", bgmVolume.toFixed(2));
    p.set("sfx", playSfx ? "1" : "0");
    p.set("sfx_vol", sfxVolume.toFixed(2));
    p.set("effects", playEffects ? "1" : "0");
    p.set("voice_lang", voiceLocale);
    p.set("scale", scale.toFixed(2));
    p.set("x", Math.round(offsetX).toString());
    p.set("y", Math.round(offsetY).toString());
    p.set("sub", showSubtitles ? "1" : "0");
    return `${window.location.origin}${window.location.pathname}?${p.toString()}`;
  });

  function copyShareableLink() {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(shareableUrl);
      copied = true;
      setTimeout(() => (copied = false), 2000);
    }
  }

  let modelUrls = $derived(selectedModel ? models[selectedModel] ?? [] : []);
  let subtitles = $derived(showSubtitles && selectedAnimation
    ? subtitlesFor(selectedModel, selectedAnimation, dialogs, characters, subtitleLocale)
    : []);
  let specialAnimations = $derived(animations.filter(
    (name) =>
      name.endsWith("_M") &&
      !/^(Talk|Idle|Start_Idle)/i.test(name) &&
      !/(?:End|Finish|Release)(?:_|$)/i.test(name),
  ));
  $effect(() => {
    if (specialAnimations.length && !specialAnimations.includes(specialAnimation)) {
    specialAnimation = specialAnimations[0];
    }
  });

  onMount(async () => {
    try {
      const [modelIndex, tables, availableVoices] = await Promise.all([
        fetchModelIndex(region),
        fetchViewerTables(region),
        fetch("/data/jp/MediaResources/GameData/Audio/voice_sources.json").then(async (response) => {
          if (!response.ok) throw new Error(`Failed to load voice-source map (${response.status})`);
          return response.json() as Promise<Record<string, VoiceSource>>;
        })
      ]);
      models = modelIndex;
      modelIds = Object.keys(modelIndex).sort();
      selectedModel = modelIds[0] ?? "";
      dialogs = tables.dialogs;
      characters = tables.characters;
      memoryLobbies = tables.memoryLobbies;
      voiceSources = availableVoices;
      subtitleLocale = region === "en" ? "EN" : "JP";

      try {
        const bgmRes = await fetch("/data/MediaResources/GameData/Audio/bgm_map.json");
        if (bgmRes.ok) {
          bgmMap = await bgmRes.json();
        }
      } catch {
        // optional map
      }

      // Load URL parameters only after all models & tables are ready
      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);

        if (params.has("model")) {
          const req = params.get("model")!.toLowerCase();
          const found = modelIds.find((id) => id.toLowerCase() === req || id.toLowerCase() === `${req}_home`);
          if (found) selectedModel = found;
        }

        if (params.has("voice")) {
          playVoice = params.get("voice") === "1" || params.get("voice") === "true";
        }
        if (params.has("voice_vol")) {
          const v = parseFloat(params.get("voice_vol")!);
          if (!isNaN(v)) voiceVolume = Math.max(0, Math.min(1, v));
        }

        if (params.has("bgm")) {
          playBGM = params.get("bgm") === "1" || params.get("bgm") === "true";
        }
        if (params.has("bgm_vol")) {
          const v = parseFloat(params.get("bgm_vol")!);
          if (!isNaN(v)) bgmVolume = Math.max(0, Math.min(1, v));
        }

        if (params.has("sfx")) {
          playSfx = params.get("sfx") === "1" || params.get("sfx") === "true";
        }
        if (params.has("sfx_vol")) {
          const v = parseFloat(params.get("sfx_vol")!);
          if (!isNaN(v)) sfxVolume = Math.max(0, Math.min(1, v));
        }

        if (params.has("effects")) {
          playEffects = params.get("effects") === "1" || params.get("effects") === "true";
        } else if (params.has("effect")) {
          playEffects = params.get("effect") === "1" || params.get("effect") === "true";
        }

        if (params.has("voice_lang")) {
          const lang = params.get("voice_lang")!.toUpperCase() as VoiceLocale;
          if (voiceSources[lang]) {
            voiceLocale = lang;
          } else {
            voiceLocale = "JP";
          }
        }

        if (params.has("scale")) {
          const s = parseFloat(params.get("scale")!);
          if (s > 0) {
            scale = s;
            customScaleSet = true;
          }
        }
        if (params.has("x")) {
          const px = parseFloat(params.get("x")!);
          if (!isNaN(px)) {
            offsetX = px;
            customOffsetSet = true;
          }
        }
        if (params.has("y")) {
          const py = parseFloat(params.get("y")!);
          if (!isNaN(py)) {
            offsetY = py;
            customOffsetSet = true;
          }
        }

        if (params.has("sub")) {
          showSubtitles = params.get("sub") === "1" || params.get("sub") === "true";
        }
      }
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      loading = false;
    }
  });

  let selectedBgm = $derived.by(() => {
    if (!selectedModel) return null;
    const key = selectedModel.toLowerCase();
    const short = key.replace(/_home.*$/i, "").replace(/_teen.*$/i, "").replace(/_multi.*$/i, "");
    const base = short.replace(/\d+$/, "");
    const fromMap = bgmMap[key] ?? bgmMap[short] ?? bgmMap[base];
    if (fromMap?.BGMId) return fromMap;

    const charId = resolveCharacterId(selectedModel, characters);
    const lobby = memoryLobbies.find((row) => row.CharacterId === charId);
    const bgmId = lobby?.BGMId ?? 0;
    if (bgmId > 0) {
      const filename = bgmId === 10004
        ? "BGM_TellYourWorld_Short.ogg"
        : `Theme_${bgmId.toString().padStart(2, "0")}.ogg`;
      return {
        BGMId: bgmId,
        filename,
        path: `/data/MediaResources/GameData/Audio/BGM/${filename}`,
      };
    }
    return null;
  });

  $effect(() => {
    const target = selectedBgm;
    if (playBGM && target?.path) {
      if (activeBgmTrack !== target.path) {
        bgm?.stop();
        activeBgmTrack = target.path;
        bgm = new Howl({
          src: [target.path],
          html5: false,
          loop: true,
          volume: bgmVolume,
          preload: true,
          onloaderror: (_id, reason) => console.error("Failed to load lobby BGM:", reason),
          onplayerror: (_id, reason) => {
            console.warn("BGM autoplay blocked, retrying on unlock:", reason);
            bgm?.once("unlock", () => bgm?.play());
          },
        });
        bgm.play();
      } else if (!bgm?.playing()) {
        bgm?.play();
      }
    } else if (!playBGM && bgm) {
      bgm.stop();
      activeBgmTrack = "";
    }
  });

  $effect(() => {
    if (bgm) {
      bgm.volume(bgmVolume);
    }
  });

  function onReady({ animations: names, scale: readyScale }: { animations: string[]; scale: number }) {
    error = "";
    animations = names;
    if (!customScaleSet) {
      scale = readyScale;
    }
    if (!customOffsetSet) {
      offsetX = window.innerWidth / 2;
      offsetY = window.innerHeight;
    }
    stage?.setOffset(offsetX, offsetY);
    stage?.setScale(scale);
    selectedAnimation = animations.find((name) => name.toLowerCase() === "start_idle_01")
      ?? animations[0]
      ?? "";
    specialAnimation = specialAnimations[0] ?? "";
  }

  function setScale() {
    stage?.setScale(scale);
  }

  function setOffset() {
    stage?.setOffset(offsetX, offsetY);
  }

  function chooseAnimation(event: Event) {
    const value = (event.currentTarget as HTMLSelectElement).value;
    selectedAnimation = value;
    stage?.playAnimation(value);
  }

  function onAnimation({ name }: { name: string }) {
    selectedAnimation = name;
  }

  function playSpecialAnimation() {
    if (!specialAnimation) return;
    selectedAnimation = specialAnimation;
    stage?.playAnimation(specialAnimation);
  }
</script>

<svelte:head>
  <title>{region.toUpperCase()} Live2D | Blue Archive</title>
</svelte:head>

<main class="relative h-screen w-screen overflow-hidden">
  {#if modelUrls.length}
    <Live2DStage
      bind:this={stage}
      modelId={selectedModel}
      {modelUrls}
      {voiceLocale}
      {playVoice}
      {voiceVolume}
      {playSfx}
      {sfxVolume}
      {playEffects}
      {voiceSources}
      tapToTalk={true}
      loopAnimation={loopAnimation}
      onready={onReady}
      onanimation={onAnimation}
      onscale={(event) => (scale = event.value)}
      onerror={(event) => (error = event.message)}
    />
  {/if}

  <div class="fixed left-0 top-0 z-10 flex h-12 w-20 items-center justify-center">
    <Button variant="ghost" ariaLabel="Open settings" onclick={() => (settingsOpen = !settingsOpen)}>
      <span class="text-xl" aria-hidden="true">⚙</span>
    </Button>
  </div>
  <aside class={`fixed left-0 top-0 z-20 h-full w-full overflow-y-auto bg-neutral-900/95 p-6 transition-transform sm:w-96 ${settingsOpen ? "translate-x-0" : "-translate-x-full"}`}>
    <div class="mb-6 flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Live2D Settings</h1>
      <Button variant="ghost" ariaLabel="Close settings" onclick={() => (settingsOpen = false)}>×</Button>
    </div>
    <div class="grid gap-5">
      {#if modelIds.length}
        <Select label="Model" bind:value={selectedModel} options={modelIds.map((id) => ({ value: id, label: id }))} />
      {/if}
      {#if animations.length}
        <label class="grid gap-1.5 text-sm">
          <span class="text-slate-300">Animation</span>
          <select class="h-10 rounded-md border border-white/20 bg-slate-950 px-3" value={selectedAnimation} onchange={chooseAnimation}>
            {#each animations as animation}<option value={animation}>{animation}</option>{/each}
          </select>
        </label>
      {/if}
      {#if specialAnimations.length}
        <div class="grid gap-2">
          <Select
            label="Available model actions"
            bind:value={specialAnimation}
            options={specialAnimations.map((name) => ({ value: name, label: name }))}
          />
          <Button variant="outline" onclick={playSpecialAnimation}>Play action</Button>
          <p class="text-xs text-slate-400">
            Actions are detected from this model's animation names. Matching _A clips are blended automatically.
          </p>
        </div>
      {/if}
      <p class="text-xs text-slate-400">
        Click to play talk animations. Also you can interact with the model by clicking and dragging certain areas on it.
      </p>
      <div class="rounded-md border border-white/10 bg-black/20 p-3 grid gap-3">
        <h2 class="text-sm font-semibold text-slate-200">Audio Settings</h2>
        <label class="flex items-center gap-3 text-sm text-slate-300">
          <input type="checkbox" bind:checked={playVoice} /> Play voice
        </label>
        {#if playVoice}
          <label class="grid gap-1 text-xs text-slate-400">
            <span>Voice Volume: {Math.round(voiceVolume * 100)}%</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              bind:value={voiceVolume}
              oninput={(e) => { voiceVolume = parseFloat(e.currentTarget.value); }}
              class="w-full accent-blue-500"
            />
          </label>
        {/if}

        <label class="flex items-center gap-3 text-sm text-slate-300">
          <input type="checkbox" bind:checked={playBGM} /> Play BGM
        </label>
        {#if playBGM}
          <label class="grid gap-1 text-xs text-slate-400">
            <span>BGM Volume: {Math.round(bgmVolume * 100)}%</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              bind:value={bgmVolume}
              oninput={(e) => {
                bgmVolume = parseFloat(e.currentTarget.value);
                if (bgm) bgm.volume(bgmVolume);
              }}
              class="w-full accent-blue-500"
            />
          </label>
        {/if}

        <label class="flex items-center gap-3 text-sm text-slate-300">
          <input type="checkbox" bind:checked={playSfx} /> Play SFX
        </label>
        {#if playSfx}
          <label class="grid gap-1 text-xs text-slate-400">
            <span>SFX Volume: {Math.round(sfxVolume * 100)}%</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              bind:value={sfxVolume}
              oninput={(e) => { sfxVolume = parseFloat(e.currentTarget.value); }}
              class="w-full accent-blue-500"
            />
          </label>
        {/if}
      </div>

      <label class="flex items-center gap-3 text-sm text-slate-300">
        <input type="checkbox" bind:checked={loopAnimation} /> Loop animation
      </label>
      <label class="flex items-center gap-3 text-sm text-slate-300">
        <input type="checkbox" bind:checked={playEffects} /> Play visual effects
      </label>
      <Select
        label="Voice language"
        bind:value={voiceLocale}
        options={[
          { value: "JP", label: `Japanese (JP)${voiceSources.JP ? "" : " — unavailable"}`, disabled: !voiceSources.JP },
          { value: "KR", label: `Korean (KR)${voiceSources.KR ? "" : " — unavailable"}`, disabled: !voiceSources.KR },
          { value: "CN", label: `Chinese (CN)${voiceSources.CN ? "" : " — unavailable"}`, disabled: !voiceSources.CN }
        ]}
      />
      <label class="grid gap-1 text-sm text-slate-300">
        Scale
        <input class="rounded border border-white/20 bg-slate-950 px-3 py-2" type="number" min="0.05" step="0.05" bind:value={scale} onchange={setScale} />
      </label>
      <div class="flex flex-col gap-3">
        <label class="grid gap-1 text-sm text-slate-300">Offset X
          <input class="rounded border border-white/20 bg-slate-950 px-3 py-2" type="number" bind:value={offsetX} onchange={setOffset} />
        </label>
        <label class="grid gap-1 text-sm text-slate-300">Offset Y
          <input class="rounded border border-white/20 bg-slate-950 px-3 py-2" type="number" bind:value={offsetY} onchange={setOffset} />
        </label>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" onclick={() => stage?.fitToScreen("fill")}>Fill</Button>
        <Button variant="outline" onclick={() => stage?.fitToScreen("fit")}>Fit</Button>
        <Button variant="outline" onclick={() => { offsetX = window.innerWidth / 2; offsetY = window.innerHeight; setOffset(); }}>Center</Button>
      </div>
      <label class="flex items-center gap-3 text-sm text-slate-300">
        <input type="checkbox" bind:checked={showSubtitles} /> Show subtitles
      </label>
      {#if showSubtitles}
        <Select
          label="Subtitle language"
          bind:value={subtitleLocale}
          options={[
            { value: "JP", label: "Japanese" },
            { value: "EN", label: "English" },
            { value: "KR", label: "Korean" },
            { value: "TW", label: "Traditional Chinese" },
            { value: "TH", label: "Thai" }
          ]}
        />
      {/if}

      <div class="rounded-md border border-white/10 bg-black/25 p-3 grid gap-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold text-slate-300">Share layout link</span>
          {#if copied}
            <span class="text-[11px] text-emerald-400">Copied to clipboard!</span>
          {/if}
        </div>
        <div class="flex gap-2">
          <input
            type="text"
            readonly
            value={shareableUrl}
            class="grow rounded border border-white/20 bg-slate-950 px-2 py-1 text-xs text-slate-300 select-all overflow-ellipsis"
          />
          <Button variant="outline" onclick={copyShareableLink}>
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </div>

      <Button variant="outline" onclick={() => (settingsOpen = false)}>Close settings</Button>
    </div>
  </aside>

  {#if subtitles.length}
    <div class="fixed bottom-12 left-1/2 z-10 flex w-full max-w-3xl -translate-x-1/2 flex-col items-center gap-2 px-4">
      {#each subtitles as line}<p class="rounded bg-neutral-900/80 p-2 text-center text-lg text-white">{line}</p>{/each}
    </div>
  {/if}
  {#if loading || error}
    <div class="fixed inset-0 z-30 grid place-items-center bg-neutral-950/75 p-6 text-center">
      {#if loading}<p class="text-xl">Loading Live2D data…</p>
      {:else}<p class="max-w-2xl text-red-200">{error}</p>{/if}
    </div>
  {/if}
</main>
