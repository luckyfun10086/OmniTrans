# OmniTrans — Engine-agnostic Game Translator

**English** | [简体中文](README.zh-CN.md)

One-click game localization: drop a game folder — RPG Maker MV/MZ, VX Ace/VX/XP,
SRPG Studio, Kirikiri, Ren'Py, TyranoScript, Unity — or a folder of subtitle files
(.srt/.ass/.vtt) or raw video/audio (locally transcribed with Whisper) — the
format is auto-detected,
text is extracted, machine-translated and written back with automatic backups
(Kirikiri/Ren'Py use non-destructive overlay patches). MTool-exported
`ManualTransFile.json` files are also supported as input. Free public translation
endpoint by default — **no API key, no quota, no content filtering** — or plug in
your own DeepL/LLM API via the GUI (credentials stored in a local `.env`, never
committed).

> [MTool](https://mtool.app/) — an excellent **third-party** game translation &
> > modification tool (made by others, closed-source, mtool.app; unrelated to this
> > repository's author). This project started out automating its exported JSON files;
> > standalone engine support came later, outgrew the original name AutoMT, and the
> > tool became OmniTrans.

Validated in the field: a 70,000+ string MTool corpus; Kirikiri on three real games
(17 archives / 22,806 files / up to 44,296 segments per game); Ren'Py against the
SDK's engine-generated French translation (788/788 statement identifiers matched);
the Ruby Marshal codec passes byte-exact ground truth, 300 fuzz round-trips and
bidirectional cross-validation with the `rubymarshal` library. Eleven self-test
suites cover every engine end-to-end.

## Download

Grab `OmniTrans.exe` from the [**Releases**](https://github.com/luckyfun10086/OmniTrans/releases)
page — a standalone Windows binary (~11 MB), no Python required. v2.0.0 ships
11-format support (8 game engines + subtitles + video/audio transcription +
comics), the 3-tab GUI and dark mode. Everything (`.env`, `names.txt`,
`mt_work/`) is created next to the exe.

> **Quality & fair use**: the built-in free endpoint delivers basic machine-translation
> quality — fine for understanding a game, not for polished prose. For better results,
> configure a DeepL/LLM endpoint in the API panel below. The free endpoint is unofficial
> and may change or rate-limit at any time; if it ever does, the tool keeps working with
> any custom endpoint. Translate only content you have the right to use.

## GUI (recommended) — three functional zones

The window is organized into tabs:

1. **⚡ Quick Translate** — drag & drop an MTool-exported JSON (or anything
   `_extracted.json`), pick **source → target language**, click **Start**:
   live progress bar ① Clean & mask → ② Translate (speed + ETA) →
   ③ Validate & apply
2. **🎮 Game Localization** — drop a **game folder / EXE** anywhere in the
   window: the engine is auto-detected (badge shown), then a guided flow:
   ② Extract text → ③ Translate → ④ Apply to game. A live table lists every
   supported engine (and detected-but-unsupported ones with guidance)
3. **⚙ Settings** — translation API configuration + custom background
   image for the drop card (needs Pillow, auto-install prompt; `MT_BG`)
4. **📚 Library** — local record of every translated game (auto-registered
   on completion, marked when applied)
5. **✏️ Review** — search & hand-fix translations after a run, before
   applying them to the game

A **dark / light theme** toggle (☀/🌙, top-right) is persisted to `.env`
(`MT_THEME`); dark is the default. After translation finishes, OmniTrans prompts
to apply the result to the game and switches back to the Game tab. Cancel
anytime — progress is resumable.

> Drag & drop inside the packaged exe works out of the box. Running from source:
> `pip install tkinterdnd2` (drag & drop; falls back to a file picker without it)
> and optionally `pip install sv-ttk` (modern Win11-style theming; without it a
> classic theme is used).
>
> Rebuild the exe (engine scripts are bundled as data files — don't drop
> the `--add-data` entries):
```
pip install pyinstaller
pyinstaller --onefile --windowed --name OmniTrans --collect-all tkinterdnd2 
  --collect-all sv_ttk 
  --add-data "engines/rpg_extract.py;engines/" --add-data "engines/rpg_apply.py;engines/" 
  --add-data "engines/rva_extract.py;engines/" --add-data "engines/rva_apply.py;engines/" 
  --add-data "engines/rvdata.py;engines/" 
  --add-data "engines/srpg_extract.py;engines/" --add-data "engines/srpg_apply.py;engines/" 
  --add-data "engines/krkr_extract.py;engines/" --add-data "engines/krkr_apply.py;engines/" 
  --add-data "engines/krkr_xp3.py;engines/" 
  --add-data "engines/renpy_extract.py;engines/" --add-data "engines/renpy_apply.py;engines/" 
  --add-data "engines/renpy_rpyc.py;engines/" 
  --add-data "engines/tyrano_extract.py;engines/" --add-data "engines/tyrano_apply.py;engines/" 
  --add-data "engines/unity_extract.py;engines/" --add-data "engines/unity_apply.py;engines/"
  --add-data "engines/wolf_extract.py;engines/" --add-data "engines/wolf_apply.py;engines/"
  --add-data "engines/subtitle_extract.py;engines/" --add-data "engines/subtitle_apply.py;engines/"
  --add-data "engines/subtitle_lib.py;engines/"
  --add-data "engines/media_extract.py;engines/"
  --add-data "engines/mtool_export.py;engines/" mt_gui.py
```

Output: `yourfile_translated.json` next to the input — keys are exact original strings,
so MTool picks them up directly.

## Privacy & Security Design

- **Zero secrets in code**: no API keys, no personal paths anywhere in the repository
- **Personal config isolated**: endpoint URL / API key / header live in `.env`
  (excluded by `.gitignore`)
- **Local data isolated**: `mt_work/` workdirs, `names.txt`, `ManualTransFile*.json`
  game texts are all gitignored — your game content and terminology never leave the machine
- Before publishing your fork: `git status` should never list `.env`, `mt_work/`, or any json

## Translation APIs (two kinds)

Pick an **API type** in the GUI panel, fill in the fields, **Save to .env**.

### Type 1 — MT (traditional machine translation, `MT · GET`)

GET-template endpoints using `{sl}` / `{tl}` / `{q}` placeholders:

```
https://api.example.com/translate?source={sl}&target={tl}&text={q}
```

Supported / tested:

| Service | How |
|---------|-----|
| **Built-in free endpoint** (Google) | leave the default URL — no key, batched 8 strings/request, basic quality |
| **LibreTranslate** (self-host / public) | `https://libretranslate.com/translate?q={q}&source={sl}&target={tl}` + API key header `X-api-key` |
| **MyMemory** | `https://api.mymemory.translated.net/get?q={q}&langpair={sl}|{tl}` |
| **DeepLX** (self-hosted DeepL proxy) | `http://localhost:1188/translate?text={q}&source_lang={sl}&target_lang={tl}` |
| Any other GET API | craft the URL with the three placeholders; response auto-detected (Google list / `translations[]` / `translatedText` / plain text) |

### Type 2 — AI translation (`AI · OpenAI`)

OpenAI-compatible **chat/completions** endpoints (POST + JSON). Fill the full URL, your
API key and a model name — quality is dramatically better than MT, at API cost:

| Service | URL | Model example |
|---------|-----|---------------|
| **DeepSeek** | `https://api.deepseek.com/chat/completions` | `deepseek-chat` |
| **OpenAI** | `https://api.openai.com/v1/chat/completions` | `gpt-4o-mini` |
| **Kimi (Moonshot)** | `https://api.moonshot.cn/v1/chat/completions` | `moonshot-v1-8k` |
| **智谱 GLM** | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | `glm-4-flash` |
| **OpenRouter** (Claude/Gemini/…) | `https://openrouter.ai/api/v1/chat/completions` | `anthropic/claude-3.5-haiku` |
| **Gemini** (OpenAI-compat) | `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions` | `gemini-2.0-flash` |
| **Ollama** (local, no key) | `http://localhost:11434/v1/chat/completions` | `qwen2.5:7b` |

**Error prompts & sensitive-word fallback**: connection problems are classified into
three kinds with clear bilingual messages — *fatal* (401 wrong key / 402 insufficient
balance / 404 bad model: stops immediately with a dialog, no wasted retries), *skip*
(content blocked by the provider's safety policy), and *retry* (429 rate-limit / network
hiccups: automatic backoff). Blocked strings are automatically **retried via the built-in
free MT endpoint** (which has no content filter) — lower quality than AI but far better
than leaving English; the run summary reports how many were salvaged. Disable with
`MT_FALLBACK=0`.

The **AI mode batches 24 strings per request** (id-aligned JSON with equal-length
validation and graded fallback to per-string), and optionally attaches the
neighbouring 2 lines as read-only context for tone/person consistency
(`MT_CONTEXT=0` to disable).

Equivalent `.env` keys are documented in [`.env.example`](.env.example).

## Proper-Noun Handling

### names.txt (optional, always takes priority)

One entry per line, two forms:

```
Alice=爱丽丝       masked, then restored as the Chinese translation (recommended)
Wonderland=仙境
Bob               masked, kept as-is
```

Masked terms are never machine-translated — **MT can never turn "Alice" into something
random** — and the `=` form guarantees a uniform translated name throughout.

### Automatic detection (zero-config, per-language, toggleable)

Without a names.txt, OmniTrans detects proper nouns per source language and keeps them
consistent across the whole file:

| Source language | Method | Notes |
|-----------------|--------|-------|
| Latin-script (en, …) | Capitalization statistics + built-in common-word list | Names are almost always capitalized and never lowercase; common words appear both ways and are filtered, incl. habitually-capitalized words like *thanks/doctor* |
| **Japanese** | Repeated katakana runs | JRPG character names are almost always katakana (アリス、リチャード) — a hard signal; ships with a game-term stoplist (ダメージ/スキル etc.) |
| Russian & inflected | Capitalized-prefix clustering | Case variants (Алиса/Алису/Алисе) cluster into one name |
| Chinese / Korean | Skipped | No case/kana signal — the log suggests using names.txt |

Detected words and their counts are listed in the log for full transparency.
**Don't want this?** Uncheck "Auto-detect names" in the GUI (persisted via Save to .env),
or use `--no-auto-names` / `MT_AUTO_NAMES=0`. Names are then machine-translated like any
other text (more natural renderings, consistency not guaranteed). Manual names.txt entries
work in every mode.

## Standalone Engine Localization (no MTool needed)

**Supported engines:**

| Engine | Data location | Status |
|--------|---------------|--------|
| **Wolf RPG Editor** (ウディタ) | `Data.wolf` / `Data/` | ✅ supported — bridges UberWolf+WolfTL (MIT, auto-downloaded); Wolf 3.x fully writable, 2.x is CP932 (Chinese dropped → use the MTool export path) |
| RPG Maker **MZ** | `data/` | ✅ fully supported |
| RPG Maker **MV** | `www/data/` (or `data/` in some distributions) | ✅ fully supported |
| **RPG Maker VX Ace / VX / XP** | `Data/*.rvdata2` (VX: `.rvdata`, XP: `.rxdata`) | ✅ fully supported — pure-Python Ruby Marshal 4.8 codec, byte-exact round-trip |
| **SRPG Studio** | `data.dts` (with `runtime.rts`/`environment.evs`) | ✅ fully supported — bridges [SRPG-ToolBox](https://github.com/Sinflower/SRPG-ToolBox) (MIT), auto-downloaded on first run |
| **Kirikiri / KAG** (.xp3) | `data.xp3` + `patch*.xp3` | ✅ fully supported — all archives parsed in mount order; write-back is a **non-destructive overlay patch** |
| **Ren'Py** (6.99+/7/8) | `game/*.rpa`, `game/*.rpyc` | ✅ fully supported — generates official `game/tl/<lang>/` packages (non-destructive) |
| **TyranoScript** | `data/scenario/*.ks` | ✅ fully supported |
| **Unity** (TextAsset scenarios / MonoBehaviour strings / Addressables & Localization bundles) | `*_Data` + `StreamingAssets/**/*.bundle` | ✅ supported (needs UnityPy — the GUI offers to install it on first use; strings compiled into DLLs are out of scope) |
| **Subtitles** (.srt / .ass / .vtt) | any folder containing subtitle files | ✅ supported — dedup + timeline-preserving write to `name.zh.srt` next to the originals (non-destructive) |
| **Video / Audio** (no subtitles) | `.mp4` `.mkv` `.ts` … / `.mp3` `.m4a` … | ✅ supported — local Whisper transcription (faster-whisper) generates the `.srt`, then the subtitle flow takes over; existing same-name `.srt` files are reused, never re-transcribed |
| **Comics** (image folders / `.cbz`) | folders of page images, `.cbz`/`.cbr`/`.cb7` | ✅ supported — local OCR ([rapidocr-onnxruntime](https://github.com/RapidAI/RapidOCR)) → translate → Pillow lettering (vertical text in tall boxes for zh/ja, auto font sizing); output to a sibling `name.zh/` folder or `name.zh.cbz`, originals untouched |

Detected but not (yet) supported: SiglusEngine (Key), AliceSoft (.ain), ExHIBIT,
NScripter, EXSTIA — dropping such a folder tells you which engine it is and
what to use instead.

MV/MZ store all game text as plain JSON (`Map*.json`, `CommonEvents.json`,
`Troops.json`, …) — OmniTrans reads and patches them directly, no third-party tool
required.

```
python engines/rpg_extract.py <game-folder>     # → game.extracted.json
python mt_clean.py game.extracted.json  # ① mask
python mt_translate.py                  # ② translate (resumable)
python mt_apply.py game.extracted.json  # ③ restore → game.extracted_translated.json
python engines/rpg_apply.py <game-folder> game.extracted_translated.json   # write back
```

What gets extracted: dialogue (code 401, consecutive lines merged into one block for
better quality), scrolling text (405), choices (102), actor name/nickname changes
(320/324), map display names — from `Map*.json`, `CommonEvents.json`, `Troops.json`.

Safety: `rpg_apply.py` backs up originals to `data_backup/` first, only replaces
exact-match blocks, and skips any block whose translated line count doesn't match —
the game can never be corrupted by a bad translation.

### RPG Maker VX Ace / VX / XP games

`.rvdata2` files are Ruby Marshal 4.8 dumps. OmniTrans ships a pure-Python,
zero-dependency Marshal codec (`rvdata.py`) that round-trips **byte-exact** —
verified against hand-crafted ground-truth byte vectors, 300 random-tree fuzz
cases, and bidirectional cross-validation against the `rubymarshal` library.

```
python engines/rva_extract.py <game-folder>     # dialogue/choices/rename/map names/skill & item text
python mt_clean.py <game>_extracted.json && python mt_translate.py && python mt_apply.py <game>_extracted.json
python engines/rva_apply.py <game-folder> <game>_extracted_translated.json
```

Safety: only exact-match blocks are replaced (line-count mismatch keeps the
original), `Scripts`/`System` are never touched, every modified file is backed
up to `Data_backup/`, and each written file is re-parsed before the atomic
replace. Translations mutate strings in place, so Marshal link/symbol tables
can never shift.

### Kirikiri (吉里吉里) games — ADV visual novels

All `*.xp3` archives are parsed in mount order (later archives override earlier
ones — `data.xp3` → `patch001.xp3` → …), covering v1/v2 headers, secondary
indexes, zlib & raw index chunks, and three different packer layouts (verified
on real games). KAG `.ks` scripts (CP932 / UTF-16LE / UTF-8) are extracted
line-by-line: text outside `[tags]`, skipping comments, labels, `@` commands
and embedded TJS (`iscript`/`macro`) blocks.

```
python engines/krkr_extract.py <game-folder>    # → <game>_extracted.json (e.g. 44,296 segments from a real game)
python mt_clean.py <game>_extracted.json && python mt_translate.py && python mt_apply.py <game>_extracted.json
python engines/krkr_apply.py <game-folder> <game>_extracted_translated.json
```

Write-back is **non-destructive**: only the modified `.ks` files are packed into
`patch_zz_omnitrans.xp3` which mounts last and overrides the originals — delete
that one file to uninstall. If Chinese text doesn't fit a CP932 script's
encoding, the file is upgraded to UTF-16LE+BOM automatically (`--keep-enc` to
skip such files instead).

### Ren'Py games

Reads `.rpa` archives (RPA-2.0/3.0) and `.rpyc` bytecode (the RPC2 format used
by Ren'Py 6.99+/7/8) with a restricted, code-execution-free unpickler.
Dialogue comes from `TranslateSay`/`Say` nodes **with the engine's own
translation identifiers**; menu choices and `_()` strings are collected too.

```
python engines/renpy_extract.py <game-folder>   # → <game>_extracted.json
python mt_clean.py <game>_extracted.json && python mt_translate.py && python mt_apply.py <game>_extracted.json
python engines/renpy_apply.py <game-folder> <game>_extracted_translated.json [language]
```

`renpy_apply.py` generates an **official translation package** in
`game/tl/<language>/omnitrans_script.rpy` (default language `chinese`) —
`translate <lang> <identifier>:` blocks for dialogue plus a
`translate <lang> strings:` block for choices/UI text. Switch the language
in-game (Preferences → Language) to see it; delete the folder to uninstall.
No game file is ever modified.

Validated against the SDK's engine-generated French translation of the tutorial
game: all 788 statement identifiers matched, regenerated blocks are identical
to the official ones.

### TyranoScript games

```
python engines/tyrano_extract.py <game-folder>  # data/scenario/*.ks + character names from system json
python mt_clean.py <game>_extracted.json && python mt_translate.py && python mt_apply.py <game>_extracted.json
python engines/tyrano_apply.py <game-folder> <game>_extracted_translated.json
```

Text segments outside `[tags]` are extracted (comments/labels/speaker
lines/macro & eval blocks skipped, `[link]` choice text included) and written
back with exact in-line replacement; each original file is backed up as
`*.automt.bak`.

### Wolf RPG Editor (ウディタ) games

Bridges two MIT tools (auto-downloaded to `bin/wolf/` on first run):
[UberWolf](https://github.com/Sinflower/UberWolf) unpacks `.wolf` archives
(originals renamed `*.wolf.automt.bak`; the engine then reads the plain
`Data/` folder — no repacking needed) and
[WolfTL](https://github.com/Sinflower/WolfTL) converts the event/database
binaries to JSON and back.

```
python engines/wolf_extract.py <game-folder>   # unpack → dump → <game>_extracted.json
python mt_clean.py <game>_extracted.json && python mt_translate.py && python mt_apply.py <game>_extracted.json
python engines/wolf_apply.py <game-folder> <game>_extracted_translated.json
```

Extracts Message/Choices commands plus database names/values; labels and
event-name references are never touched. Apply verifies the patched data by
re-parsing it and warns if translation characters were dropped by the
archive's encoding — **Wolf 3.x accepts Chinese end-to-end; Wolf 2.x is
CP932 and drops Simplified Chinese characters** (Japanese-compatible
translations still apply). For 2.x Chinese localization use the MTool
export path instead. Verified on the official 3.728 base system (full
round-trip) and a real packed 2.x game (Misao, 548 strings).

### Subtitle files (.srt / .ass / .vtt)

Drop a video folder (or a single subtitle file) — recognized as the *Subtitle*
engine. Timelines, VTT headers and ASS styles are preserved via a sidecar file;
duplicate lines are deduplicated (translated once, replaced everywhere); inline
tags (`<i>`, `{\an8}`, ASS `{\...}`/`\N`) are stripped before translation.
Writing back is **non-destructive** — output lands next to the originals:

```
python engines/subtitle_extract.py <folder>    # → <name>_extracted.json + <name>_subs.json
python mt_clean.py <name>_extracted.json && python mt_translate.py && python mt_apply.py <name>_extracted.json
python engines/subtitle_apply.py <folder> <name>_extracted_translated.json   # ep01.srt → ep01.zh.srt
```

Encoding auto-detection: BOM / UTF-8 / GBK / Big5 / Shift-JIS / cp1252 —
output is always UTF-8. Untranslated entries keep the original text, so
partial translations are safe to apply. Pass `--bi` for bilingual subtitles
(translation on top, original below).

### Video / audio without subtitles (local Whisper transcription)

Drop a folder of videos (or audio) — recognized as the *Video/Audio* engine.
Each file is transcribed **locally** with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
(CPU, int8 — audio never leaves the machine) into a same-name `.srt`, which
then flows through the subtitle pipeline above. Files that already have a
same-name `.srt` are reused as-is. Progress streams live into the GUI log.

- Dependency: `pip install faster-whisper` (~150 MB; the GUI offers to install
  it on first use, same as UnityPy)
- Model: downloaded automatically on first transcription and cached
  (`small` ≈ 244 MB by default); pick `tiny`…`large-v3` via `MT_ASR_MODEL` in
  `.env`. Slow HuggingFace downloads? Set `HF_ENDPOINT=https://hf-mirror.com`
- Source language is auto-detected per file (or forced via `MT_SL`)

### Comics (image folders / CBZ)

Drop a folder of page images or a `.cbz` — recognized as the *Comics*
engine. Pages are OCR'd locally with
[rapidocr-onnxruntime](https://github.com/RapidAI/RapidOCR) into text
regions; repeated lines dedup into one translation. After translation,
`comic_apply.py` lettering-renders each region: the box is filled with a
color sampled from its border (bubbles ≈ white), then the translation is
auto-sized and drawn — tall boxes with zh/ja text render vertically
(columns right-to-left). Symbol-only regions (♪ etc.) are neither
translated nor touched. Output is non-destructive: a sibling `name.zh/`
folder, or `name.zh.cbz` for archives.

- Dependencies: `pip install rapidocr-onnxruntime Pillow` (GUI prompts on
  first use); the font is picked from system CJK fonts, override via
  `MT_FONT` in `.env`
- Known limit: the OCR model is strongest at horizontal text; heavily
  vertical Japanese manga is only partially recognized at the source stage
  (translation rendering is unaffected). A manga-ocr bridge is on the
  roadmap for that case.

### SRPG Studio games

```
python engines/srpg_extract.py <game-folder>   # auto: download tool → unpack → patch → collect
python mt_clean.py <game>_extracted.json
python mt_translate.py                 # MT or AI (set MT_API_TYPE=openai + model in .env)
python mt_apply.py <game>_extracted.json
python engines/srpg_apply.py <game-folder> <game>_extracted_translated.json
```

Safety: original `data.dts` is backed up to `.automt.bak`; messages are re-chunked on
original line boundaries (mismatched line counts are skipped, original kept); if
`localization.dat` (official localization) is present it is disabled automatically —
it would otherwise override custom translations. Battle-tested on a 943 MB game
(6,985 strings extracted → 26 marker translations applied → repacked → re-parsed
to confirm).

### Unity games

```
pip install UnityPy                       # only for CLI use; the GUI installs it on demand
python engines/unity_extract.py <game-folder>     # scan assets/levels/bundles → strings + manifest
python mt_clean.py <game>_extracted.json && python mt_translate.py && python mt_apply.py <game>_extracted.json
python engines/unity_apply.py <game-folder> <game>_extracted_translated.json
```

Covers: TextAssets (JSON scenario files parsed value-by-value), strings embedded in
MonoBehaviour data (works even for IL2CPP builds without typetrees, via length-prefix
scanning), and `.bundle` files under StreamingAssets (incl. Addressables and Unity
Localization string tables). TMP layout tables (LineBreaking etc.) are auto-excluded.

Safety: writes go to a temp file first and are swapped in atomically (originals are
never truncated before the new data is fully produced); every modified file is backed
up to `.automt.bak`; byte-prefix rebuilds are validated and skipped on mismatch.
Battle-tested on an IL2CPP + Addressables game (283 strings extracted → 68 patched →
re-extraction found every marker back).

> Tip: for games that ship with a partial translation patch, the extraction contains
> both translated and untranslated strings — delete the already-translated entries
> from `<game>_extracted.json` to translate only the remainder. For Unity Localization
> games the translation is written into the source-language table (select that
> language in-game to see it).

## MTool interop

`mtool_export.py` converts an OmniTrans translation into a MTool
`ManualTransFile.json` (runtime-overlay format) — the output format is
identical; what the exporter adds are **key-form variants** so MTool's
runtime-intercepted keys can match: line-split entries (choices/short lines),
leading-control-code-stripped, and all-codes-stripped forms. Extra keys are
harmless (MTool falls back to the original text for unmatched keys).

```
python engines/mtool_export.py <game>_extracted_translated.json --dir <game-folder>
```

The GUI's Game tab has an **📤 Export for MTool** button doing the same.
Measured against real MTool exports, variants raise key coverage by a
stable margin (e.g. 19.1%→23.7% of MTool keys, 20.3%→25.2% of text-only
keys) — MTool's runtime dictionary accumulates fragments/numbers/version
drift that static extraction can't match. For engines OmniTrans writes
back directly, the static ④ Apply is always 100%; the MTool path is most
valuable for engines we detect but don't support (Siglus, AliceSoft,
ExHIBIT, Wolf, EXSTIA…): export untranslated text from MTool, translate
it here, put the file back.

## CLI (equivalent to the GUI)

```
python mt_clean.py [file]     ① clean & mask: codes/newlines/names → 〔Thash〕 tokens
python mt_translate.py        ② translate: batched endpoint requests (resumable)
python mt_apply.py [file]     ③ restore: unmask → validate → clean → write output
```

`mt_translate.py --seg` retranslates stubborn strings segment-wise (tokens can never be
lost). The optional `[file]` argument works for any engine's `*_extracted.json`; it
defaults to `ManualTransFile.json` in the current directory.

## Key Mechanisms (battle-tested)

| Mechanism | Why |
|-----------|-----|
| Content-hash tokens 〔Txxxxxxxx〕 | Re-runs and incremental exports never invalidate prior work |
| Skip already-translated entries | Every stage is resumable |
| 8 strings/request + throttle + backoff | 47k strings in 2.5h without bans |
| `--seg` segment-wise mode | MT occasionally drops tokens; splitting on tokens makes that impossible |
| Count-based token validation | Catches lost/duplicated tokens even when the same token appears twice |
| Bracket-variant tolerance | MT normalizes 〔〕 to 【】（）[], adds spaces, fullwidth chars — all normalized back |
| Cleanup uses `[ \t]` only | `\s` eats real newlines (1,258 entries lost to this in testing) |
| Invalid-escape sanitization | MT injects `\ ` `\~` etc.; stripped against the engine-valid set |
| Failed entries stay empty | MTool falls back to the original text — never breaks the game |

## Typical Workflow

**Recommended (GUI, any engine)** — drop the game folder into the window and follow
the guided Game Localization tab: ① engine detected → ② Extract text → ③ Translate
→ ④ Apply to game. Backups are automatic at every step.

**MTool JSON (CLI)**:

```
1. MTool → export ManualTransFile.json → copy into this folder
2. (optional) put the game's names/places into names.txt
3. python mt_clean.py
4. python mt_translate.py          # interrupt anytime, rerun to resume
5. python mt_apply.py
6. If "token lost" entries are reported:
   python mt_translate.py --seg    # retries only the stubborn ones
   python mt_apply.py
7. Import ManualTransFile_translated.json back into MTool
```

**Any engine (CLI)**: run the engine's `<engine>_extract.py`, then the same three
pipeline steps on `<game>_extracted.json`, then `<engine>_apply.py` — see the
per-engine sections above.

## Project layout

```
mt_gui.py            GUI entry point (PyInstaller target)
mt_clean.py          CLI stage 1: clean & mask
mt_translate.py      CLI stage 2: translate (batched)
mt_apply.py          CLI stage 3: restore & validate
mt_config.py         config layer (.env, URLs, name detection, engine registry)
engines/             one extractor/applier pair per engine + binary codecs
  rpg_*.py           RPG Maker MV/MZ          rvdata/rva_*.py   VX Ace/VX/XP (Ruby Marshal)
  krkr_*.py          Kirikiri (.xp3)          renpy_*.py        Ren'Py (rpyc/rpa + tl)
  tyrano_*.py        TyranoScript             srpg_*.py         SRPG Studio
  unity_*.py         Unity                     wolf_*.py         Wolf RPG (UberWolf/WolfTL)
  mtool_export.py    MTool-compatible export
tests/               11 self-test suites (run from anywhere)
names.example.txt    names.txt template
```

## License

MIT
