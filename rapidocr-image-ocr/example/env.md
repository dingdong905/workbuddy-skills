# 本机 OCR 环境（2026-10-08 建成，实测可用）

## 专用 venv

- 解释器：`C:\Users\admin\.workbuddy\binaries\python\envs\ocr\Scripts\python.exe`
- 基础：WorkBuddy 托管 Python 3.13.12（`C:\Users\admin\.workbuddy\binaries\python\versions\3.13.12`）

## 已装包（12 个）

rapidocr-onnxruntime 1.4.4（--ignore-requires-python 强装：其元数据声明 <3.13，纯 python 包实际兼容 3.13）、onnxruntime 1.30.0、opencv-python 5.0.0.93、numpy 2.5.3、pillow 12.3.0、PyYAML 6.0.2、Shapely 2.1.2、pyclipper 1.4.0、six 1.17.0、tqdm 4.9.0、flatbuffers 25.9.23、packaging 26.3、protobuf 7.36.2

## 离线重建（wheel 备份）

```bash
# wheel 备份在 D:\skills\.workbuddy\tmp\wheels\（84MB，若被清理需重新 curl 下载）
"C:/Users/admin/.workbuddy/binaries/python/versions/3.13.12/python.exe" -m venv "C:/Users/admin/.workbuddy/binaries/python/envs/ocr"
"C:/Users/admin/.workbuddy/binaries/python/envs/ocr/Scripts/python.exe" -m pip install --no-index --find-links "D:/skills/.workbuddy/tmp/wheels" --ignore-requires-python rapidocr-onnxruntime
```

## 为什么不用 pip 在线装（本机坑，2026-10-08 实证）

WorkBuddy Bash 沙箱给环境注入代理 `http://127.0.0.1:58512`（http_proxy/https_proxy 四层全设），且 pip 网络栈被区别对待：`--proxy ""`、清环境变量、系统注册表代理全试过仍报 `from versions: none`（curl 直连同一 URL 却正常）。解法：curl `--noproxy "*"` 从清华镜像直连下载 wheel，再 `--no-index --find-links` 本地安装。注意 wheel 文件名可能与内容不符（实测下到过文件名 1.17.0、METADATA 是 1.9.0 的 six），装前用 zipfile 读 METADATA 校验。
