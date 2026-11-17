# OmniTrans 覆盖率报告

> 由 `python mt_coverage.py` 从 `mt_config.ENGINES` 生成（单一事实源，随代码更新重跑即可）。

## 总览

- 内容引擎 **16** 项：全链路 **12**，其中 3 项的封包层依赖真实样本（核心阶段已由合成样本覆盖）；仅识别·暂不支持 4 项（均给出替代方案）
- 载体格式：字幕 4 种、音视频 25 种封装、漫画 10 种容器/图型、MTool json 1 种

## 内容引擎矩阵

| 引擎 | 状态 | 依赖 | 提取 → 回写 | 模拟测试 | 级别 |
|---|---|---|---|---|---|
| RPG Maker MV/MZ | ✓ 全链路 | - | `engines/rpg_extract.py` → `engines/rpg_apply.py` | `tests/_test_rpg.py` | FULL |
| RPG Maker VX Ace / VX / XP | ✓ 全链路 | - | `engines/rva_extract.py` → `engines/rva_apply.py` | `tests/_test_rva_pipeline.py` | FULL |
| SRPG Studio | ✓ 全链路 | - | `engines/srpg_extract.py` → `engines/srpg_apply.py` | `tests/_test_engine_matrix.py` | STAGE |
| Kirikiri (吉里吉里) | ✓ 全链路 | - | `engines/krkr_extract.py` → `engines/krkr_apply.py` | `tests/_test_krkr.py` | FULL |
| Ren'Py | ✓ 全链路 | - | `engines/renpy_extract.py` → `engines/renpy_apply.py` | `tests/_test_engine_matrix.py` | FULL |
| TyranoScript | ✓ 全链路 | - | `engines/tyrano_extract.py` → `engines/tyrano_apply.py` | `tests/_test_tyrano.py` | FULL |
| Unity | ✓ 全链路 | UnityPy | `engines/unity_extract.py` → `engines/unity_apply.py` | `tests/_test_unity.py + tests/_test_engine_matrix.py` | STAGE |
| SiglusEngine (Key) | 仅识别·不支持 | - | — | `—` | — |
| AliceSoft (.ain/.ex) | ✓ 全链路 | - | `engines/ain_extract.py` → `engines/ain_apply.py` | `tests/_test_ain.py` | FULL |
| ExHIBIT 私有引擎 | 仅识别·不支持 | - | — | `—` | — |
| Wolf RPG Editor (ウディタ) | ✓ 全链路 | - | `engines/wolf_extract.py` → `engines/wolf_apply.py` | `tests/_test_wolf.py + tests/_test_engine_matrix.py` | STAGE |
| NScripter | 仅识别·不支持 | - | — | `—` | — |
| EXSTIA (.MED) | 仅识别·不支持 | - | — | `—` | — |
| Video / Audio (Whisper ASR) | ✓ 全链路 | faster-whisper | `engines/media_extract.py` → `engines/subtitle_apply.py` | `tests/_test_engine_matrix.py` | FULL |
| Subtitle files (SRT/ASS/VTT) | ✓ 全链路 | - | `engines/subtitle_extract.py` → `engines/subtitle_apply.py` | `tests/_test_subtitle.py` | FULL |
| Comics (images / CBZ) | ✓ 全链路 | rapidocr-onnxruntime, Pillow | `engines/comic_extract.py` → `engines/comic_apply.py` | `tests/_test_comic.py` | FULL |

级别说明：**FULL**=合成样本全链路（提取→翻译→回写全部模拟验证）；**STAGE**=合成样本覆盖核心阶段（解析/收集/回写逻辑）；封包层需真实样本；**REAL**=需真实游戏样本

## 载体格式矩阵

| 载体 | 处理方式 | 格式 | 状态 |
|---|---|---|---|
| 字幕 | SRT / VTT / ASS / SSA | `.srt .vtt .ass .ssa` | ✓ 全链路 |
| 音视频 | faster-whisper 本地听译（无需云/物理样本） | `.mp4 .mkv .avi .mov .wmv .mpg .mpeg .ts .m2ts .webm .flv .m4v .3gp .ogv .rmvb .vob .mp3 .wav .m4a .flac .ogg .opus .wma .aac .amr` | ✓ 全链路 |
| 漫画 | OCR→翻译→嵌字（图片文件夹 / CBZ·CBR·CB7） | `.jpg .jpeg .png .webp .gif .bmp .avif  .cbz .cbr .cb7` | ✓ 全链路 |
| MTool json | ManualTransFile.json 运行时挂载导出 | `.json` | ✓ 全链路 |
