<script lang="ts">
  import { onMount } from "svelte";
  import { Spine, SpineTexture } from "@esotericsoftware/spine-pixi";
  import { Vector2 } from "@esotericsoftware/spine-core";
  import type { Bone, Event as SpineEvent, TrackEntry } from "@esotericsoftware/spine-core";
  import * as PIXI from "pixi.js";
  import { Howl } from "howler";
  import type { VoiceLocale, VoiceSource } from "$lib/live2d-data";

  type InteractionKind = "pat" | "cheek" | "pinch" | "touch" | "look";
  type InteractionSpec = {
    kind: InteractionKind;
    frames: string[];
    endFrames: string[];
    anchor: Bone;
    offsetLimit: number;
    origin?: { x: number; y: number } | number[];
    min?: { x: number; y: number } | number[];
    max?: { x: number; y: number } | number[];
    dragSpeed?: number;
    releaseSpeed?: number;
  };
  type SerializedInteraction = Omit<InteractionSpec, "anchor"> & {
    bone: string;
    inClip?: string | null;
    endClip?: string | null;
    gameObject?: string;
  };
  type InteractionMap = {
    characters: Record<string, { interactions: SerializedInteraction[]; effects?: string[] }>;
    effect_catalog?: { name: string; kind: "flash" | "particle" | "timeline"; trigger: string }[];
  };

  SpineTexture.toPixiBlending = (value: number) => {
    switch (value) {
      case 1: // Additive
        return PIXI.BLEND_MODES.SCREEN;
      case 2: // Multiply
        return PIXI.BLEND_MODES.MULTIPLY;
      case 3: // Screen
        return PIXI.BLEND_MODES.SCREEN;
      default:
        return PIXI.BLEND_MODES.NORMAL;
    }
  };

  function applyLightOverlayEffects(spine: Spine) {
    for (const slot of spine.skeleton.slots) {
      if (/top_?light|hardlight|screen_light|facelight|intro_.*light/i.test(slot.data.name)) {
        if (!playEffects) {
          slot.color.a = 0;
        } else if (slot.color.a > 0.55) {
          slot.color.a = 0.45;
        }
      }
    }
  }

  type PendingPointer = {
    pointerId: number;
    startGlobal: PIXI.Point;
    latestGlobal: PIXI.Point;
    startCss: PIXI.Point;
    latestCss: PIXI.Point;
    startBoneGlobal?: PIXI.Point;
    startBoneLocal?: PIXI.Point;
    interaction?: InteractionSpec;
    held: boolean;
    timer: ReturnType<typeof setTimeout>;
  };

  let {
    modelId = "",
    modelUrls = [],
    voiceLocale = "JP",
    playVoice = false,
    voiceSources = {},
    voiceVolume = 1,
    playSfx = true,
    sfxVolume = 1,
    playEffects = true,
    tapToTalk = true,
    loopAnimation = false,
    onready,
    onanimation,
    onscale,
    onerror,
  }: {
    modelId?: string;
    modelUrls?: string[];
    voiceLocale?: VoiceLocale;
    playVoice?: boolean;
    voiceSources?: Record<string, VoiceSource>;
    voiceVolume?: number;
    playSfx?: boolean;
    sfxVolume?: number;
    playEffects?: boolean;
    tapToTalk?: boolean;
    loopAnimation?: boolean;
    onready?: (event: { animations: string[]; scale: number }) => void;
    onanimation?: (event: { name: string }) => void;
    onscale?: (event: { value: number }) => void;
    onerror?: (event: { message: string }) => void;
  } = $props();

  let canvas: HTMLCanvasElement;
  let app: PIXI.Application | undefined;
  let character: Spine | undefined;
  let howl: Howl | undefined;
  let generation = 0;
  let scale = 1;
  let interactionOffsetGain = 1;
  let currentModelId = "";
  let isTalking = false;
  let canStartTalk = false;
  let activeTalkEntry: TrackEntry | undefined;
  let activeInteraction: "talk" | "action" | "hold" | "release" | undefined;
  let talkAnimations: string[] = [];
  let talkIndex = 0;
  let lastTalkAnimation = "";
  let interactions: InteractionSpec[] = [];
  let pendingPointer: PendingPointer | undefined;
  let activePointerId: number | null = null;
  let activeInteractionSpec: InteractionSpec | undefined;
  let activeBone: Bone | undefined;
  let activeFrameIndex = 0;
  let activeOffset = { x: 0, y: 0 };
  let appliedInteractionOffset = { x: 0, y: 0 };
  let targetOffset = { x: 0, y: 0 };
  let lastOffsetFrameAt = 0;
  let lastDragLogAt = 0;
  let lastVoiceClip = "";
  let lastVoiceEventAt = 0;
  let releaseVisualCompleted = false;
  let releaseActionCompleted = false;
  const animationMix = 0.2;
  const startIdleToIdleMix = 0.2;
  const endReleaseToIdleMix = 0.2;
  let interactionMapPromise: Promise<InteractionMap> | undefined;
  let lobbyEffectOverlay: PIXI.Sprite | undefined;
  let lobbyDustLayer: PIXI.Container | undefined;
  class LobbyDustSprite extends PIXI.Sprite {
    lobbyClipIndex = 0;
    originX = 0;
    originY = 0;
    baseScale = 1.0;
    baseAlpha = 1.0;
    wasActive = false;
  }
  let lobbyDustSprites: LobbyDustSprite[] = [];
  let lobbyEffects: string[] = [];
  let lobbyEffectCatalog: InteractionMap["effect_catalog"] = [];
  let lobbyEffectElapsed = 0;
  let lobbyEffectDuration = 0.4;
  let lobbyDustManifest: UnityTimelineManifest | undefined;
  let lobbyFlashActive = false;
  let lobbyTimelineFlash = false;
  let lobbyTimelineActive = false;
  let lobbyAnimationKeyframes: UnityKeyframe[] = [];
  let lobbyActiveKeyframes: UnityKeyframe[] = [];
  let lobbyEffectTint = 0xffffff;
  let lobbyFlashColor = $state("#ffffff");
  let lobbySfxCues: LobbyEffectSfxCue[] = [];
  let lobbySfxPlayed = new Set<number>();
  let lobbySfxSounds = new Map<string, Howl>();
  let lobbyCssFlashVisible = $state(false);
  let lobbyCssFlashOpacity = $state(0);
  let lastLobbyEffectLogAt = 0;

  interface UnityKeyframe {
    time: number;
    value: number;
    curveIndex?: number;
    inSlope?: number;
    outSlope?: number;
  }

  interface UnityClip {
    m_DisplayName?: string;
    m_Start?: number;
    m_Duration?: number;
    m_TimeScale?: number;
    AudioData?: {
      Volume?: number;
      Pitch?: number;
      AudioClip?: {
        m_Name?: string;
        m_PathID?: number;
        source?: string;
      };
    };
    sourceGameObject?: string;
    updateParticle?: number;
    particleRandomSeed?: number;
  }

  interface UnityTrack {
    m_Name: string;
    m_Clips: UnityClip[];
    m_InfiniteClip?: {
      m_Name?: string;
      m_SampleRate?: number;
      m_ClipBindingConstant?: Array<{
        path?: number;
        attribute?: number;
        typeID?: number;
      }>;
      m_Keyframes?: UnityKeyframe[];
    };
  }

  interface UnityTimelineManifest {
    m_Name: string;
    character: string;
    m_Duration: number;
    m_Tracks: UnityTrack[];
  }

  const effectManifestCache = new Map<string, UnityTimelineManifest | null>();
  type LobbyEffectSfxCue = {
    start: number;
    source: string;
    volume?: number;
    pitch?: number;
  };

  onMount(() => {
    if (!canvas) return;
    app = new PIXI.Application({
      view: canvas,
      width: window.innerWidth,
      height: window.innerHeight,
      backgroundColor: 0x0a0c10,
      backgroundAlpha: 1,
      antialias: true,
    });
    lobbyEffectOverlay = new PIXI.Sprite(PIXI.Texture.WHITE);
    lobbyEffectOverlay.anchor.set(0);
    lobbyEffectOverlay.visible = false;
    lobbyEffectOverlay.eventMode = "none";
    lobbyEffectOverlay.interactive = false;
    app.stage.addChild(lobbyEffectOverlay);
    lobbyDustLayer = new PIXI.Container();
    app.stage.addChild(lobbyDustLayer);
    const resize = () => {
      app?.renderer.resize(window.innerWidth, window.innerHeight);
      app?.stage.children.forEach((child) => {
        if (child === lobbyEffectOverlay || child === lobbyDustLayer || child instanceof PIXI.Graphics) return;
        child.x = window.innerWidth / 2;
        child.y = window.innerHeight;
      });
    };
    app.ticker.add(updateLobbyEffect);
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      howl?.stop();
      app?.destroy(true, { children: true, texture: false, baseTexture: false });
      lobbyEffectOverlay = undefined;
      app = undefined;
    };
  });

  $effect(() => {
    if (!playEffects) {
      drawLobbyEffect(0);
      if (lobbyEffectOverlay) lobbyEffectOverlay.visible = false;
      lobbyCssFlashVisible = false;
      lobbyCssFlashOpacity = 0;
    }
  });

  $effect(() => {
    if (app && modelUrls.length && currentModelId !== `${modelId}:${modelUrls.join("|")}`) {
    currentModelId = `${modelId}:${modelUrls.join("|")}`;
    void loadModel(modelUrls);
    }
  });

  $effect(() => {
    if (character) {
    const active = character.state.tracks[1];
    if (active?.animation) {
      const animationName = active.animation.name;
      active.loop =
        animationName.startsWith("Idle") ||
        (loopAnimation &&
          activeInteraction !== "hold" &&
          activeInteraction !== "release" &&
          !animationName.includes("Start_Idle"));
    }
    const action = character.state.tracks[3];
    if (action) {
      action.loop =
        loopAnimation &&
        activeInteraction !== "hold" &&
        activeInteraction !== "release";
    }
    }
  });

  function animationGroups(names: string[], family: string) {
    const escaped = family.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = new RegExp(`^${escaped}_(\\d+)_M$`, "i");
    return names
      .map((name) => ({ name, index: Number(pattern.exec(name)?.[1]) }))
      .filter((item) => Number.isFinite(item.index))
      .sort((left, right) => left.index - right.index)
      .map((item) => item.name);
  }

  function interactionFamilies(names: string[]) {
    const families = new Set<string>();
    for (const name of names) {
      const match = /^(.*?)_(\d+)_M$/i.exec(name);
      if (match && !/(?:End|Finish|Release)$/i.test(match[1])) {
        families.add(match[1]);
      }
    }
    return [...families].flatMap((family) => {
      let kind: InteractionKind | undefined;
      if (/pat/i.test(family)) kind = "pat";
      else if (/cheek/i.test(family)) kind = "cheek";
      else if (/pinch|touch|finger|hand|follow|point/i.test(family)) kind = "touch";
      else if (/look/i.test(family)) kind = "look";
      if (!kind) return [];

      const frames = animationGroups(names, family);
      if (!frames.length) return [];
      const endFamilies = [`${family}End`, `${family}_End`];
      const endFrames = endFamilies.flatMap((endFamily) =>
        animationGroups(names, endFamily),
      );
      return [{ family, kind, frames, endFrames }];
    });
  }

  function buildInteractions(spine: Spine, names: string[]) {
    const anchors = spine.skeleton.bones.filter((bone) =>
      /^Touch_.+/i.test(bone.data.name) && !/_key$/i.test(bone.data.name),
    );
    const families = interactionFamilies(names);
    const result: InteractionSpec[] = [];
    for (const anchor of anchors) {
      const suffix = anchor.data.name.replace(/^Touch_/i, "").replace(/_key$/i, "");
      const parentNames: string[] = [];
      for (let parent = anchor.parent; parent; parent = parent.parent) {
        parentNames.push(parent.data.name);
      }
      const normalizedSuffix = suffix.replace(/[^a-z0-9]/gi, "").toLowerCase();
      const normalizedParents = parentNames.join("_").replace(/[^a-z0-9]/gi, "").toLowerCase();
      const supportedKinds = new Set<InteractionKind>();
      if (/eye/.test(normalizedSuffix)) {
        supportedKinds.add("pat");
        supportedKinds.add("look");
      } else if (/cheek|face/.test(normalizedSuffix)) {
        supportedKinds.add("cheek");
      } else if (/finger|hand|point|touch/.test(normalizedSuffix)) {
        supportedKinds.add("touch");
        if (/point/.test(normalizedSuffix)) supportedKinds.add("cheek");
      } else if (/head/.test(normalizedSuffix)) {
        supportedKinds.add("pat");
      } else if (/eye/.test(normalizedParents)) {
        supportedKinds.add("pat");
        supportedKinds.add("look");
      } else if (/cheek|face/.test(normalizedParents)) {
        supportedKinds.add("cheek");
      } else if (/finger|hand/.test(normalizedParents)) {
        supportedKinds.add("touch");
      }

      for (const family of families) {
        if (!supportedKinds.has(family.kind)) continue;
        result.push({
          kind: family.kind,
          frames: family.frames,
          endFrames: family.endFrames,
          anchor,
          offsetLimit: 60,
        });
      }
    }

    const lookFamily = families.find((family) => family.kind === "look");
    const lookAnchor =
      anchors.find((anchor) => /eye/i.test(anchor.data.name)) ??
      anchors[0];
    if (lookFamily && lookAnchor) {
      if (!result.some((interaction) => interaction.kind === "look")) {
        result.push({
          kind: "look",
          frames: lookFamily.frames,
          endFrames: lookFamily.endFrames,
          anchor: lookAnchor,
          offsetLimit: 60,
        });
      }
    }
    return result;
  }

  function modelBaseUrl(): string {
    const firstUrl = modelUrls[0];
    if (firstUrl) {
      const lastSlash = firstUrl.lastIndexOf("/");
      if (lastSlash > 0) {
        return firstUrl.slice(0, lastSlash);
      }
    }
    return `/data/en/GameData/Android/${modelId}`;
  }

  async function loadInteractionMap() {
    if (!interactionMapPromise) {
      interactionMapPromise = fetch("/data/live2d-interactions.json").then(async (response) => {
        if (!response.ok) {
          throw new Error(`Failed to load interaction map (${response.status})`);
        }
        return response.json() as Promise<InteractionMap>;
      });
    }
    return interactionMapPromise;
  }

  async function loadEffectManifest(): Promise<UnityTimelineManifest | undefined> {
    const base = modelBaseUrl();
    if (effectManifestCache.has(base)) {
      const cached = effectManifestCache.get(base);
      return cached ?? undefined;
    }
    try {
      const response = await fetch(`${base}/effects.json`);
      if (response.ok) {
        const data = (await response.json()) as UnityTimelineManifest;
        effectManifestCache.set(base, data);
        return data;
      }
    } catch {
      // ignore
    }
    effectManifestCache.set(base, null);
    return undefined;
  }

  function evaluateKeyframeCurve(
    keyframes: UnityKeyframe[],
    elapsed: number,
  ): number {
    if (!keyframes.length) return 0;
    if (elapsed < keyframes[0].time) {
      return keyframes[0].time <= 0.05 ? Math.max(0, Math.min(1, keyframes[0].value)) : 0;
    }
    const lastKeyframe = keyframes[keyframes.length - 1];
    if (elapsed > lastKeyframe.time) return 0;
    if (elapsed >= lastKeyframe.time) return Math.max(0, Math.min(1, lastKeyframe.value));

    for (let i = 0; i < keyframes.length - 1; i++) {
      const cur = keyframes[i];
      const next = keyframes[i + 1];
      if (elapsed >= cur.time && elapsed <= next.time) {
        const range = next.time - cur.time;
        if (range <= 0.0001) return Math.max(0, Math.min(1, next.value));
        const t = (elapsed - cur.time) / range;
        return Math.max(0, Math.min(1, cur.value + t * (next.value - cur.value)));
      }
    }
    return 0;
  }

  function updateLobbyEffect() {
    if (!app || !lobbyTimelineActive) return;
    const overlay = lobbyEffectOverlay;
    if (lobbyTimelineFlash && lobbyEffectElapsed === 0) {
      console.debug("[lobby-effect] first ticker frame", {
        deltaMS: app.ticker.deltaMS,
        cssVisible: lobbyCssFlashVisible,
        overlayVisible: lobbyEffectOverlay?.visible,
      });
    }
    if (overlay && app.stage.children.at(-1) !== overlay) {
      app.stage.removeChild(overlay);
      app.stage.addChild(overlay);
    }
    lobbyEffectElapsed += app.ticker.deltaMS / 1000;
    if (playSfx) {
      for (const [index, cue] of lobbySfxCues.entries()) {
        if (!lobbySfxPlayed.has(index) && lobbyEffectElapsed >= cue.start) {
          lobbySfxPlayed.add(index);
          let sound = lobbySfxSounds.get(cue.source);
          const cueVol = Math.max(0, Math.min(1, (cue.volume ?? 1) * sfxVolume));
          if (!sound) {
            const base = modelBaseUrl();
            sound = new Howl({
              src: [`${base}/audio/${cue.source}`],
              volume: cueVol,
              rate: cue.pitch ?? 1,
              preload: true,
            });
            lobbySfxSounds.set(cue.source, sound);
          } else {
            sound.volume(cueVol);
          }
          sound.play();
        }
      }
    }
    const progress = Math.min(lobbyEffectElapsed / lobbyEffectDuration, 1);
    let flashAlpha = 0;
    if (playEffects) {
      if (lobbyTimelineFlash && lobbyAnimationKeyframes.length > 0) {
        flashAlpha = evaluateKeyframeCurve(lobbyAnimationKeyframes, lobbyEffectElapsed);
      } else if (lobbyFlashActive) {
        const flashDuration = Math.min(0.08, lobbyEffectDuration * 0.3);
        flashAlpha = lobbyEffectElapsed <= flashDuration
          ? 0.85
          : 0.85 * (1 - (lobbyEffectElapsed - flashDuration) / (lobbyEffectDuration - flashDuration));
      }
    }
    if (lobbyTimelineFlash && lobbyEffectElapsed - lastLobbyEffectLogAt >= 0.05) {
      lastLobbyEffectLogAt = lobbyEffectElapsed;
      console.debug("[lobby-effect] tick", {
        character: characterKey(),
        elapsed: lobbyEffectElapsed.toFixed(3),
        flashAlpha,
        cssVisible: lobbyCssFlashVisible,
        cssOpacity: lobbyCssFlashOpacity,
        pixiVisible: lobbyEffectOverlay?.visible,
      });
    }
    drawLobbyEffect(flashAlpha);
    lobbyCssFlashVisible = flashAlpha > 0;
    lobbyCssFlashOpacity = flashAlpha;
    if (progress >= 1) {
      lobbyTimelineActive = false;
      if (overlay) overlay.visible = false;
      drawLobbyEffect(0);
      lobbyCssFlashVisible = false;
      lobbyCssFlashOpacity = 0;
      if (lobbyDustLayer) lobbyDustLayer.visible = false;
    }
    updateLobbyDust();
  }

  function updateLobbyDust() {
    return; // particle layer disabled for now
    if (!app || !lobbyDustLayer || !lobbyDustSprites.length) return;
    const controlTracks = lobbyDustManifest?.m_Tracks?.filter((t) => t.m_Name.includes("Control")) ?? [];
    const particleClips = controlTracks.flatMap((t) => t.m_Clips.filter((c) => c.updateParticle === 1));
    const spineScale = scale ?? 1.0;

    for (const sprite of lobbyDustSprites) {
      const clipIndex = sprite.lobbyClipIndex;
      const clip = particleClips[clipIndex];
      if (!clip) {
        sprite.visible = false;
        continue;
      }
      const clipStart = clip.m_Start ?? 0;
      const clipDuration = clip.m_Duration ?? 0;
      const clipActive = lobbyEffectElapsed >= clipStart
        && lobbyEffectElapsed <= clipStart + clipDuration;

      if (!clipActive) {
        sprite.visible = false;
        continue;
      }

      if (!sprite.wasActive) {
        sprite.wasActive = true;
        console.info("[lobby-smoke] activated at", lobbyEffectElapsed.toFixed(2), "clip:", clip.m_DisplayName);
      }

      sprite.visible = true;
      const activeElapsed = lobbyEffectElapsed - clipStart;
      const clipProgress = clipDuration > 0
        ? Math.max(0, Math.min(activeElapsed / clipDuration, 1))
        : 0;

      // Natural steam physics: gentle upward drift and soft horizontal curl
      const driftY = activeElapsed * 10.0 * spineScale;
      const waveX = Math.sin(activeElapsed * 0.9) * 12.0 * spineScale;
      sprite.x = sprite.originX + waveX;
      sprite.y = sprite.originY - driftY;

      // Soft expansion as steam expands into air
      const expansion = 1.0 + clipProgress * 0.35;
      sprite.scale.set(sprite.baseScale * expansion);

      // Smooth fade envelope
      const fadeIn = Math.min(1.0, activeElapsed / 0.8);
      const fadeOut = Math.min(1.0, (clipDuration - activeElapsed) / 1.5);
      sprite.alpha = sprite.baseAlpha * fadeIn * Math.max(0, fadeOut);
    }
  }

  function drawLobbyEffect(alpha: number) {
    if (!app || !lobbyEffectOverlay) return;
    lobbyEffectOverlay.alpha = alpha;
    lobbyEffectOverlay.visible = alpha > 0;
    if (alpha <= 0) return;
    lobbyEffectOverlay.tint = lobbyEffectTint;
    lobbyEffectOverlay.position.set(0, 0);
    lobbyEffectOverlay.scale.set(
      app.renderer.width / lobbyEffectOverlay.texture.width,
      app.renderer.height / lobbyEffectOverlay.texture.height,
    );
  }

  function spawnLobbyDust(manifest?: UnityTimelineManifest) {
    if (!app || !lobbyDustLayer) return;
    lobbyDustManifest = manifest;
    lobbyDustLayer.removeChildren();
    lobbyDustSprites = [];
    lobbyDustLayer.position.set(0, 0);
    lobbyDustLayer.scale.set(1);
    lobbyDustLayer.visible = true;

    // Ensure layer is above character and below overlay
    if (app.stage.children.includes(lobbyDustLayer)) {
      app.stage.removeChild(lobbyDustLayer);
    }
    app.stage.addChild(lobbyDustLayer);
    if (lobbyEffectOverlay && app.stage.children.includes(lobbyEffectOverlay)) {
      app.stage.removeChild(lobbyEffectOverlay);
      app.stage.addChild(lobbyEffectOverlay);
    }

    const controlTracks = manifest?.m_Tracks?.filter((t) => t.m_Name.includes("Control")) ?? [];
    const particleClips = controlTracks.flatMap((t) => t.m_Clips.filter((c) => c.updateParticle === 1));
    if (!particleClips.length) return;

    const base = modelBaseUrl();
    const spineBaseX = character?.x ?? (window.innerWidth / 2);
    const spineBaseY = character?.y ?? window.innerHeight;
    const spineScale = scale ?? 1.0;

    for (const [clipIndex, clip] of particleClips.entries()) {
      const clipName = clip.m_DisplayName ?? "";
      const particles = (clip as { m_Particles?: Array<{
        m_Name?: string;
        texture?: string;
        position?: { x: number; y: number; z?: number };
        scale?: { x: number; y: number; z?: number };
        startSize?: number;
        startColor?: { r: number; g: number; b: number; a: number };
      }> }).m_Particles;

      if (particles && particles.length) {
        for (const p of particles) {
          const texName = p.texture ?? clipName;
          const textureUrl = `${base}/${texName}.png`;
          const tex = PIXI.Texture.from(textureUrl);
          const sprite = new LobbyDustSprite(tex);
          tex.baseTexture.on("error", () => {
            sprite.texture = PIXI.Texture.from(`/data/effects/common/${texName}.png`);
          });
          sprite.anchor.set(0.5);
          sprite.lobbyClipIndex = clipIndex;

          // Position relative to screen bottom-center (where character sits in hot spring)
          const posX = spineBaseX + (p.position?.x ?? 0) * spineScale;
          const posY = spineBaseY + (p.position?.y ?? 0) * spineScale;

          const size = p.startSize ?? 14.0;
          const baseScale = Math.max(0.8, (size / 10.0) * 1.5 * spineScale);

          sprite.originX = posX;
          sprite.originY = posY;
          sprite.baseScale = baseScale;
          sprite.baseAlpha = p.startColor?.a ?? 0.65;
          sprite.position.set(posX, posY);
          sprite.scale.set(baseScale);

          sprite.alpha = 0;
          sprite.visible = false;
          // Soft additive glowing mist matching in-game reference 2.webp
          sprite.blendMode = PIXI.BLEND_MODES.ADD;
          lobbyDustLayer.addChild(sprite);
          lobbyDustSprites.push(sprite);
        }
      }
    }
    console.info("[lobby-dust] spawned", lobbyDustSprites.length, "particle sprites for timeline", manifest?.m_Name);
  }


  async function playLobbyEffect(existingManifest?: UnityTimelineManifest) {
    const key = characterKey();
    const manifest = existingManifest ?? await loadEffectManifest();

    const hasTimeline = manifest !== undefined;
    console.info("[lobby-effect] play requested", {
      character: key,
      hasTimeline,
      timelineName: manifest?.m_Name,
      tracks: manifest?.m_Tracks?.length ?? 0,
    });

    if (hasTimeline && manifest) {
      lobbyTimelineActive = true;
      lobbyEffectElapsed = 0;
      lobbyEffectDuration = manifest.m_Duration ?? 30.0;

      // Find the Animation Track that specifically animates SpriteRenderer color alpha (attribute 304273561)
      let foundKeyframes: UnityKeyframe[] = [];
      let foundActiveKeyframes: UnityKeyframe[] = [];
      let tint = 0xffffff;
      for (const track of manifest.m_Tracks) {
        const inf = track.m_InfiniteClip;
        if (!inf?.m_Keyframes?.length) continue;
        const bindings = inf.m_ClipBindingConstant ?? [];
        let alphaCurveIndex = -1;
        let fadePath: number | undefined;
        for (let i = 0; i < bindings.length; i++) {
          if (bindings[i].attribute === 304273561) {
            alphaCurveIndex = i;
            fadePath = bindings[i].path;
            break;
          }
        }
        if (alphaCurveIndex !== -1) {
          const kfs = inf.m_Keyframes.filter((k) => k.curveIndex === alphaCurveIndex);
          if (kfs.length > 0) {
            let isAlwaysDisabled = false;
            if (fadePath !== undefined) {
              const activeIndex = bindings.findIndex((b) => b.path === fadePath && b.attribute === 2086281974);
              if (activeIndex !== -1) {
                const actKfs = inf.m_Keyframes.filter((k) => k.curveIndex === activeIndex);
                if (actKfs.length > 0 && actKfs.every((k) => k.value === 0.0)) {
                  isAlwaysDisabled = true;
                }
              }
            }
            if (!isAlwaysDisabled) {
              foundKeyframes = kfs;
              if (fadePath !== undefined) {
                const rIdx = bindings.findIndex((b) => b.path === fadePath && b.attribute === 2526845255);
                const gIdx = bindings.findIndex((b) => b.path === fadePath && b.attribute === 4215373228);
                const bIdx = bindings.findIndex((b) => b.path === fadePath && b.attribute === 2334886179);
                const rVal = rIdx !== -1 ? inf.m_Keyframes.find((k) => k.curveIndex === rIdx)?.value ?? 1.0 : 1.0;
                const gVal = gIdx !== -1 ? inf.m_Keyframes.find((k) => k.curveIndex === gIdx)?.value ?? 1.0 : 1.0;
                const bVal = bIdx !== -1 ? inf.m_Keyframes.find((k) => k.curveIndex === bIdx)?.value ?? 1.0 : 1.0;
                const r = Math.round(Math.max(0, Math.min(1, rVal)) * 255);
                const g = Math.round(Math.max(0, Math.min(1, gVal)) * 255);
                const b = Math.round(Math.max(0, Math.min(1, bVal)) * 255);
                tint = (r << 16) | (g << 8) | b;
              }
              break;
            }
          }
        }
      }
      lobbyEffectTint = tint;
      lobbyFlashColor = "#" + tint.toString(16).padStart(6, "0");
      lobbyAnimationKeyframes = foundKeyframes;
      lobbyActiveKeyframes = foundActiveKeyframes;
      lobbyTimelineFlash = lobbyAnimationKeyframes.length > 0;
      const initialAlpha = (playEffects && lobbyTimelineFlash) ? evaluateKeyframeCurve(lobbyAnimationKeyframes, 0) : 0;
      lobbyCssFlashVisible = initialAlpha > 0;
      lobbyCssFlashOpacity = initialAlpha;
      drawLobbyEffect(initialAlpha);
      if (lobbyEffectOverlay) {
        lobbyEffectOverlay.visible = lobbyCssFlashVisible;
        lobbyEffectOverlay.alpha = lobbyCssFlashOpacity;
        app?.stage.removeChild(lobbyEffectOverlay);
        app?.stage.addChild(lobbyEffectOverlay);
      }

      // Collect audio cues from SFX / Audio tracks
      const audioTracks = manifest.m_Tracks.filter((t) =>
        t.m_Name.startsWith("SFX") || t.m_Name.includes("Audio"),
      );
      lobbySfxCues = audioTracks.flatMap((t) =>
        t.m_Clips
          ?.filter((c) => c.AudioData?.AudioClip?.source)
          .map((c) => ({
            start: c.m_Start ?? 0,
            source: c.AudioData!.AudioClip!.source!,
            volume: c.AudioData!.Volume ?? 1,
            pitch: c.AudioData!.Pitch ?? 1,
          })) ?? [],
      );
      lobbySfxPlayed = new Set();
      if (lobbyDustLayer) lobbyDustLayer.visible = false;
      // spawnLobbyDust(manifest); // particle layer disabled for now
      return;
    }

    const flashEffects = lobbyEffectCatalog?.filter((effect) =>
      lobbyEffects.includes(effect.name) && effect.kind === "flash",
    ) ?? [];
    const particleEffects = lobbyEffectCatalog?.filter((effect) =>
      lobbyEffects.includes(effect.name) && (effect.kind === "particle" || effect.kind === "timeline"),
    ) ?? [];
    const hasLegacyFade = lobbyEffectCatalog?.length === 0 && lobbyEffects.some((effect) =>
      /fade|flash|white|FX_into/i.test(effect),
    );
    if (flashEffects.length === 0 && particleEffects.length === 0 && !hasLegacyFade) return;
    lobbyTimelineActive = true;
    lobbyEffectElapsed = 0;
    lobbyEffectDuration = particleEffects.length > 0 ? 4.2 : 0.42;
    lobbyFlashActive = flashEffects.length > 0 || hasLegacyFade;
    lobbyTimelineFlash = false;
    lobbyCssFlashVisible = lobbyFlashActive;
    lobbyCssFlashOpacity = 0.85;
    drawLobbyEffect(lobbyFlashActive ? 0.85 : 0);
    if (lobbyEffectOverlay) {
      app?.stage.removeChild(lobbyEffectOverlay);
      app?.stage.addChild(lobbyEffectOverlay);
      lobbyEffectOverlay.visible = true;
    }
  }

  function characterKey() {
    return modelId ? modelId.toLowerCase().trim() : "";
  }

  async function buildMappedInteractions(spine: Spine, names: string[]) {
    const base = modelBaseUrl();
    let mapped: { interactions: SerializedInteraction[]; effects?: string[] } | undefined;
    try {
      const response = await fetch(`${base}/interactions.json`);
      if (response.ok) {
        mapped = (await response.json()) as { interactions: SerializedInteraction[]; effects?: string[] };
      }
    } catch {
      // fallback
    }
    if (!mapped) {
      const rawKey = characterKey();
      const shortKey = rawKey.replace(/_home.*$/i, "");
      const interactionMap = await loadInteractionMap();
      mapped = interactionMap.characters[shortKey] ?? interactionMap.characters[rawKey];
    }
    const serialized = mapped?.interactions ?? [];
    lobbyEffects = mapped?.effects ?? [];
    lobbyEffectCatalog = [];
    const available = new Set(names);
    return serialized.flatMap((item) => {
      let inClip = item.inClip;
      if (!inClip || !available.has(inClip)) {
        const kind = (item.kind ?? item.gameObject ?? "").toLowerCase();
        const fallback = names.find((n) => {
          if (kind.includes("look") || kind.includes("eye")) return /Look_01_M/i.test(n) || /Look.*_M/i.test(n);
          if (kind.includes("pat") || kind.includes("hair")) return /Pat_01_M/i.test(n) || /Pat.*_M/i.test(n);
          if (kind.includes("pinch") || kind.includes("cheek")) return /Pinch_01_M/i.test(n) || /Pinch.*_M/i.test(n);
          return /Touch_01_M/i.test(n) || /Touch.*_M/i.test(n);
        });
        if (fallback) inClip = fallback;
      }
      if (!inClip || !available.has(inClip)) {
        return [];
      }
      const anchor = (item.bone ? spine.skeleton.findBone(item.bone) : undefined)
        ?? spine.skeleton.bones.find((b) => /^Touch_/i.test(b.data.name))
        ?? spine.skeleton.bones[0];
      if (!anchor) return [];
      const familyMatch = inClip.match(/^(.+?)_(\d+)_M$/i);
      const family = familyMatch?.[1];
      const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const framePattern = family ? new RegExp(`^${escape(family)}_(\\d+)_M$`, "i") : undefined;
      const frames = framePattern
        ? names
            .filter((name) => framePattern.test(name))
            .sort((left, right) => Number(left.match(/_(\d+)_M$/i)?.[1]) - Number(right.match(/_(\d+)_M$/i)?.[1]))
        : [inClip];
      const endFamily = item.endClip?.replace(/(?:_?End)_\d+_M$/i, "");
      const endPattern = endFamily
        ? new RegExp(`^${escape(endFamily)}(?:End|_End)_?(\\d+)_M$`, "i")
        : undefined;
      const endFrames = endPattern
        ? names
            .filter((name) => endPattern.test(name))
            .sort((left, right) => Number(left.match(/_(\d+)_M$/i)?.[1]) - Number(right.match(/_(\d+)_M$/i)?.[1]))
        : item.endClip && available.has(item.endClip) ? [item.endClip] : [];
      const mappedOrigin = Array.isArray(item.origin)
        ? { x: item.origin[0] ?? 0, y: item.origin[1] ?? 0 }
        : item.origin;
      return [{
        kind: item.kind,
        frames: frames.length ? frames : [inClip],
        endFrames,
        anchor,
        offsetLimit: 60,
        origin: mappedOrigin,
        min: item.min,
        max: item.max,
        dragSpeed: item.dragSpeed,
        releaseSpeed: item.releaseSpeed,
      }];
    });
  }

  function idleAnimationName() {
    const names = character?.state.data.skeletonData.animations.map((item) => item.name) ?? [];
    return names.includes("Idle_01") ? "Idle_01" : names.find((name) => /^Idle(_|$)/i.test(name));
  }

  function setIdleBase(force = false) {
    if (!character) return;
    const idle = idleAnimationName();
    if (!idle) return;
    if (force || character.state.tracks[2]?.animation?.name !== idle) {
      const entry = character.state.setAnimation(2, idle, true);
      entry.mixDuration = animationMix;
    }
  }

  function setIdleBaseAfterRelease() {
    setIdleBase();
  }

  function configureAnimationMixes() {
    if (!character) return;
    character.state.data.defaultMix = animationMix;
    const animations = character.state.data.skeletonData.animations;
    for (const from of animations) {
      for (const to of animations) {
        if (from !== to) {
          character.state.data.setMix(from.name, to.name, animationMix);
        }
      }
    }
  }

  function stopVoice() {
    howl?.stop();
    howl = undefined;
    lastVoiceClip = "";
    lastVoiceEventAt = 0;
  }

  function returnToIdle() {
    if (!character) return;
    stopVoice();
    targetOffset = { x: 0, y: 0 };
    isTalking = false;
    canStartTalk = true;
    activeInteraction = undefined;
    activeTalkEntry = undefined;
    activeInteractionSpec = undefined;
    character.state.addEmptyAnimation(1, endReleaseToIdleMix, 0);
    character.state.addEmptyAnimation(3, endReleaseToIdleMix, 0);
    character.state.clearTrack(0);
    onanimation?.({ name: idleAnimationName() ?? "Idle" });
  }

  function returnFromStartIdle() {
    if (!character) return;
    character.state.clearTrack(0);
    setIdleBase(true);
    isTalking = false;
    canStartTalk = true;
    onanimation?.({ name: idleAnimationName() ?? "Idle" });
    releaseVisualCompleted = false;
  }

  function finishRelease() {
    if (releaseVisualCompleted && releaseActionCompleted) {
      returnToIdle();
    } else if (!activeInteractionSpec?.endFrames.length) {
      returnToIdle();
    }
  }

  async function loadModel(urls: string[]) {
    const ownGeneration = ++generation;
    stopVoice();
    if (pendingPointer) clearTimeout(pendingPointer.timer);
    app?.stage.removeChildren().forEach((child) => child.destroy());
    lobbyEffectOverlay = new PIXI.Sprite(PIXI.Texture.WHITE);
    lobbyEffectOverlay.anchor.set(0);
    lobbyEffectOverlay.visible = false;
    app?.stage.addChild(lobbyEffectOverlay);
    lobbyDustLayer = new PIXI.Container();
    lobbyDustSprites = [];
    app?.stage.addChild(lobbyDustLayer);
    character = undefined;
    isTalking = false;
    canStartTalk = false;
    activeInteraction = undefined;
    activeTalkEntry = undefined;
    talkAnimations = [];
    talkIndex = 0;
    lastTalkAnimation = "";
    interactions = [];
    lobbyEffects = [];
    pendingPointer = undefined;
    activePointerId = null;
    activeInteractionSpec = undefined;
    activeBone = undefined;
    activeOffset = { x: 0, y: 0 };
    appliedInteractionOffset = { x: 0, y: 0 };
    targetOffset = { x: 0, y: 0 };
    const animations: string[] = [];
    try {
      for (let index = 0; index < urls.length; index += 1) {
        const src = urls[index];
        const key = `live2d-${ownGeneration}-${index}`;
        const skel = `${key}-skel`;
        const atlas = `${key}-atlas`;
        const atlasSrc = src.replace(/\.skel$/i, ".atlas");
        PIXI.Assets.add({ alias: skel, src });
        PIXI.Assets.add({ alias: atlas, src: atlasSrc });
        try {
          await PIXI.Assets.load([skel, atlas]);
        } catch {
          const folder = src.substring(0, src.lastIndexOf("/") + 1);
          const baseName = src.substring(src.lastIndexOf("/") + 1).replace(/\.skel$/i, "");
          const altAtlasSrc = `${folder}${baseName.charAt(0).toUpperCase() + baseName.slice(1)}.atlas`;
          PIXI.Assets.add({ alias: atlas, src: altAtlasSrc });
          await PIXI.Assets.load([skel, atlas]);
        }
        if (ownGeneration !== generation) return;
        const spine = Spine.from(skel, atlas);
        spine.name = `model-${index}`;
        const voiceName =
          src
            .split("/")
            .pop()
            ?.replace(/\.skel$/i, "")
            .replace(/_home.*$/i, "") ?? modelId;
        if (index === 0) {
              character = spine;
              character.state.data.defaultMix = animationMix;
              configureAnimationMixes();
              const names = character.state.data.skeletonData.animations.map((item) => item.name);
          animations.push(...names);
          talkAnimations = names.filter((name) => name.startsWith("Talk_") && name.endsWith("_M"));
          interactions = await buildMappedInteractions(character, names);
          if (!interactions.length) interactions = buildInteractions(character, names);
          character.beforeUpdateWorldTransforms = () => {
            applyInteractionOffset();
            if (character) applyLightOverlayEffects(character);
          };
          character.afterUpdateWorldTransforms = () => restoreInteractionOffset();
          character.state.addListener({
            event: (_entry, event) => onSpineEvent(voiceName, event),
            complete: (entry) => {
              const animationName = entry.animation?.name;
              if (!animationName) return;
              if (entry.trackIndex === 3 && activeInteraction === "release") {
                releaseActionCompleted = true;
                finishRelease();
                return;
              }
              if (entry.trackIndex === 0) {
                if (animationName.includes("Start_Idle")) {
                  setIdleBase(true);
                  returnFromStartIdle();
                }
                return;
              }
              if (entry.trackIndex !== 1) return;
              if (entry === activeTalkEntry) {
                if (activeInteraction === "hold" && activeInteractionSpec) {
                  if (activeFrameIndex < activeInteractionSpec.frames.length - 1) {
                    activeFrameIndex += 1;
                    playInteractionFrame(
                      activeInteractionSpec.frames[activeFrameIndex],
                      activeInteraction,
                      false,
                    );
                  } else {
                    playInteractionFrame(
                      activeInteractionSpec.frames[activeFrameIndex],
                      activeInteraction,
                      true,
                    );
                  }
                  return;
                }
                if (activeInteraction === "release") {
                  if (
                    activeInteractionSpec &&
                    activeFrameIndex < activeInteractionSpec.endFrames.length - 1
                  ) {
                    activeFrameIndex += 1;
                    playInteractionFrame(
                      activeInteractionSpec.endFrames[activeFrameIndex],
                      "release",
                      false,
                    );
                  } else {
                    releaseVisualCompleted = true;
                    finishRelease();
                  }
                  return;
                }
                if (loopAnimation) return;
                returnToIdle();
              } else if (animationName.includes("Start_Idle")) {
                returnFromStartIdle();
              }
            },
          });
        }
        if (index > 0) {
          spine.beforeUpdateWorldTransforms = () => applyLightOverlayEffects(spine);
        }
        app?.stage.addChildAt(spine, 0);
      }
      if (!character) throw new Error(`No skeleton loaded for ${modelId}`);
      const width = Math.max(character.width, 1);
      const height = Math.max(character.height, 1);
      scale =
        Math.ceil(
          Math.max(window.innerWidth / width, window.innerHeight / height) * 10,
        ) / 10;
      for (const spine of app?.stage.children ?? []) {
        if (spine === lobbyEffectOverlay || spine === lobbyDustLayer || spine instanceof PIXI.Graphics) continue;
        spine.scale.set(scale);
        spine.x = window.innerWidth / 2;
        spine.y = window.innerHeight;
      }
      const effectManifest = await loadEffectManifest();
      if (ownGeneration !== generation) return;

      // Start transition effect first so opening flash/fade masks scene
      await playLobbyEffect(effectManifest);
      if (ownGeneration !== generation) return;

      // Start L2D animation instantly after effect is initialized
      const startAnimation = animations.find((name) =>
        name.toLowerCase() === "start_idle_01",
      );
      const idle = idleAnimationName() ?? animations.find((name) => /^Idle/i.test(name));
      if (startAnimation) {
        const startEntry = character.state.setAnimation(0, startAnimation, false);
        startEntry.mixDuration = startIdleToIdleMix;
        onanimation?.({ name: startAnimation });
      } else if (idle) {
        character.state.setAnimation(2, idle, true);
        canStartTalk = true;
        onanimation?.({ name: idle });
      } else {
        const firstAnimation = animations[0];
        if (firstAnimation) {
          character.state.setAnimation(1, firstAnimation, true);
        }
      }
      onready?.({ animations, scale });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      onerror?.({ message });
    }
  }

  function playAnimationCore(
    name: string,
    mode: "talk" | "action" | "hold",
  ) {
    if (!character) return;
    stopVoice();
    character.state.data.defaultMix = animationMix;
    const animation =
      name.endsWith("_A") && character.state.data.skeletonData.findAnimation(`${name.slice(0, -2)}_M`)
        ? `${name.slice(0, -2)}_M`
        : name;
    if (animation.startsWith("Idle")) {
      activeInteraction = undefined;
      activeTalkEntry = undefined;
      isTalking = false;
      canStartTalk = true;
      activeInteractionSpec = undefined;
      targetOffset = { x: 0, y: 0 };
      character.state.clearTrack(0);
      setIdleBase();
      onanimation?.({ name: animation });
      return;
    }

    const isStart = animation.includes("Start_Idle");
    if (!isStart) {
      targetOffset = { x: 0, y: 0 };
    }
    if (isStart) void playLobbyEffect();
    setIdleBase();
    const action = animation.endsWith("_M") ? `${animation.slice(0, -2)}_A` : "";
    if (action && character.state.data.skeletonData.findAnimation(action)) {
      const actionEntry = character.state.setAnimation(3, action, mode === "hold" || loopAnimation);
      actionEntry.mixDuration = 0;
    } else {
      character.state.setEmptyAnimation(3, animationMix);
    }

    activeInteraction = isStart ? undefined : mode;
    isTalking = !isStart;
    canStartTalk = false;
    activeTalkEntry = character.state.setAnimation(
      isStart ? 0 : 1,
      animation,
      mode === "hold" || (!isStart && loopAnimation),
    );
    activeTalkEntry.mixDuration = startIdleToIdleMix;
    if (activeTalkEntry.mixingFrom) activeTalkEntry.mixingFrom.mixDuration = activeTalkEntry.mixDuration;
    if (animation.startsWith("Talk_") && animation.endsWith("_M")) {
      lastTalkAnimation = animation;
    }
    onanimation?.({ name: animation });
  }

  export function playAnimation(name: string) {
    if (name.startsWith("Talk_") && name.endsWith("_M")) {
      playAnimationCore(name, "talk");
    } else {
      playAnimationCore(name, "action");
    }
  }

  function playInteractionFrame(
    name: string,
    mode: "hold" | "release",
    loop: boolean,
  ) {
    if (!character) return;
    character.state.data.defaultMix = animationMix;
    const action = `${name.slice(0, -2)}_A`;
    if (character.state.data.skeletonData.findAnimation(action)) {
      const actionEntry = character.state.setAnimation(3, action, loop);
      actionEntry.mixDuration = 0;
    } else {
      character.state.setEmptyAnimation(3, animationMix);
    }
    activeInteraction = mode;
    activeTalkEntry = character.state.setAnimation(1, name, loop);
    const isLookRelease = mode === "release" && activeInteractionSpec?.kind === "look";
    activeTalkEntry.mixDuration = isLookRelease ? endReleaseToIdleMix : animationMix;
    if (activeTalkEntry.mixingFrom) {
      activeTalkEntry.mixingFrom.mixDuration = activeTalkEntry.mixDuration;
    }
    onanimation?.({ name });
  }

  function playNextTalk() {
    if (!character || isTalking || !canStartTalk) return;
    if (talkAnimations.length === 0) return;
    if (talkIndex < talkAnimations.length) {
      playAnimationCore(talkAnimations[talkIndex], "talk");
      talkIndex += 1;
      return;
    }
    const choices =
      talkAnimations.length > 1
        ? talkAnimations.filter((name) => name !== lastTalkAnimation)
        : talkAnimations;
    playAnimationCore(choices[Math.floor(Math.random() * choices.length)], "talk");
  }

  function applyInteractionOffset() {
    if (!activeBone) return;
    const now = performance.now();
    const delta = lastOffsetFrameAt ? Math.min((now - lastOffsetFrameAt) / 1000, 0.05) : 1 / 60;
    lastOffsetFrameAt = now;
    const configuredSpeed = activeInteraction === "release"
      ? activeInteractionSpec?.releaseSpeed
      : activeInteractionSpec?.dragSpeed;
    const isLookRelease = activeInteraction === "release" && activeInteractionSpec?.kind === "look";
    const followRate = isLookRelease
      ? 12
      : configuredSpeed ? configuredSpeed * 45 : activeInteraction === "release" ? 3.6 : 7.2;
    const blend = 1 - Math.exp(-delta * followRate);
    activeOffset.x += (targetOffset.x - activeOffset.x) * blend;
    activeOffset.y += (targetOffset.y - activeOffset.y) * blend;
    const renderedOrigin = activeBone.localToWorld(new Vector2(0, 0));
    const renderedUnitX = activeBone.localToWorld(new Vector2(1, 0));
    const renderedUnitY = activeBone.localToWorld(new Vector2(0, 1));
    character!.skeletonToPixiWorldCoordinates(renderedOrigin);
    character!.skeletonToPixiWorldCoordinates(renderedUnitX);
    character!.skeletonToPixiWorldCoordinates(renderedUnitY);
    const pixelsPerBoneX = Math.hypot(
      renderedUnitX.x - renderedOrigin.x,
      renderedUnitX.y - renderedOrigin.y,
    );
    const pixelsPerBoneY = Math.hypot(
      renderedUnitY.x - renderedOrigin.x,
      renderedUnitY.y - renderedOrigin.y,
    );
    if (activeInteractionSpec?.min && activeInteractionSpec.max && activeInteractionSpec.origin) {
      interactionOffsetGain = 60;
    } else {
      interactionOffsetGain = 0.75;
    }
    appliedInteractionOffset = {
      x: activeOffset.x * interactionOffsetGain,
      y: activeOffset.y * interactionOffsetGain,
    };
    activeBone.x += appliedInteractionOffset.x;
    activeBone.y += appliedInteractionOffset.y;
    const nowLog = performance.now();
    if (pendingPointer && nowLog - lastDragLogAt >= 100) {
      lastDragLogAt = nowLog;
      const pointerDelta = {
        x: pendingPointer.latestCss.x - pendingPointer.startCss.x,
        y: pendingPointer.latestCss.y - pendingPointer.startCss.y,
      };
      const origin = activeBone.localToWorld(new Vector2(0, 0));
      const unitX = activeBone.localToWorld(new Vector2(1, 0));
      const unitY = activeBone.localToWorld(new Vector2(0, 1));
      character!.skeletonToPixiWorldCoordinates(origin);
      character!.skeletonToPixiWorldCoordinates(unitX);
      character!.skeletonToPixiWorldCoordinates(unitY);
      // console.debug("[interaction-drag]", {
      //   bone: activeBone.data.name,
      //   pointerDelta,
      //   targetOffset: { ...targetOffset },
      //   appliedOffset: {
      //     x: activeOffset.x * interactionOffsetGain,
      //     y: activeOffset.y * interactionOffsetGain,
      //   },
      //   interactionOffsetGain,
      //   pixelsPerBoneX: {
      //     x: unitX.x - origin.x,
      //     y: unitX.y - origin.y,
      //   },
      //   pixelsPerBoneY: {
      //     x: unitY.x - origin.x,
      //     y: unitY.y - origin.y,
      //   },
      //   expectedRendererDelta: {
      //     x: activeOffset.x * interactionOffsetGain * (unitX.x - origin.x) + activeOffset.y * interactionOffsetGain * (unitY.x - origin.x),
      //     y: activeOffset.x * interactionOffsetGain * (unitX.y - origin.y) + activeOffset.y * interactionOffsetGain * (unitY.y - origin.y),
      //   },
      //   animatedBonePosition: {
      //     x: activeBone.x - activeOffset.x * interactionOffsetGain,
      //     y: activeBone.y - activeOffset.y * interactionOffsetGain,
      //   },
      //   renderedBonePosition: { x: activeBone.x, y: activeBone.y },
      // });
    }
  }

  function restoreInteractionOffset() {
    if (!activeBone) return;
    activeBone.x -= appliedInteractionOffset.x;
    activeBone.y -= appliedInteractionOffset.y;
    appliedInteractionOffset = { x: 0, y: 0 };
    if (
      activeInteraction === undefined &&
      Math.abs(activeOffset.x) < 0.01 &&
      Math.abs(activeOffset.y) < 0.01
    ) {
      activeBone = undefined;
      activeInteractionSpec = undefined;
    }
  }

  function pointerPoint(clientX: number, clientY: number) {
    if (!character || !app) return undefined;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return undefined;
    return new PIXI.Point(
      ((clientX - rect.left) * app.renderer.width) / rect.width,
      ((clientY - rect.top) * app.renderer.height) / rect.height,
    );
  }

  function cssPointerPoint(clientX: number, clientY: number) {
    const rect = canvas.getBoundingClientRect();
    return new PIXI.Point(
      rect.width ? clientX - rect.left : clientX,
      rect.height ? clientY - rect.top : clientY,
    );
  }

  function pointInBoneSpace(point: PIXI.Point, bone: Bone) {
    const local = point.clone();
    character?.pixiWorldCoordinatesToBone(local, bone);
    return local;
  }

  function boneClientPosition(bone: Bone) {
    if (!character || !app) return undefined;
    const point = character.getBonePosition(bone, new PIXI.Point());
    if (!point) return undefined;
    character.skeletonToPixiWorldCoordinates(point);
    const rect = canvas.getBoundingClientRect();
    return {
      x: rect.left + (point.x / app.renderer.width) * rect.width,
      y: rect.top + (point.y / app.renderer.height) * rect.height,
    };
  }

  function interactionVector(value: InteractionSpec["origin"]): { x: number; y: number } | undefined {
    if (!value) return undefined;
    return Array.isArray(value)
      ? { x: value[0] ?? 0, y: value[1] ?? 0 }
      : value;
  }

  function interactionClientPosition(interaction: InteractionSpec) {
    return interaction.anchor ? boneClientPosition(interaction.anchor) : undefined;
  }

  function interactionAt(clientX: number, clientY: number) {
    const nearby = interactions
      .map((interaction) => {
        const center = interactionClientPosition(interaction);
        return center
          ? {
              interaction,
              distance: Math.hypot(clientX - center.x, clientY - center.y),
            }
          : undefined;
      })
      .filter((item): item is { interaction: InteractionSpec; distance: number } =>
        Boolean(item && item.distance <= Math.max(140, 180 * scale)),
      )
      .sort((left, right) => {
        const distance = left.distance - right.distance;
        if (Math.abs(distance) > 1) return distance;
        const priority: Record<InteractionKind, number> = {
          pat: 0,
          cheek: 1,
          pinch: 2,
          touch: 3,
          look: 4,
        };
        return priority[left.interaction.kind] - priority[right.interaction.kind];
      });
    const specific = nearby.filter((item) => item.interaction.kind !== "look");
    return (
      specific[0]?.interaction ??
      nearby.find((item) => item.interaction.kind === "look")?.interaction ??
      interactions.find((item) => item.kind === "look") ??
      interactions[0]
    );
  }

  function beginHeldInteraction(pending: PendingPointer) {
    if (pendingPointer !== pending) return;
    pending.held = true;
    if (!pending.interaction || !character) return;
    activePointerId = pending.pointerId;
    activeInteractionSpec = pending.interaction;
    activeBone = pending.interaction.anchor;
    activeOffset = { x: 0, y: 0 };
    appliedInteractionOffset = { x: 0, y: 0 };
    targetOffset = { x: 0, y: 0 };
    lastOffsetFrameAt = 0;
    activeFrameIndex = 0;
    setIdleBase();
    stopVoice();
    isTalking = true;
    canStartTalk = false;
    playInteractionFrame(pending.interaction.frames[0], "hold", false);
    pending.startBoneGlobal = new PIXI.Point(
      activeBone.worldX,
      activeBone.worldY,
    );
    character.skeletonToPixiWorldCoordinates(pending.startBoneGlobal);
    pending.startBoneLocal = pointInBoneSpace(pending.startBoneGlobal, activeBone);
    updateInteractionTarget(pending.latestGlobal);
  }

  function updateInteractionTarget(globalPoint: PIXI.Point) {
    if (!character || !activeInteractionSpec || !activeBone || !pendingPointer) return;
    const rect = canvas.getBoundingClientRect();
    if (!pendingPointer.startBoneGlobal) return;
    const startBoneCss = {
      x: pendingPointer.startBoneGlobal.x / app!.renderer.width * rect.width + rect.left,
      y: pendingPointer.startBoneGlobal.y / app!.renderer.height * rect.height + rect.top,
    };
    const cssDistanceX = pendingPointer.latestCss.x - (startBoneCss.x - rect.left);
    const cssDistanceY = pendingPointer.latestCss.y - (startBoneCss.y - rect.top);
    const distanceX = cssDistanceX;
    const distanceY = cssDistanceY;
    const screenLimit = activeInteractionSpec.offsetLimit;
    const distance = Math.hypot(distanceX, distanceY);
    const softenedDistance = distance <= screenLimit
      ? distance
      : screenLimit + screenLimit * 0.35 * Math.tanh((distance - screenLimit) / screenLimit);
    const ratio = distance > 0 ? softenedDistance / distance : 0;
    const clampedDistanceX = distanceX * ratio;
    const clampedDistanceY = distanceY * ratio;
    const clampedGlobal = new PIXI.Point(
      pendingPointer.startBoneGlobal.x + clampedDistanceX / rect.width * app!.renderer.width,
      pendingPointer.startBoneGlobal.y + clampedDistanceY / rect.height * app!.renderer.height,
    );
    const spec = activeInteractionSpec;
    const local = pointInBoneSpace(clampedGlobal, activeBone);
    const startLocal = pendingPointer.startBoneLocal ?? pointInBoneSpace(pendingPointer.startGlobal, activeBone);
    if (spec.origin && spec.min && spec.max) {
      const origin = interactionVector(spec.origin)!;
      const min = interactionVector(spec.min)!;
      const max = interactionVector(spec.max)!;
      const minX = min.x - origin.x;
      const maxX = max.x - origin.x;
      const minY = min.y - origin.y;
      const maxY = max.y - origin.y;
      targetOffset = {
        x: Math.max(minX, Math.min(maxX, local.x - startLocal.x)),
        y: Math.max(minY, Math.min(maxY, local.y - startLocal.y)),
      };
    } else {
      targetOffset = {
        x: local.x - startLocal.x,
        y: local.y - startLocal.y,
      };
    }
  }

  function finishHeldInteraction() {
    const interaction = activeInteractionSpec;
    activePointerId = null;
    targetOffset = { x: 0, y: 0 };
    if (!character || activeInteraction !== "hold") return;
    if (!interaction?.endFrames.length) {
      returnToIdle();
      return;
    }
    isTalking = true;
    canStartTalk = false;
    activeFrameIndex = 0;
    releaseVisualCompleted = false;
    releaseActionCompleted =
      !activeInteractionSpec?.endFrames.some((endFrame) => {
        const action = `${endFrame.slice(0, -2)}_A`;
        return character?.state.data.skeletonData.findAnimation(action);
      });
    playInteractionFrame(interaction.endFrames[0], "release", false);
  }

  function onPointerDown(event: PointerEvent) {
    if (
      event.button !== 0 ||
      !character ||
      !app ||
      !tapToTalk ||
      isTalking
    ) return;
    const point = pointerPoint(event.clientX, event.clientY);
    if (!point) return;
    const cssPoint = cssPointerPoint(event.clientX, event.clientY);
    const bounds = character.getBounds();
    const interaction = interactionAt(event.clientX, event.clientY);
    if (!interaction && !bounds.contains(point.x, point.y)) return;
    let pending!: PendingPointer;
    pending = {
      pointerId: event.pointerId,
      startGlobal: point.clone(),
      latestGlobal: point.clone(),
      startCss: cssPoint.clone(),
      latestCss: cssPoint.clone(),
      interaction,
      held: false,
      timer: setTimeout(() => beginHeldInteraction(pending), 170),
    };
    pendingPointer = pending;
    event.preventDefault();
    canvas.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent) {
    const point = pointerPoint(event.clientX, event.clientY);
    if (!point) return;
    if (pendingPointer?.pointerId === event.pointerId) {
      pendingPointer.latestGlobal = point;
      pendingPointer.latestCss = cssPointerPoint(event.clientX, event.clientY);
      if (activePointerId === event.pointerId) {
        updateInteractionTarget(point);
      }
      event.preventDefault();
    }
  }

  function onPointerUp(event: PointerEvent, allowTap = true) {
    if (event.pointerId === pendingPointer?.pointerId) {
      const pending = pendingPointer;
      clearTimeout(pending.timer);
      pendingPointer = undefined;
      if (activePointerId === event.pointerId) {
        finishHeldInteraction();
      } else {
        const distance = Math.hypot(
          event.clientX - (canvas.getBoundingClientRect().left +
            (pending.startGlobal.x / app!.renderer.width) * canvas.getBoundingClientRect().width),
          event.clientY - (canvas.getBoundingClientRect().top +
            (pending.startGlobal.y / app!.renderer.height) * canvas.getBoundingClientRect().height),
        );
        if (allowTap && !pending.held && distance < 8) playNextTalk();
      }
    }
    if (canvas.hasPointerCapture(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId);
    }
  }

  function onSpineEvent(voiceName: string, event: SpineEvent) {
    if (!playVoice || event.data?.name !== "Talk" || !event.stringValue) return;
    const voice = event.stringValue.toLowerCase().replace(/\.ogg$/, "") + ".ogg";
    const now = Date.now();
    if (lastVoiceClip === voice && now - lastVoiceEventAt < 500) return;
    howl?.stop();
    lastVoiceClip = voice;
    lastVoiceEventAt = now;
    const source = voiceSources[voiceLocale];
    if (!source) {
      console.warn(`No local ${voiceLocale} voice pack is configured.`);
      return;
    }
    const pack = source.packs.find(
      (name) =>
        name.replace(/[^a-z0-9]/gi, "").toLowerCase() ===
        `${voiceLocale}${voiceName}`.replace(/[^a-z0-9]/gi, "").toLowerCase(),
    ) ?? source.packs
      .filter((name) =>
        `${voiceLocale}${voiceName}`
          .replace(/[^a-z0-9]/gi, "")
          .toLowerCase()
          .startsWith(name.replace(/[^a-z0-9]/gi, "").toLowerCase()),
      )
      .sort((left, right) => right.length - left.length)[0];
    if (!pack) {
      console.warn(`No ${voiceLocale} voice pack was found for ${voiceName}.`);
      return;
    }
    const root = `/data/jp/MediaResources/GameData/Audio/${source.directory}/${pack}`;
    howl = new Howl({
      src: [`${root}/${voice}`],
      volume: Math.max(0, Math.min(1, voiceVolume)),
      onloaderror: (_id, error) => console.error(`Voice clip unavailable (${voiceLocale}):`, error),
    });
    howl.play();
  }

  export function setScale(value: number) {
    if (!Number.isFinite(value) || value <= 0) return;
    scale = value;
    app?.stage.children.forEach((child) => child.scale.set(scale));
    onscale?.({ value });
  }

  export function setOffset(x: number, y: number) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    app?.stage.children.forEach((child) => {
      child.x = x;
      child.y = y;
    });
  }

  export function fitToScreen(mode: "fit" | "fill") {
    if (!character || !app) return;
    const width = Math.max(character.width / scale, 1);
    const height = Math.max(character.height / scale, 1);
    const ratio =
      mode === "fill"
        ? Math.max(app.renderer.width / width, app.renderer.height / height)
        : Math.min(app.renderer.width / width, app.renderer.height / height);
    setScale(Math.ceil(ratio * 100) / 100);
  }

  export function setMaxFPS(value: number) {
    if (app && Number.isFinite(value) && value > 0) app.ticker.maxFPS = value;
  }
</script>

<canvas
  class="fixed inset-0 h-full w-full"
  style="touch-action: none"
  bind:this={canvas}
  onpointerdown={onPointerDown}
  onpointermove={onPointerMove}
  onpointerup={(event) => onPointerUp(event)}
  onpointercancel={(event) => onPointerUp(event, false)}
></canvas>

{#if playEffects && lobbyCssFlashVisible && lobbyCssFlashOpacity > 0.005}
  <div
    class="pointer-events-none fixed inset-0"
    style:opacity={lobbyCssFlashOpacity}
    style:background-color={lobbyFlashColor}
    style:z-index="15"
  ></div>
{/if}
