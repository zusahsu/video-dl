# Video-DL

基于 yt-dlp 的 Windows 桌面视频下载工具，支持 Bilibili、YouTube 等站点。打包为单个 exe，无需安装任何依赖。

## 特性

- 图形界面（tkinter），中文友好
- 抓取所有可用格式，树形展示分辨率、编码、大小、码率
- 自动检测 HEVC/AV1/VP9 编码并使用 ffmpeg 转码为 H.264（Windows 原生可播放）
- 启动时检测 ffmpeg，未安装可一键自动下载（支持 GitHub / ghproxy 镜像）
- 无 ffmpeg 时自动切换受限模式，只展示可直接播放的格式
- 支持 cookies.txt（Bilibili 大会员 / YouTube 会员）
- 支持字幕下载与嵌入
- 支持代理（HTTP/SOCKS5）
- 支持播放列表下载

## 下载

从 [Releases](../../releases) 页面下载最新 `video-dl.exe`（约 25MB），双击运行即可。

## 自行构建

```bash
pip install yt-dlp pyinstaller
pyinstaller video-dl.spec -y
```

输出在 `dist/video-dl.exe`。

## 使用说明

1. 粘贴视频 URL，点击 **Fetch Formats**
2. 从列表中选择格式，点击 **Download**
3. 输出默认保存到 `Downloads` 文件夹

### ffmpeg

首次启动时如未检测到 ffmpeg，程序会询问是否自动下载（~50MB）。选择"是"则自动从 GitHub 或国内镜像下载并缓存到 exe 同目录；选择"否"则进入受限模式，仅列出无需转码的预合并 H.264 格式。

也可手动安装 ffmpeg：

```bash
choco install ffmpeg-full
```

### Cookies

将 Netscape 格式的 `cookies.txt` 放在 `video-dl.exe` 同目录下，程序会自动检测。也可在界面中手动选择路径。

## 技术要点

- **格式串**: `{id}+bestaudio[ext=m4a]/best[ext=mp4]/best` — 始终合并最佳音轨
- **转码**: HEVC/AV1/VP9 通过 ffmpeg libx264 重编码，CRF 23，preset fast
- **线程模型**: 所有 yt-dlp 操作在后台线程，UI 更新通过消息队列投递到主线程
- **打包**: PyInstaller `--windowed`，无控制台窗口

## 免责声明

**本软件仅供学习、研究与个人使用，严禁用于任何商业用途，严禁用于任何盈利性活动。**

- 使用者应遵守目标网站的服务条款及相关法律法规，尊重版权，不得下载、传播侵权内容。
- 因使用本软件产生的任何法律责任，由使用者自行承担，开发者不承担任何连带责任。
- 商业用途包括但不限于：以本软件为基础提供付费服务、将本软件集成至商业产品、利用本软件下载内容用于盈利。

If you use this software for commercial purposes, you are solely responsible for any legal consequences.

## License

MIT
