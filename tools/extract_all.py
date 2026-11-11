#!/usr/bin/env python3
"""
Complete Unified Extraction Pipeline for Blue Archive Live2D Viewer.

Extracts all character Live2D assets (.skel, .atlas, .png), timeline effects,
interactions, audio cues, Excel tables, and game metadata in one portable run.

CLI Arguments:
  -k, --key       : SQLCipher 32-byte hexadecimal database key (required)
  -i, --input     : Game data input root directory (required)
  -o, --output    : Viewer data destination directory (required)
  -c, --character : Single character filter (e.g. ch0355_home or aru_home) (optional)
  --force         : Re-extract existing textures, skel, and atlas files (optional)
  -h, --help      : Display help message
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import re
import shutil
import struct
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

import UnityPy


# ---------------------------------------------------------------------------
# FlatBuffer Table Decoding (for SQLCipher ExcelDB.db)
# ---------------------------------------------------------------------------

class FlatBufferTable:
    def __init__(self, data: bytes):
        if len(data) < 8:
            raise ValueError("FlatBuffer record is too short")
        self.data = data
        self.position = struct.unpack_from("<I", data, 0)[0]
        vtable_distance = struct.unpack_from("<i", data, self.position)[0]
        self.vtable = self.position - vtable_distance
        self.vtable_size = struct.unpack_from("<H", data, self.vtable)[0]
        self.object_size = struct.unpack_from("<H", data, self.vtable + 2)[0]

    def _field(self, index: int) -> int | None:
        entry = self.vtable + 4 + index * 2
        if entry + 2 > self.vtable + self.vtable_size:
            return None
        offset = struct.unpack_from("<H", self.data, entry)[0]
        return None if offset == 0 else self.position + offset

    def scalar(self, index: int, fmt: str, default: Any) -> Any:
        pos = self._field(index)
        return default if pos is None else struct.unpack_from(fmt, self.data, pos)[0]

    def string(self, index: int) -> str:
        pos = self._field(index)
        if pos is None:
            return ""
        rel = struct.unpack_from("<I", self.data, pos)[0]
        target = pos + rel
        length = struct.unpack_from("<I", self.data, target)[0]
        return self.data[target + 4 : target + 4 + length].decode("utf-8", errors="ignore")

    def uint32_vector(self, index: int) -> list[int]:
        pos = self._field(index)
        if pos is None:
            return []
        rel = struct.unpack_from("<I", self.data, pos)[0]
        target = pos + rel
        length = struct.unpack_from("<I", self.data, target)[0]
        return list(struct.unpack_from(f"<{length}I", self.data, target + 4))

    def string_vector(self, index: int) -> list[str]:
        pos = self._field(index)
        if pos is None:
            return []
        rel = struct.unpack_from("<I", self.data, pos)[0]
        vec_pos = pos + rel
        length = struct.unpack_from("<I", self.data, vec_pos)[0]
        result = []
        for i in range(length):
            elem_pos = vec_pos + 4 + i * 4
            elem_rel = struct.unpack_from("<I", self.data, elem_pos)[0]
            str_pos = elem_pos + elem_rel
            str_len = struct.unpack_from("<I", self.data, str_pos)[0]
            result.append(self.data[str_pos + 4 : str_pos + 4 + str_len].decode("utf-8", errors="ignore"))
        return result


DIALOG_CATEGORIES = """
Cafe Echelon CharacterSSRNew CharacterGet Birthday Dating Title UILobby
UILobbySpecial UIShop UIGacha UIRaidLobby UIWork UITitle UIWeekDungeon
UIAcademyLobby UIRaidLobbySeasonOff UIRaidLobbySeasonOn UIWorkAronaSit
UIWorkAronaSleep UIWorkAronaWatch UIGuideMission UILobby2 UIClanSearchList
UIAttendance UIAttendanceEvent01 UIEventLobby UIEventShop UIEventBoxGachaShop
UIAttendanceEvent02 UIAttendanceEvent03 UIEventCardShop UISchoolDungeon
UIAttendanceEvent UISpecialOperationLobby WeaponGet UIAttendanceEvent04
UIEventFortuneGachaShop UIAttendanceEvent05 UIAttendanceEvent06 UIMission
UIEventMission UIAttendanceEvent08 UIAttendanceEvent07 UIEventMiniGameMission
UIAttendanceEvent09 UIAttendanceEvent10 UIAttendanceEvent11 UIWorkPlanaSit
UIWorkPlanaUmbrella UIWorkPlanaCabinet UIWorkCoexist_AronaSleepSit
UIWorkCoexist_PlanaWatchSky UIWorkCoexist_PlanaSitPeek
UIWorkCoexist_AronaSleepPeek UIEventArchive UIAttendanceEvent12
UIAttendanceEvent13 UIAttendanceEvent14 GlobalAttendance01 GlobalAttendance02
GlobalAttendance03 GlobalAttendance04 GlobalAttendance05 UIAttendanceEvent15
UILobbySpecial2 UIAttendanceEvent16 UIEventTreasure UIMultiFloorRaid
UIEventMiniGameDreamMaker UIAttendanceEvent17 UIAttendanceEvent18
UIBattlePassLobby UIBattlePassMission UIAttendanceEvent19 UIAttendanceEvent20
UIAttendanceEvent21 UIEventClueSearch
""".split()

DIALOG_TYPES = {0: "Talk", 1: "Think", 2: "UITalk"}
PRODUCTION_STEPS = {0: "ToDo", 1: "Doing", 2: "Complete", 3: "Release"}
MEMORY_LOBBY_CATEGORIES = {0: "None", 1: "UILobbySpecial", 2: "UILobbySpecial2"}
RARITIES = {0: "N", 1: "R", 2: "SR", 3: "SSR"}
TACTIC_ROLES = {0: "None", 1: "DamageDealer", 2: "Tanker", 3: "Supporter", 4: "Healer", 5: "Vehicle"}
SCHOOLS = {
    0: "None", 1: "Hyakkiyako", 2: "RedWinter", 3: "Trinity", 4: "Gehenna",
    5: "Abydos", 6: "Millennium", 7: "Arius", 8: "Shanhaijing", 9: "Valkyrie",
    10: "WildHunt", 11: "SRT", 12: "SCHALE", 13: "ETC", 14: "Tokiwadai",
    15: "Sakugawa", 16: "Highlander"
}
CLUBS = {
    0: "None", 1: "Engineer", 2: "CleanNClearing", 3: "KnightsHospitaller",
    4: "IndeGEHENNA", 5: "IndeMILLENNIUM", 6: "IndeHyakkiyako", 7: "IndeShanhaijing",
    8: "IndeTrinity", 9: "FoodService", 10: "Countermeasure", 11: "BookClub",
    12: "MatsuriOffice", 13: "GourmetClub", 14: "HoukagoDessert", 15: "RedwinterSecretary",
    16: "Schale", 17: "TheSeminar", 18: "AriusSqud", 19: "Justice", 20: "Fuuki",
    21: "Kohshinjo68", 22: "Meihuayuan", 23: "SisterHood", 24: "GameDev",
    25: "anzenkyoku", 26: "RemedialClass", 27: "SPTF", 28: "TrinityVigilance",
    29: "Veritas", 30: "TrainingClub", 31: "Onmyobu", 32: "Shugyobu",
    33: "Endanbou", 34: "NinpoKenkyubu", 35: "Class227", 36: "EmptyClub",
    37: "Emergentology", 38: "RabbitPlatoon", 39: "PandemoniumSociety",
    40: "HotSpringsDepartment", 41: "TeaParty", 42: "PublicPeaceBureau",
    43: "Genryumon", 44: "BlackTortoisePromenade", 45: "LaborParty",
    46: "KnowledgeLiberationFront", 47: "Hyakkayouran", 48: "ShinySparkleSociety",
    49: "AbydosStudentCouncil", 50: "CentralControlCenter", 51: "FreightLogisticsDepartment",
    52: "OccultClub"
}


def read_dialog(record: bytes) -> dict[str, Any]:
    t = FlatBufferTable(record)
    cat_val = t.scalar(4, "<i", 0)
    cat_name = DIALOG_CATEGORIES[cat_val] if 0 <= cat_val < len(DIALOG_CATEGORIES) else f"UnknownCategory_{cat_val}"
    return {
        "CharacterId": t.scalar(0, "<q", 0),
        "CostumeUniqueId": t.scalar(1, "<q", 0),
        "DialogCategory": cat_name,
        "GroupId": t.scalar(9, "<q", 0),
        "DialogType": DIALOG_TYPES.get(t.scalar(10, "<i", 0), "Talk"),
        "ActionName": t.string(11),
        "AnimationName": t.string(14),
        "LocalizeKR": t.string(15),
        "LocalizeJP": t.string(16),
        "LocalizeTH": t.string(17),
        "LocalizeTW": t.string(18),
        "LocalizeEN": t.string(19),
        "VoiceId": t.uint32_vector(20),
    }


def read_memory_lobby(record: bytes) -> dict[str, Any]:
    t = FlatBufferTable(record)
    cat_val = t.scalar(5, "<i", 0)
    return {
        "Id": t.scalar(0, "<q", 0),
        "CharacterId": t.scalar(3, "<q", 0),
        "PrefabName": t.string(4),
        "MemoryLobbyCategory": MEMORY_LOBBY_CATEGORIES.get(cat_val, "None"),
        "BGMId": t.scalar(8, "<q", 0),
        "AudioClipJp": t.string(9),
        "AudioClipEn": t.string(13),
    }


def read_character(record: bytes) -> dict[str, Any]:
    t = FlatBufferTable(record)
    return {
        "Id": t.scalar(0, "<q", 0),
        "DevName": t.string(1),
        "CostumeGroupId": t.scalar(2, "<q", 0),
        "IsPlayable": bool(t.scalar(3, "<?", False)),
        "ProductionStep": PRODUCTION_STEPS.get(t.scalar(4, "<i", 0), "Release"),
        "IsPlayableCharacter": bool(t.scalar(9, "<?", False)),
        "Rarity": RARITIES.get(t.scalar(11, "<i", 0), "SSR"),
        "TacticRole": TACTIC_ROLES.get(t.scalar(17, "<i", 0), "None"),
        "School": SCHOOLS.get(t.scalar(23, "<i", 0), "None"),
        "Club": CLUBS.get(t.scalar(24, "<i", 0), "None"),
        "ScenarioCharacter": t.string(36),
    }


def read_bgm(record: bytes) -> dict[str, Any]:
    t = FlatBufferTable(record)
    paths = t.string_vector(2)
    return {
        "Id": t.scalar(0, "<q", 0),
        "ProductionStep": t.scalar(1, "<i", 0),
        "Path": paths[0] if paths else ""
    }


def export_tables(db_path: Path, key: str, out_dirs: list[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    print("Exporting database tables from ExcelDB.db...")
    import sqlcipher3.dbapi2 as sqlite

    conn = sqlite.connect(str(db_path))
    conn.execute(f"PRAGMA key = \"x'{key}'\"")

    cursor = conn.execute('SELECT "Bytes" FROM "CharacterDialogDBSchema" ORDER BY rowid')
    dialogs = [read_dialog(row[0]) for row in cursor]

    cursor = conn.execute('SELECT "Bytes" FROM "MemoryLobbyDBSchema" ORDER BY rowid')
    lobbies = [read_memory_lobby(row[0]) for row in cursor]

    cursor = conn.execute('SELECT "Bytes" FROM "CharacterDBSchema" ORDER BY rowid')
    characters = [read_character(row[0]) for row in cursor]

    bgms: list[dict[str, Any]] = []
    try:
        cursor = conn.execute('SELECT "Bytes" FROM "BGMDBSchema" ORDER BY rowid')
        bgms = [read_bgm(row[0]) for row in cursor]
    except Exception as e:
        print(f"Warning: could not export BGMDBSchema ({e})")

    for out_dir in out_dirs:
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "CharacterDialogExcelTable.json", "w", encoding="utf-8") as f:
            json.dump(dialogs, f, indent=2)
        with open(out_dir / "MemoryLobbyExcelTable.json", "w", encoding="utf-8") as f:
            json.dump(lobbies, f, indent=2)
        with open(out_dir / "CharacterExcelTable.json", "w", encoding="utf-8") as f:
            json.dump(characters, f, indent=2)
        if bgms:
            with open(out_dir / "BGMExcelTable.json", "w", encoding="utf-8") as f:
                json.dump(bgms, f, indent=2)

    print(f"Exported {len(dialogs)} dialogs, {len(lobbies)} memory lobbies, {len(characters)} characters, and {len(bgms)} BGMs to TableBundles.")
    return dialogs, lobbies, characters, bgms


# ---------------------------------------------------------------------------
# StreamedClip Decoding & Timeline Extraction
# ---------------------------------------------------------------------------

def decode_streamed_clip_clean(data_list: list[int]) -> list[dict[str, Any]]:
    if not data_list:
        return []
    keyframes = []
    idx = 0
    while idx < len(data_list):
        t = struct.unpack("<f", struct.pack("<I", data_list[idx]))[0]
        if 0 <= t <= 120:
            break
        num = data_list[idx + 1]
        idx += 2 + num * 5

    while idx < len(data_list) - 1:
        t = struct.unpack("<f", struct.pack("<I", data_list[idx]))[0]
        if t == float("inf") or t < 0 or t > 120:
            break
        num = data_list[idx + 1]
        idx += 2
        for _ in range(num):
            if idx + 4 >= len(data_list):
                break
            c_idx = data_list[idx]
            c3 = struct.unpack("<f", struct.pack("<I", data_list[idx + 4]))[0]
            keyframes.append({
                "time": round(t, 4),
                "curveIndex": c_idx,
                "value": round(c3, 4)
            })
            idx += 5
    return keyframes


def resolve_external_cab_audio(
    cab_name: str,
    path_id: int,
    game_android: Path,
    preload_android: Optional[Path],
    cab_bundle_cache: dict[str, str],
    audio_map: dict[int, tuple[str, bytes]],
    name_map: dict[str, tuple[str, bytes]],
) -> tuple[str, bytes] | None:
    if path_id in audio_map:
        return audio_map[path_id]

    bundle_path = cab_bundle_cache.get(cab_name)
    if not bundle_path:
        cab_bytes = cab_name.encode("utf-8")
        roots = [game_android]
        if preload_android and preload_android.is_dir():
            roots.append(preload_android)
        for r in roots:
            for f in os.listdir(r):
                fl = f.lower()
                if "dependency" in fl or "prolog" in fl or "common" in fl or "audio" in fl:
                    full = os.path.join(r, f)
                    try:
                        with open(full, "rb") as fp:
                            if cab_bytes in fp.read(4096):
                                bundle_path = full
                                cab_bundle_cache[cab_name] = full
                                break
                    except Exception:
                        pass
            if bundle_path:
                break

    if bundle_path:
        try:
            env = UnityPy.load(bundle_path)
            for o in env.objects:
                if o.type.name == "AudioClip":
                    d = o.read()
                    name = getattr(d, "m_Name", "")
                    samples = getattr(d, "samples", {})
                    if samples:
                        sname, sdata = next(iter(samples.items()))
                        audio_map[o.path_id] = (name, sdata)
                        name_map[name.lower()] = (name, sdata)
        except Exception:
            pass

    return audio_map.get(path_id)


def index_audio_clips(
    game_android: Path, preload_android: Optional[Path] = None
) -> tuple[dict[int, tuple[str, bytes]], dict[str, tuple[str, bytes]]]:
    print("Indexing audio clips across game audio bundles and preload bundles...")
    candidate_bundles = []
    roots = [game_android]
    if preload_android and preload_android.is_dir():
        roots.append(preload_android)

    for r in roots:
        for f in os.listdir(r):
            fl = f.lower()
            if any(w in fl for w in ["audio", "wav", "sfx", "sound"]):
                candidate_bundles.append(os.path.join(r, f))
            elif "common" in fl and ("spine" in fl or "character" in fl or "prolog" in fl):
                candidate_bundles.append(os.path.join(r, f))

    candidate_bundles = sorted(set(candidate_bundles))
    audio_map: dict[int, tuple[str, bytes]] = {}
    name_map: dict[str, tuple[str, bytes]] = {}

    for b in candidate_bundles:
        try:
            env = UnityPy.load(b)
            for o in env.objects:
                if o.type.name == "AudioClip":
                    d = o.read()
                    name = getattr(d, "m_Name", "")
                    samples = getattr(d, "samples", {})
                    if samples:
                        sname, sdata = next(iter(samples.items()))
                        audio_map[o.path_id] = (name, sdata)
                        name_map[name.lower()] = (name, sdata)
        except Exception:
            pass
    print(f"Indexed {len(audio_map)} unique AudioClips ({len(name_map)} by name) across {len(candidate_bundles)} bundles.")
    return audio_map, name_map


def find_all_character_bundles(game_android: Path) -> dict[str, list[str]]:
    """Scan all character lobby bundles grouped by character model key."""
    print("Scanning for all character Live2D lobby bundles...")
    bundles = glob.glob(str(game_android / "*spinelobbies*"))
    char_map: dict[str, list[str]] = {}
    for b in bundles:
        base = os.path.basename(b)
        parts = base.split("-")
        if len(parts) >= 4 and parts[2] == "spinelobbies":
            char = parts[3]
            if char not in ["_mxcommon", "_mxdependency"]:
                char_map.setdefault(char, []).append(b)
    print(f"Found lobby bundle sets for {len(char_map)} characters.")
    return char_map


def extract_character_l2d_and_timeline(
    char_bundles: list[str],
    char_key: str,
    target_dirs: list[Path],
    audio_index: tuple[dict[int, tuple[str, bytes]], dict[str, tuple[str, bytes]]],
    interaction_data: dict[str, Any] | None,
    game_android: Optional[Path] = None,
    preload_android: Optional[Path] = None,
    cab_bundle_cache: Optional[dict[str, str]] = None,
    force: bool = False
) -> dict[str, Any] | None:
    """Extract Live2D .skel, .atlas, .png textures, effects.json, and audio cues."""
    for tdir in target_dirs:
        tdir.mkdir(parents=True, exist_ok=True)

    audio_map, name_map = audio_index
    if cab_bundle_cache is None:
        cab_bundle_cache = {}

    char_audio_map: dict[int, tuple[str, bytes]] = {}
    char_name_map: dict[str, tuple[str, bytes]] = {}

    clean_char = char_key.replace("_home", "").replace("_teen", "").replace("_multi", "")
    base_char = clean_char.split("_")[0]
    if game_android and game_android.is_dir():
        dep_patterns = [f"assets-_mx-characters-{clean_char}*.bundle", f"assets-_mx-characters-{base_char}*.bundle"]
        for dp in dep_patterns:
            for b in glob.glob(str(game_android / dp)):
                if b in char_bundles:
                    continue
                try:
                    env = UnityPy.load(b)
                    for o in env.objects:
                        if o.type.name == "AudioClip":
                            d = o.read()
                            cname = getattr(d, "m_Name", "")
                            samples = getattr(d, "samples", {})
                            if samples:
                                sname, sdata = next(iter(samples.items()))
                                char_audio_map[o.path_id] = (cname, sdata)
                                char_name_map[cname.lower()] = (cname, sdata)
                except Exception:
                    pass

    timeline_data: dict[str, Any] | None = None
    timeline_bundle_env: Any = None

    for b_path in char_bundles:
        try:
            env = UnityPy.load(b_path)
        except Exception:
            continue

        for o in env.objects:
            if o.type.name == "AudioClip":
                try:
                    d = o.read()
                    name = getattr(d, "m_Name", "")
                    samples = getattr(d, "samples", {})
                    if samples:
                        sname, sdata = next(iter(samples.items()))
                        char_audio_map[o.path_id] = (name, sdata)
                        char_name_map[name.lower()] = (name, sdata)
                except Exception:
                    pass

            # 1. Live2D TextAsset (.skel and .atlas)
            elif o.type.name == "TextAsset":
                d = o.read()
                name = getattr(d, "m_Name", "")
                if not name:
                    continue
                if not (name.endswith(".atlas") or name.endswith(".skel")):
                    if "atlas" in name.lower():
                        name = f"{name}.atlas"
                    elif "skel" in name.lower():
                        name = f"{name}.skel"
                if name.endswith(".atlas") or name.endswith(".skel"):
                    missing_any = any(force or not (tdir / name).exists() for tdir in target_dirs)
                    if missing_any:
                        raw_bytes = d.m_Script.encode("utf-8", errors="surrogateescape")
                        for tdir in target_dirs:
                            out_file = tdir / name
                            if force or not out_file.exists():
                                with open(out_file, "wb") as f:
                                    f.write(raw_bytes)

            # 2. Live2D Texture2D (.png textures)
            elif o.type.name == "Texture2D":
                d = o.read()
                name = getattr(d, "m_Name", "")
                if name:
                    png_name = f"{name}.png"
                    missing_any = any(force or not (tdir / png_name).exists() for tdir in target_dirs)
                    if missing_any:
                        try:
                            img = d.image
                            for tdir in target_dirs:
                                out_png = tdir / png_name
                                if force or not out_png.exists():
                                    img.save(out_png)
                        except Exception:
                            pass

            # 3. Check for Timeline
            elif o.type.name == "MonoBehaviour" and timeline_data is None:
                d = o.read_typetree()
                if "m_Tracks" in d and "Audio" not in d.get("m_Name", ""):
                    timeline_bundle_env = env

    # Parse timeline from identified environment
    if timeline_bundle_env:
        externals: list[str] = []
        for bf in getattr(timeline_bundle_env, "files", {}).values():
            if hasattr(bf, "files"):
                for sf in bf.files.values():
                    if hasattr(sf, "externals"):
                        externals = [ext.path.split("/")[-1] for ext in sf.externals]
                        if externals:
                            break

        obj_map = {o.path_id: o for o in timeline_bundle_env.objects}
        timeline_obj = None
        for o in timeline_bundle_env.objects:
            if o.type.name == "MonoBehaviour":
                d = o.read_typetree()
                if "m_Tracks" in d and "Audio" not in d.get("m_Name", ""):
                    timeline_obj = d
                    break

        if timeline_obj:
            timeline_name = timeline_obj.get("m_Name", f"{char_key}_Timeline")
            tracks_data = []
            max_duration = 0.0

            for tr_ref in timeline_obj.get("m_Tracks", []):
                tr_id = tr_ref.get("m_PathID")
                tr_obj = obj_map.get(tr_id)
                if not tr_obj:
                    continue
                td = tr_obj.read_typetree()
                track_name = td.get("m_Name", "")

                track_data: dict[str, Any] = {
                    "m_Name": track_name,
                    "m_Clips": []
                }

                inf_ref = td.get("m_InfiniteClip", {}).get("m_PathID")
                if inf_ref and inf_ref in obj_map:
                    inf_obj = obj_map[inf_ref]
                    inf_d = inf_obj.read_typetree()
                    cdata = inf_d.get("m_MuscleClip", {}).get("m_Clip", {}).get("data", {})
                    streamed = cdata.get("m_StreamedClip", {})
                    clean_keyframes = decode_streamed_clip_clean(streamed.get("data", []))

                    track_data["m_InfiniteClip"] = {
                        "m_Name": inf_d.get("m_Name"),
                        "m_SampleRate": inf_d.get("m_SampleRate"),
                        "m_ClipBindingConstant": inf_d.get("m_ClipBindingConstant", {}).get("genericBindings", []),
                        "m_Keyframes": clean_keyframes
                    }

                for c in td.get("m_Clips", []):
                    clip_name = c.get("m_DisplayName", "")
                    start = round(c.get("m_Start", 0.0), 6)
                    dur = round(c.get("m_Duration", 0.0), 6)
                    time_scale = round(c.get("m_TimeScale", 1.0), 6)
                    max_duration = max(max_duration, start + dur)

                    clip_entry: dict[str, Any] = {
                        "m_DisplayName": clip_name,
                        "m_Start": start,
                        "m_Duration": dur,
                        "m_TimeScale": time_scale
                    }

                    aid = c.get("m_Asset", {}).get("m_PathID")
                    if aid and aid in obj_map:
                        ad = obj_map[aid].read_typetree()

                        if "AudioData" in ad:
                            adata = ad.get("AudioData", {})
                            clips_list = adata.get("AudioClips", [])
                            clip_ref = clips_list[0] if clips_list else {}
                            clip_fid = clip_ref.get("m_FileID", 0)
                            clip_pid = clip_ref.get("m_PathID")

                            audio_entry = None
                            if clip_pid:
                                audio_entry = char_audio_map.get(clip_pid) or audio_map.get(clip_pid)
                                if not audio_entry and clip_fid > 0 and clip_fid <= len(externals) and game_android:
                                    cab_name = externals[clip_fid - 1]
                                    audio_entry = resolve_external_cab_audio(
                                        cab_name,
                                        clip_pid,
                                        game_android,
                                        preload_android,
                                        cab_bundle_cache,
                                        audio_map,
                                        name_map,
                                    )
                            if not audio_entry and clip_name:
                                audio_entry = char_name_map.get(clip_name.lower()) or name_map.get(clip_name.lower())
                            if not audio_entry and "m_Name" in ad:
                                ad_name = ad.get("m_Name", "")
                                audio_entry = char_name_map.get(ad_name.lower()) or name_map.get(ad_name.lower())

                            audio_clip_info: dict[str, Any] = {}
                            if audio_entry:
                                sfx_name, sfx_bytes = audio_entry
                                source_file = f"{sfx_name}.wav"
                                for tdir in target_dirs:
                                    audio_out_dir = tdir / "audio"
                                    audio_out_dir.mkdir(parents=True, exist_ok=True)
                                    wav_path = audio_out_dir / source_file
                                    if force or not wav_path.exists():
                                        with open(wav_path, "wb") as wf:
                                            wf.write(sfx_bytes)
                                audio_clip_info = {
                                    "m_Name": sfx_name,
                                    "m_PathID": clip_pid,
                                    "source": source_file
                                }
                            elif clip_pid:
                                audio_clip_info = {
                                    "m_PathID": clip_pid
                                }

                            clip_entry["AudioData"] = {
                                "Volume": adata.get("Volume", 1.0),
                                "Pitch": adata.get("Pitch", 1.0),
                                "AudioClip": audio_clip_info
                            }

                        if "sourceGameObject" in ad:
                            src_go = ad.get("sourceGameObject", {})
                            clip_entry["sourceGameObject"] = src_go.get("exposedName") or src_go.get("defaultValue", {}).get("m_PathID")
                            clip_entry["updateParticle"] = ad.get("updateParticle")
                            clip_entry["particleRandomSeed"] = ad.get("particleRandomSeed")

                    track_data["m_Clips"].append(clip_entry)

                tracks_data.append(track_data)

            timeline_data = {
                "m_Name": timeline_name,
                "character": char_key,
                "m_Duration": round(max_duration or 30.0, 6),
                "m_Tracks": tracks_data
            }

            for tdir in target_dirs:
                with open(tdir / "effects.json", "w", encoding="utf-8") as jf:
                    json.dump(timeline_data, jf, indent=2)

    # Save interactions.json
    if interaction_data:
        for tdir in target_dirs:
            with open(tdir / "interactions.json", "w", encoding="utf-8") as inf:
                json.dump(interaction_data, inf, indent=2)

    # Ensure every .skel has a corresponding .atlas with exact matching name/casing
    for tdir in target_dirs:
        skels = list(tdir.glob("*.skel"))
        atlases = list(tdir.glob("*.atlas"))
        for s in skels:
            matched_atlas = tdir / f"{s.stem}.atlas"
            if not matched_atlas.exists():
                cand = [a for a in atlases if a.stem.lower() == s.stem.lower()] or atlases
                if cand:
                    shutil.copyfile(cand[0], matched_atlas)

    return timeline_data


def generate_info_json(directory: Path, prefix: str) -> dict[str, list[str]]:
    info = {}
    if not directory.exists():
        return info
    for d in sorted(os.listdir(directory)):
        full_d = directory / d
        if not full_d.is_dir():
            continue
        skels = [f for f in os.listdir(full_d) if f.endswith(".skel")]
        if not skels:
            continue
        char_base = d.lower().replace("_home", "").replace("_teen", "").replace("_multi", "")

        def score(s: str) -> int:
            s_lower = s.lower()
            is_bg = "bg" in s_lower or "scene" in s_lower or "background" in s_lower
            is_main = char_base in s_lower and "home" in s_lower and not is_bg
            is_char = char_base in s_lower and not is_bg
            if is_main:
                return 0
            if is_char:
                return 1
            if not is_bg:
                return 2
            return 3

        valid_skels = []
        for s in skels:
            s_lower = s.lower()
            # Skip intro-only cutscene overlay skeletons (_00.skel, _01.skel)
            if re.search(r"_\d{2}\.skel$", s_lower):
                continue
            # Skip skeletons belonging to completely different characters
            if not any(k in s_lower for k in [char_base, "bg", "scene", "background"]):
                continue
            valid_skels.append(s)

        if not valid_skels:
            valid_skels = skels

        sorted_skels = sorted(valid_skels, key=lambda s: (score(s), s.lower()))
        info[d] = [f"{prefix}/{d}/{s}" for s in sorted_skels]
    return info


def extract_voices(media_dir: Path, output_dir: Path, lang: str = "JP") -> None:
    print(f"Extracting {lang} voice archives...")
    archives = sorted(media_dir.rglob(f"{lang}_*.zip"))
    if not archives:
        print(f"No {lang}_*.zip voice archives found under {media_dir}.")
        return

    extracted_count = 0
    for archive_path in archives:
        target_dir = output_dir / archive_path.stem
        target_dir.mkdir(parents=True, exist_ok=True)
        with ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                if entry.is_dir() or Path(entry.filename).suffix.lower() != ".ogg":
                    continue
                member_path = PurePosixPath(entry.filename)
                target_path = target_dir / member_path.name
                if not target_path.exists():
                    with archive.open(entry) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted_count += 1
    print(f"Extracted {extracted_count} {lang} voice clips into {output_dir}.")


def extract_bgm(
    media_dir: Path,
    bgm_dirs: list[Path],
    table_dir: Path,
    memory_lobbies: Optional[list[dict[str, Any]]] = None,
    characters: Optional[list[dict[str, Any]]] = None,
    bgms: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    print("Extracting BGM tracks and building Memorial Lobby BGM map from tables...")

    # Load tables if not provided
    if not bgms:
        bgm_file = table_dir / "BGMExcelTable.json"
        if not bgm_file.is_file() and (table_dir.parent / "Excel" / "BGMExcelTable.json").is_file():
            bgm_file = table_dir.parent / "Excel" / "BGMExcelTable.json"
        if bgm_file.is_file():
            try:
                with open(bgm_file, "r", encoding="utf-8") as f:
                    bgms = json.load(f)
            except Exception:
                bgms = []
        else:
            bgms = []

    bgm_table_map = {b["Id"]: b for b in (bgms or [])}

    if not memory_lobbies:
        lobby_file = table_dir / "MemoryLobbyExcelTable.json"
        if not lobby_file.is_file() and (table_dir.parent / "Excel" / "MemoryLobbyExcelTable.json").is_file():
            lobby_file = table_dir.parent / "Excel" / "MemoryLobbyExcelTable.json"
        if lobby_file.is_file():
            try:
                with open(lobby_file, "r", encoding="utf-8") as f:
                    memory_lobbies = json.load(f)
            except Exception:
                memory_lobbies = []
        else:
            memory_lobbies = []

    if not characters:
        char_file = table_dir / "CharacterExcelTable.json"
        if not char_file.is_file() and (table_dir.parent / "Excel" / "CharacterExcelTable.json").is_file():
            char_file = table_dir.parent / "Excel" / "CharacterExcelTable.json"
        if char_file.is_file():
            try:
                with open(char_file, "r", encoding="utf-8") as f:
                    characters = json.load(f)
            except Exception:
                characters = []
        else:
            characters = []

    char_map = {c["Id"]: c for c in (characters or [])}

    # Discover and copy all BGM tracks
    media_ogg_map: dict[str, Path] = {}
    if media_dir.is_dir():
        for ogg in media_dir.glob("*.ogg"):
            media_ogg_map[ogg.name.lower()] = ogg

    target_filenames: set[str] = set()
    for b in (bgms or []):
        p = b.get("Path", "")
        if p:
            target_filenames.add(f"{os.path.basename(p)}.ogg".lower())

    for pat in ["Theme_*.ogg", "BGM_*.ogg", "AMB_*.ogg", "BlueNewWorld_*.ogg", "TargetForLove*.ogg", "ClearMorning_*.ogg", "*Sound.ogg"]:
        for tf in media_dir.glob(pat):
            target_filenames.add(tf.name.lower())

    extracted_count = 0
    for bd in bgm_dirs:
        bd.mkdir(parents=True, exist_ok=True)
        for low_name in target_filenames:
            src = media_ogg_map.get(low_name)
            if src:
                target = bd / src.name
                if not target.exists():
                    shutil.copy2(src, target)
                    extracted_count += 1
    if extracted_count:
        print(f"Copied {extracted_count} BGM files across output directories.")

    bgm_map: dict[str, Any] = {}

    for lobby in (memory_lobbies or []):
        cid = lobby.get("CharacterId")
        bgm_id = lobby.get("BGMId", 0)
        if not bgm_id:
            continue
        c_info = char_map.get(cid, {})
        dev_name = (c_info.get("DevName") or "").lower()
        prefab = (lobby.get("PrefabName") or "").lower()

        bgm_entry = bgm_table_map.get(bgm_id)
        if bgm_entry and bgm_entry.get("Path"):
            theme_name = f"{os.path.basename(bgm_entry['Path'])}.ogg"
        elif bgm_id == 10004 or cid == 20007:
            theme_name = "BGM_TellYourWorld_Short.ogg"
        else:
            theme_name = f"Theme_{bgm_id:02d}.ogg"

        entry = {
            "CharacterId": cid,
            "PrefabName": lobby.get("PrefabName", ""),
            "BGMId": bgm_id,
            "filename": theme_name,
            "path": f"/data/MediaResources/GameData/Audio/BGM/{theme_name}"
        }

        keys = set()
        if dev_name:
            keys.add(dev_name)
            keys.add(f"{dev_name}_home")
            clean_dev = dev_name[:-8] if dev_name.endswith("_default") else dev_name
            keys.add(clean_dev)
            keys.add(f"{clean_dev}_home")
            keys.add(f"{clean_dev}_home_gl")
            base_dev = dev_name.split("_")[0]
            keys.add(base_dev)
            keys.add(f"{base_dev}_home")
            base_clean = clean_dev.rstrip("0123456789")
            if base_clean:
                keys.add(base_clean)
                keys.add(f"{base_clean}_home")
        if prefab:
            keys.add(prefab)
            clean_p = prefab.replace("lobby", "")
            keys.add(clean_p)
            keys.add(f"{clean_p}_home")
            keys.add(f"{clean_p}_home_gl")
        if cid:
            keys.add(str(cid))
        scen = (c_info.get("ScenarioCharacter") or "").lower()
        if scen:
            keys.add(scen)
            keys.add(f"{scen}_home")

        for k in keys:
            if k:
                bgm_map[k] = entry

    for bd in bgm_dirs:
        map_path = bd.parent / "bgm_map.json"
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(bgm_map, f, indent=2)
        print(f"Wrote BGM map ({len(bgm_map)} keys) -> {map_path}")

    return bgm_map


def write_voice_sources_json(audio_dirs: list[Path], media_dir: Optional[Path] = None) -> dict[str, Any]:
    voice_sources: dict[str, Any] = {}

    jp_packs = set()
    for ad in audio_dirs:
        voc_jp = ad / "VOC_JP"
        if voc_jp.is_dir():
            for p in voc_jp.iterdir():
                if p.is_dir():
                    jp_packs.add(p.name)
    if media_dir and media_dir.is_dir():
        for z in media_dir.rglob("JP_*.zip"):
            jp_packs.add(z.stem)

    if jp_packs:
        voice_sources["JP"] = {
            "directory": "VOC_JP",
            "packs": sorted(jp_packs)
        }

    kr_packs = set()
    for ad in audio_dirs:
        voc_kr = ad / "VOC_KR"
        if voc_kr.is_dir():
            for p in voc_kr.iterdir():
                if p.is_dir():
                    kr_packs.add(p.name)
    if kr_packs:
        voice_sources["KR"] = {
            "directory": "VOC_KR",
            "packs": sorted(kr_packs)
        }

    for ad in audio_dirs:
        ad.mkdir(parents=True, exist_ok=True)
        manifest_path = ad / "voice_sources.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(voice_sources, f, indent=2)
        print(f"Wrote voice-source manifest to {manifest_path}")

    return voice_sources


def extract_common_effect_textures(game_android: Path, common_dir: Path) -> None:
    common_bundles = list(game_android.glob("*spinelobbies*common*tga*.bundle"))
    if not common_bundles:
        return
    common_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for b in common_bundles:
        try:
            env = UnityPy.load(str(b))
            for o in env.objects:
                if o.type.name == "Texture2D":
                    d = o.read()
                    name = getattr(d, "m_Name", "")
                    if name:
                        out_path = common_dir / f"{name}.png"
                        if not out_path.exists():
                            d.image.save(out_path)
                            count += 1
        except Exception:
            pass
    if count:
        print(f"Extracted {count} common lobby effect textures to {common_dir}.")


def extract_interaction_map(game_android: Path, output_file: Path) -> dict[str, Any]:
    print("Extracting live2d-interactions directly from uilobbyelement bundles...")
    bundles = sorted(game_android.glob("*uilobbyelement*.bundle"))
    if not bundles:
        print(f"No uilobbyelement bundles found under {game_android}.")
        return {}

    def interaction_kind(clip: str, bone: str, go: str) -> str:
        text = f"{clip} {bone} {go}".lower()
        if "pinch" in text or "cheek" in text:
            return "pinch"
        if "pat" in text or "touch_point" in text or "hair" in text:
            return "pat"
        if "look" in text or "eye" in text:
            return "look"
        return "touch"

    def resolve_clip_fallback(go_name: str) -> tuple[str, str]:
        lower = go_name.lower()
        if "pinch" in lower:
            return "Pinch_01_M", "PinchEnd_01_M"
        if "pat" in lower or "hair" in lower:
            return "Pat_01_M", "PatEnd_01_M"
        if "eye" in lower:
            return "Look_01_M", "LookEnd_01_M"
        if "pink" in lower:
            return "Pink_01_M", "PinkEnd_01_M"
        if "follow" in lower:
            return "HandFollow_01_M", "HandFollowEnd_01_M"
        return "Touch_01_M", "TouchEnd_01_M"

    characters_data: dict[str, Any] = {}
    character_effects: dict[str, set[str]] = {}

    for b in bundles:
        try:
            env = UnityPy.load(str(b))
        except Exception:
            continue

        obj_map = {o.path_id: o for o in env.objects}

        spine_drag_pids = set()
        for o in env.objects:
            if o.type.name == "MonoScript":
                try:
                    d = o.read()
                    if getattr(d, "m_Name", "") == "SpineDragIK":
                        spine_drag_pids.add(o.path_id)
                except Exception:
                    pass

        if not spine_drag_pids:
            continue

        char_names = set()
        for o in env.objects:
            if o.type.name == "GameObject":
                try:
                    name = o.read_typetree().get("m_Name", "")
                    m = re.match(r"^Lobby([A-Za-z0-9_]+)$", name, re.I)
                    if m:
                        cname = m.group(1).lower()
                        if not cname.endswith("lobbyspine") and not cname.endswith("_bg"):
                            char_names.add(cname)
                except Exception:
                    pass

        if not char_names:
            continue

        for o in env.objects:
            if o.type.name == "GameObject":
                try:
                    name = o.read_typetree().get("m_Name", "")
                    lower_name = name.lower()
                    if name.startswith("FX_") or any(k in lower_name for k in ["flash", "fade", "white"]):
                        for cname in char_names:
                            if cname not in character_effects:
                                character_effects[cname] = set()
                            character_effects[cname].add(name)
                except Exception:
                    pass

        interactions = []
        for o in env.objects:
            if o.type.name == "MonoBehaviour":
                try:
                    d = o.read_typetree()
                    if d.get("m_Script", {}).get("m_PathID") in spine_drag_pids:
                        go_id = d.get("m_GameObject", {}).get("m_PathID")
                        go_name = obj_map[go_id].read_typetree().get("m_Name", "") if go_id in obj_map else ""

                        bone_ref = d.get("Bone", {}).get("m_PathID")
                        bone_name = ""
                        if bone_ref in obj_map:
                            bone_tr = obj_map[bone_ref].read_typetree()
                            b_go_id = bone_tr.get("m_GameObject", {}).get("m_PathID")
                            if b_go_id in obj_map:
                                bone_name = obj_map[b_go_id].read_typetree().get("m_Name", "")

                        in_clip, end_clip = resolve_clip_fallback(go_name)
                        kind = interaction_kind(in_clip, bone_name, go_name)

                        orig = d.get("OrigLocalPos", {})
                        b_offset = d.get("BoneCenterOffset", {})
                        min_pos = d.get("MinLocalPos", {})
                        max_pos = d.get("MaxLocalPos", {})
                        drag = d.get("FollowDragSpeed01", 0.0)
                        release = d.get("FollowReleaseSpeed01", 0.0)
                        trigger = d.get("TriggerDelay", 0.0)

                        interactions.append({
                            "gameObject": go_name,
                            "bone": bone_name,
                            "inClip": in_clip,
                            "endClip": end_clip,
                            "kind": kind,
                            "origin": {"x": orig.get("x", 0.0), "y": orig.get("y", 0.0), "z": orig.get("z", 0.0)},
                            "boneCenterOffset": {"x": b_offset.get("x", 0.0), "y": b_offset.get("y", 0.0), "z": b_offset.get("z", 0.0)},
                            "min": {"x": min_pos.get("x", 0.0), "y": min_pos.get("y", 0.0), "z": min_pos.get("z", 0.0)},
                            "max": {"x": max_pos.get("x", 0.0), "y": max_pos.get("y", 0.0), "z": max_pos.get("z", 0.0)},
                            "dragSpeed": drag,
                            "releaseSpeed": release,
                            "triggerDelay": trigger
                        })
                except Exception:
                    pass

        if interactions:
            for cname in char_names:
                if cname not in characters_data:
                    characters_data[cname] = {
                        "interactions": interactions,
                        "effects": sorted(character_effects.get(cname, []))
                    }

    full_manifest = {
        "characters": characters_data
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(full_manifest, f, indent=2)
    print(f"Extracted interaction map for {len(characters_data)} characters -> {output_file}")
    return characters_data


# ---------------------------------------------------------------------------
# Main CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Blue Archive Live2D & Game Data Extraction Pipeline",
        add_help=True,
    )
    parser.add_argument(
        "-k", "--key",
        required=True,
        help="SQLCipher 32-byte hexadecimal database key"
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        required=True,
        help="Game data input directory"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        required=True,
        help="Viewer data destination directory"
    )
    parser.add_argument(
        "-c", "--character",
        help="Extract single character (e.g. ch0355_home or aru_home)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite existing Live2D textures, skel, and atlas files"
    )
    parser.add_argument(
        "--skip-tables",
        action="store_true",
        help="Skip database table export"
    )
    parser.add_argument(
        "--skip-voices",
        action="store_true",
        help="Skip voice archive extraction"
    )

    args = parser.parse_args()

    input_root = args.input.resolve()
    if not input_root.is_dir():
        parser.error(f"Input directory does not exist or is not a directory: {input_root}")

    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    key = args.key.strip()
    if key.lower().startswith("0x"):
        key = key[2:]
    if len(key) != 64:
        parser.error(f"Database key must be exactly 32 bytes of hexadecimal (64 characters); got {len(key)}")

    # Resolve input subdirectories
    game_android = input_root / "AssetBundles" / "GameData" / "Android"
    if not game_android.is_dir():
        game_android = input_root / "Android" if (input_root / "Android").is_dir() else input_root

    preload_android = input_root / "AssetBundles" / "Preload" / "Android"
    if not preload_android.is_dir():
        preload_android = input_root / "Preload" / "Android" if (input_root / "Preload" / "Android").is_dir() else None

    db_path = input_root / "TableBundles" / "ExcelDB.db"
    if not db_path.is_file():
        db_path = input_root / "ExcelDB.db" if (input_root / "ExcelDB.db").is_file() else None
        if not db_path:
            cand = list(input_root.rglob("ExcelDB.db"))
            if cand:
                db_path = cand[0]

    media_dir = input_root / "MediaResources"
    if not media_dir.is_dir():
        media_dir = input_root

    # Resolve output directory structure
    if output_root.name == "data":
        data_dir = output_root
    elif (output_root / "static" / "data").is_dir():
        data_dir = output_root / "static" / "data"
    elif (output_root / "data").is_dir():
        data_dir = output_root / "data"
    else:
        data_dir = output_root / "data"

    en_char_dir = data_dir / "en" / "GameData" / "Android"
    jp_char_dir = data_dir / "jp" / "Android"
    en_table_dir = data_dir / "en" / "Preload" / "TableBundles" / "Excel"
    jp_table_dir = data_dir / "jp" / "TableBundles" / "Excel"
    jp_audio_dir = data_dir / "jp" / "MediaResources" / "GameData" / "Audio"
    jp_voice_dir = jp_audio_dir / "VOC_JP"
    kr_voice_dir = jp_audio_dir / "VOC_KR"
    en_audio_dir = data_dir / "en" / "MediaResources" / "GameData" / "Audio"
    en_gamedata_audio_dir = data_dir / "en" / "GameData" / "MediaResources" / "GameData" / "Audio"
    bgm_dirs = [
        data_dir / "MediaResources" / "GameData" / "Audio" / "BGM",
        jp_audio_dir / "BGM",
        en_audio_dir / "BGM",
    ]
    interaction_map_file = data_dir / "live2d-interactions.json"

    # 1. Export Excel tables
    dialogs, lobbies, characters, bgms = None, None, None, None
    if not args.skip_tables and db_path and db_path.is_file():
        try:
            dialogs, lobbies, characters, bgms = export_tables(db_path, key, [en_table_dir, jp_table_dir])
        except Exception as e:
            print(f"Table export warning: {e}")

    # 2. Extract Voices (JP and KR)
    if not args.skip_voices and media_dir and media_dir.is_dir():
        try:
            extract_voices(media_dir, jp_voice_dir, lang="JP")
            extract_voices(media_dir, kr_voice_dir, lang="KR")
        except Exception as e:
            print(f"Voice extraction warning: {e}")

    # 2b. Extract BGM & generate bgm_map.json
    if media_dir and media_dir.is_dir():
        try:
            extract_bgm(media_dir, bgm_dirs, en_table_dir, lobbies, characters, bgms)
        except Exception as e:
            print(f"BGM extraction warning: {e}")

    try:
        write_voice_sources_json([jp_audio_dir, en_audio_dir, en_gamedata_audio_dir], media_dir)
    except Exception as e:
        print(f"Voice source manifest warning: {e}")

    try:
        extract_common_effect_textures(game_android, data_dir / "effects" / "common")
    except Exception as e:
        print(f"Common effect textures warning: {e}")

    # 3. Extract interactions map directly from game bundles
    interaction_map: dict[str, Any] = {}
    if interaction_map_file.is_file() and not args.force:
        try:
            with open(interaction_map_file, "r", encoding="utf-8") as f:
                interaction_map = json.load(f).get("characters", {})
        except Exception:
            pass

    if not interaction_map:
        try:
            interaction_map = extract_interaction_map(game_android, interaction_map_file)
        except Exception as e:
            print(f"Interaction extraction warning: {e}")

    # Ensure per-character interactions.json exists in all character directories
    if interaction_map and en_char_dir.is_dir():
        for d in en_char_dir.iterdir():
            if not d.is_dir():
                continue
            char_key = d.name.lower()
            short_key = char_key.replace("_home", "").replace("_teen", "").replace("_multi", "")
            inter = interaction_map.get(short_key) or interaction_map.get(char_key)
            if inter and not (d / "interactions.json").exists():
                with open(d / "interactions.json", "w", encoding="utf-8") as out:
                    json.dump(inter, out, indent=2)

    # 4. Extract Character Lobbies (.skel, .atlas, .png), Timelines, and Audio
    audio_index = index_audio_clips(game_android, preload_android)
    cab_bundle_cache: dict[str, str] = {}
    char_bundles = find_all_character_bundles(game_android)

    if args.character:
        char_key = args.character.lower()
        if char_key not in char_bundles and f"{char_key}_home" in char_bundles:
            char_key = f"{char_key}_home"
        items = [(char_key, char_bundles[char_key])] if char_key in char_bundles else []
    else:
        items = sorted(char_bundles.items())

    processed_count = 0
    total = len(items)

    for char_key, b_paths in items:
        processed_count += 1
        short_key = char_key.replace("_home", "").replace("_teen", "").replace("_multi", "").lower()

        target_dirs = [en_char_dir / char_key]
        jp_dir = jp_char_dir / char_key
        if jp_dir.exists():
            target_dirs.append(jp_dir)

        char_interactions = interaction_map.get(short_key) or interaction_map.get(char_key.lower())

        try:
            res = extract_character_l2d_and_timeline(
                b_paths,
                char_key,
                target_dirs,
                audio_index,
                char_interactions,
                game_android=game_android,
                preload_android=preload_android,
                cab_bundle_cache=cab_bundle_cache,
                force=args.force
            )
            if res and (processed_count % 25 == 0 or processed_count == total):
                print(f"[{processed_count}/{total}] Processed {char_key} ({res['m_Duration']:.1f}s, {len(res['m_Tracks'])} tracks)")
        except Exception as e:
            print(f"Error processing {char_key}: {e}")

    # 5. Generate info.json for both regions
    en_info = generate_info_json(en_char_dir, "data/en/GameData/Android")
    if en_info:
        en_char_dir.mkdir(parents=True, exist_ok=True)
        with open(en_char_dir / "info.json", "w", encoding="utf-8") as f:
            json.dump(en_info, f, indent=2)
        print(f"Wrote {len(en_info)} model entries to {en_char_dir / 'info.json'}.")

    jp_info = generate_info_json(jp_char_dir, "data/jp/Android")
    if jp_info:
        jp_char_dir.mkdir(parents=True, exist_ok=True)
        with open(jp_char_dir / "info.json", "w", encoding="utf-8") as f:
            json.dump(jp_info, f, indent=2)
        print(f"Wrote {len(jp_info)} model entries to {jp_char_dir / 'info.json'}.")

    print("\nAll tasks completed successfully. Pipeline finished!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
