# DoroHelper 模板替换提醒

当前已通过脚本从 DoroHelper 的 `PicLib.ahk` 导入以下模板到本项目：

- `assets/zh-CN/daemon/MINIMAP_MAP_POINTER.png`
- `assets/zh-CN/daemon/MINIMAP_ZOOM_ICON.png`
- `assets/zh-CN/daemon/MINIMAP_ENEMY_TRIANGLE.png`
- `assets/zh-CN/daemon/MINIMAP_ENEMY_CIRCLE.png`

## 后续必须做的事

1. 使用你自己的游戏截图，重新制作并替换上述 4 张图片。  
2. 替换后实机验证 `SemiCombat -> MainStoryMark` 是否稳定命中。  
3. 若误点较多，调整 `module/daemon/semi_combat.py` 中模板匹配阈值（`similarity`）与小地图搜索区域。

## 说明

- 目前版本是为了先验证流程，模板来源于 DoroHelper 的 FindText 编码数据。  
- 为降低后续维护和许可风险，建议尽快替换成你自己采集的模板图。  
