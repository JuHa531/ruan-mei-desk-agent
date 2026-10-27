# 界面素材

背景、图标、表情原图与缩略图位于本目录，元数据分别由 `bg-library.json` 与 `stickers.json` 管理。
自动表情根据回复内容选择，存在同意图的无腮红版本时优先使用；用户可以关闭自动表情。

`stickers.custom.json` 保存自定义表情，重新导入素材时由 `scripts/import_asset_folders.py` 合并保留。
`sticker-rm-*-v2.png` 是倾听、认可、晚安和悠闲的无腮红版本，配有对应缩略图。
其他原图与缩略图作为素材保留。大型背景视频不随源码分发。
