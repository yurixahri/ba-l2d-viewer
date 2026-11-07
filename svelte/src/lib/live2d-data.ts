export type Region = "jp" | "en";
export type VoiceLocale = "JP" | "KR" | "CN";
export type SubtitleLocale = "JP" | "EN" | "KR" | "TW" | "TH";

export interface Dialog {
  CharacterId: number;
  GroupId: number;
  DialogCategory: string;
  DialogType: string;
  AnimationName: string;
  LocalizeEN?: string;
  LocalizeJP?: string;
  LocalizeKR?: string;
  LocalizeTW?: string;
  LocalizeTH?: string;
}

export interface VoiceSource {
  directory: string;
  packs: string[];
}

export interface MemoryLobbyRecord {
  CharacterId: number;
  BGMId: number;
}

interface CharacterRecord {
  Id: number;
  DevName: string;
  ScenarioCharacter: string;
  IsPlayable?: boolean;
  IsPlayableCharacter?: boolean;
}

export async function fetchModelIndex(region: Region): Promise<Record<string, string[]>> {
  const indexUrl =
    region === "en"
      ? "/data/en/GameData/Android/info.json"
      : "/data/jp/Android/info.json";
  const response = await fetch(indexUrl);
  if (!response.ok) throw new Error(`Failed to load model index (${response.status}): ${indexUrl}`);
  const index = (await response.json()) as Record<string, string[]>;
  const origin = window.location.origin;
  return Object.fromEntries(
    Object.entries(index).map(([id, files]) => [
      id,
      files.map((file) => `${origin}/${file.replace(/^\/+/, "")}`),
    ]),
  );
}

export async function fetchViewerTables(region: Region): Promise<{
  dialogs: Dialog[];
  characters: CharacterRecord[];
  memoryLobbies: MemoryLobbyRecord[];
}> {
  const base = region === "en" ? "/data/en/Preload" : "/data/jp";
  const [dialogResponse, characterResponse, lobbyResponse] = await Promise.all([
    fetch(`${base}/TableBundles/Excel/CharacterDialogExcelTable.json`),
    fetch(`${base}/TableBundles/Excel/CharacterExcelTable.json`),
    fetch(`${base}/TableBundles/Excel/MemoryLobbyExcelTable.json`),
  ]);
  if (!dialogResponse.ok || !characterResponse.ok || !lobbyResponse.ok) {
    throw new Error(
      `Failed to load viewer tables (dialog=${dialogResponse.status}, character=${characterResponse.status}, memory-lobby=${lobbyResponse.status})`,
    );
  }
  const [dialogs, characters, memoryLobbies] = await Promise.all([
    dialogResponse.json() as Promise<Dialog[]>,
    characterResponse.json() as Promise<CharacterRecord[]>,
    lobbyResponse.json() as Promise<MemoryLobbyRecord[]>,
  ]);
  return { dialogs, characters, memoryLobbies };
}

export function resolveCharacterId(
  modelId: string,
  characters: CharacterRecord[],
): number {
  const devName = modelId.replace(/_home.*$/i, "").toLowerCase();
  const matches = (name: string) =>
    characters.find(
    (character) =>
      (character.IsPlayable || character.IsPlayableCharacter) &&
        (character.DevName.toLowerCase() === name ||
          character.ScenarioCharacter.toLowerCase() === name),
    );
  const match = matches(devName);
  if (match) return match.Id;
  for (let suffix = 10; suffix >= 1; suffix -= 1) {
    const candidate = matches(`${devName}_${suffix.toString().padStart(2, "0")}`);
    if (candidate) return candidate.Id;
  }
  return -1;
}

export function subtitlesFor(
  modelId: string,
  animation: string,
  dialogs: Dialog[],
  characters: CharacterRecord[],
  locale: SubtitleLocale,
): string[] {
  const characterId = resolveCharacterId(modelId, characters);
  if (characterId < 0) return [];
  const rows = dialogs.filter(
    (row) =>
      row.CharacterId === characterId &&
      row.DialogCategory === "UILobbySpecial",
  );
  let started = false;
  const matching = [];
  for (const row of rows) {
    if (row.AnimationName === animation) started = true;
    else if (row.AnimationName && started) break;
    if (started && row.DialogType === "Talk") {
      const localized = dialogText(row, locale);
      if (localized) matching.push(localized);
    }
  }
  if (matching.length) return matching;
  if (!animation.startsWith("Talk_")) return [];
  const groupId = Number(animation.replace(/^Talk_/, "").split("_")[0]);
  return rows
    .filter((row) => row.DialogType === "Talk" && row.GroupId === groupId)
    .map((row) =>
        dialogText(row, locale) || row.LocalizeJP || "",
    )
    .filter(Boolean);
}

export function dialogText(row: Dialog, locale: SubtitleLocale): string {
  const localized = {
    JP: row.LocalizeJP,
    EN: row.LocalizeEN,
    KR: row.LocalizeKR,
    TW: row.LocalizeTW,
    TH: row.LocalizeTH,
  }[locale];
  return localized || row.LocalizeJP || row.LocalizeKR || row.LocalizeTW || row.LocalizeTH || "";
}
