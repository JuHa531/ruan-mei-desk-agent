# 梅梅内置阮梅桌宠

这是由梅梅主程序管理的 Windows 透明桌面伙伴，沿用梅梅的角色设定、对话、记忆和语音服务。用户从梅梅顶栏「桌宠」开启；最小化主窗口可以保留桌宠，关闭梅梅则同时结束桌宠。没有独立桌面快捷方式。

## 功能

- 人物拖动、百分比缩放、置顶和点击穿透恢复；设置窗口打开时恢复并激活。
- 双眼与头颈跟随鼠标、连续眨眼和表情、自然待机、短曝光运动模糊。
- 日常待机、吃点心、双手端杯三种动作，包含拿取、使用、收回和改选时的连续过渡。
- 点心动作包含承托盘子、从上方落叉、取小口和送入口；杯饮由一手握柄、另一手托底。
- 点击头部或身体互动、时段问候、休息提示、生日问候、音量和勿扰设置。
- 青蓝主题按键云朵，仅显示最近一个可打印字符，约一秒后消失；可关闭显示。
- 鼠标轨迹、猫耳、眼镜及骨骼预览可在设置中调整。

表情快捷键为空格＋数字，装扮为空格＋F1／F2，动作为空格＋F3／F5／F6。可启用 Ctrl＋Alt 备用组合键；Ctrl＋Alt＋P 恢复人物点击操作。F4 不绑定动作。完整操作见 [桌宠说明](../docs/DESKTOP_PET.md)。

## 与梅梅连接

`app/pet_controller.py` 通过私有 Windows 命名管道管理组件，使用 Job Object 清理主程序异常退出后的渲染进程。聊天固定连接本机 `127.0.0.1:7788`；内置模式返回现有主界面对话，不另外建立一份聊天和历史。

文字、图片、麦克风、音乐和工具调用继续使用梅梅主界面。角色语音复用梅梅已经配置的 TTS；英文音色重建由梅梅的可选英文路由处理。桌宠不另外加载一套聊天模型。

大小及开关保存在 `app/desktop-profile/pet-mode.json`，其他偏好在 `app/desktop-profile/pet`；这些本机状态不提交到仓库。迁移机器时配置 `RM_TOOLKIT_ROOT`、`RM_APP_PYTHON`，并按主项目说明安装 Python 和模型依赖。

## 构建与语音

需要 Node.js 22+，在本目录执行：

```powershell
npm ci
npm test
npm run package
```

构建后的 `release/win-unpacked` 整个目录供梅梅调用。用户使用构建好的组件不需要安装 Node.js。`npm start` 用于开发预览；直接启动打包组件会返回梅梅。

仓库包含角色绘制素材、台词、生成脚本和音频映射，不包含模型权重、原始音色参考、生成 WAV、依赖目录或打包产物。自动问候36条和点击互动18条音频，需要先配置并启动梅梅 TTS，再在已配置梅梅依赖的 Python 环境中执行：

```powershell
npm run prepare:voices
npm run package
```

生成文件位于 `assets/voice/audio-final` 与 `assets/interaction-voice/audio-final`，对应映射记录文本及 SHA256。声音由本机合成，不是官方录音；实际音质需要试听。

## 绘制与验证

这是二维骨骼蒙皮与分层手臂系统。身体采用28个层级骨骼，头颈关节仅旋转；手臂以三维定长 IK 求解后投影，腕角有限制。绘制、拾取、道具接触和窗口范围共用动作数据。虹膜、眼睑和原画纹理由同一角色素材绑定；表情与眨眼使用连续参数。

- `npm test`：状态、快捷键、输入边界、骨骼、动作、窗口策略与语音队列回归。
- `npm run test:smoke`：真实原生窗口与设置检查。
- `node scripts/settings-window-check.cjs`：设置交互、三个动作入口与青蓝映射配色。
- `node scripts/audit-human-motion.mjs`：保留动作和中断过程中的可达性、骨长与掌向连续性。
- `node scripts/meimei-human-actions-check.cjs`：实际 GPU 握持接触、遮挡与头部跟随。
- `node scripts/meimei-action-check.cjs --record`：六种动作切换、窗口覆盖和连续动作视频。
- 应用 Python 运行 `../scripts/check_pet_mode.py`：内置启停、大小保存、设置置顶、共享聊天和退出清理。
- `npm run test:integration`：调用本机聊天、ASR 与 TTS，需要相应服务在线。

检查产物在 `artifacts`，不提交到仓库。自动检查不代替动作自然度或声音听感验收。其他较早的素材检查脚本可能保留历史姿态假设，当前动作验证以以上脚本为准。

## 来源

桌面窗口、输入交互和部分渲染框架参考 [ActorF/Elysia_desktop_pet](https://github.com/ActorF/Elysia_desktop_pet)，保留 MIT 许可与署名。未使用其角色图片或音频。阮梅形象按用户提供的角色参考制作，相关角色权利归原权利人；这是非官方个人项目。详见 [THIRD_PARTY.md](THIRD_PARTY.md)。
