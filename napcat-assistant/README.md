# NapCat 群聊助手

独立 Python 服务：监听 NapCat 上报的所有群消息，只处理明确 @机器人自身的指令。
与上层 B 站机器人不共享代码、进程、凭证文件或数据库；本目录包含单独的 Docker 构建与 Compose 配置。

## 当前指令

去掉消息中的 @消息段，拼接文字并去除开头空白后，前两个字为 `周表` 就向原群发送一张图片。

| 消息 | 行为 |
| --- | --- |
| `@机器人 周表` | 发送图片 |
| `@机器人 周表看看` | 发送图片 |
| `周表 @机器人` | 发送图片 |
| `@机器人 看看周表` | 忽略 |
| `周表`、`@其他人 周表`、`@全体成员 周表` | 忽略 |

所有群使用同一张图片，无需配置群白名单。忽略私聊、机器人自己的消息、心跳等事件。
图片文件名必须为 `YYYYMMDD-YYYYMMDD.扩展名`，例如 `20261013-20261020.png`。
按北京时间判断当天是否落在范围内，包含起止日；这是文件名校验，不识别图片上的文字。
支持 PNG、JPG、JPEG、WebP、GIF（扩展名不区分大小写）。格式错误、无效日期、过期、尚未生效、
没有图片或选中的图片为空时，回复“未发现本周周表”。多张图片同时有效时，优先开始日期最新的，
再按结束日期和文件名字典序取最大值。日期格式及时区规则固定在 `commands.py` 中。
默认同群同指令有 5 秒冷却，可通过 `COMMAND_COOLDOWN_SECONDS=0` 关闭。
最近 4096 条已处理指令的消息 ID 保存在内存中去重，重连保留，进程重启清空。
不会保存群聊正文，也不会在日志打印账号 Token、群聊正文或图片内容。

## 在 tt 上部署

当前 NapCat 位于独立 Compose 网络 `napcat_default`。本服务加入该网络，通过
`napcat:3000` 和 `napcat:3001` 访问 NapCat，不需要发布新端口。

1. 在 NapCat WebUI 的网络配置中新增 **WebSocket 服务端（正向 WS）**：
   - 启用，监听地址 `0.0.0.0`，端口 `3001`。
   - 消息格式 `array`，关闭自身消息上报。
   - 设置 Token；现有 HTTP 服务保持开启。
   - 按 WebUI 提示使配置生效。
2. 将本目录放到 `/root/bilibili-gachi-bot/napcat-assistant`，进入该目录：

   ```sh
   cp .env.sample .env
   ```

   填入 HTTP 的 `NAPCAT_API_TOKEN`。若 WS Token 不同，另填 `NAPCAT_WS_TOKEN`。
   本服务不会自动读取上层项目 `.env`。
3. 将真实周表图片按日期范围命名后放入 `data/`，例如 `data/20261013-20261020.png`。
   `WEEKLY_IMAGE_DIR=/data` 指定扫描目录，程序每次请求自动选择当前有效的图片。
   旧配置 `WEEKLY_IMAGE_PATH` 已替换为 `WEEKLY_IMAGE_DIR`。
4. 在本目录启动：

   ```sh
   docker compose -f compose.yaml up -d --build
   docker compose -f compose.yaml logs --tail=50 -f assistant
   ```

   看到 `Connected to NapCat` 后，在群中发送 `@机器人 周表`，确认收到图片。
   图片未放入或文件为空时服务仍可连接，触发指令会回复“未发现本周周表”。

更新周表只需在 `data/` 放入对应日期范围命名的图片，每次触发都会重新扫描、读取。建议先上传临时文件再重命名替换，
避免读取到上传中的半张图片。挂载的是目录，不需要重启容器。

停止本服务：`docker compose -f compose.yaml down`。不会停止原机器人或 NapCat。

### tt 的 systemd 管理方式

与现有 NapCat、gachi 保持一致，由 systemd 前台运行 Compose，使容器日志进入 journal。
安装本目录的 `napcat-assistant.service` 到 `/etc/systemd/system/`，先执行
`docker compose -f compose.yaml build`，再执行 `systemctl daemon-reload` 和
`systemctl enable --now napcat-assistant`。使用 systemd 后通过
`systemctl stop/start/restart napcat-assistant` 管理，不要同时另起一个手工监听进程。

日志：`journalctl -u napcat-assistant -f`。
现有 `/root/scripts/check-server.sh` 的服务白名单需加入 `napcat-assistant`，并在 root crontab 添加：

```cron
*/5 * * * * /bin/bash /root/scripts/check-server.sh napcat-assistant
```

该脚本沿用现有日志告警机制，不是主动发送 QQ 测试消息。发送失败与 WebSocket 断连会记录 ERROR。
正常缺少本周周表属于业务回复，不作为服务异常告警。

## 开发与扩展

`main.py` 负责连接、重连、去重、冷却及调用发送 API；`commands.py` 负责指令匹配和消息构建。
在 `COMMANDS` 注册新的前缀和处理函数即可扩展；有重叠前缀时将更具体的前缀排在前面。
无需引入 AI 或机器人框架。

本地测试（在本目录运行）：

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m unittest -v
```

测试使用本机模拟 WebSocket 和 HTTP，不连接真实 QQ，不发送真实群消息。
本地直接启动时需自行导出环境变量，并将 NapCat 地址和图片目录改为本机可访问的值；
`python main.py` 不会自动加载 `.env`，Docker Compose 会加载。

发送成功同时检查 HTTP 状态和 OneBot `status=ok`、`retcode=0`。
发送失败只记录日志，不盲目重发（超时不代表 QQ 没收到），用户可再次发指令。
WebSocket 断线后每 5 秒重连；断线期间未收到的群消息不会补抓。

协议参考：[NapCat 网络配置](https://napneko.github.io/config/basic)、
[NapCat 消息段](https://napneko.github.io/develop/msg)。
