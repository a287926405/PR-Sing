# PR-Sing

轻量级 sing-box 透明代理面板，面向路由器 / 旁路由场景。
Python3 单服务端 + 原生 Web 面板 + sing-box v1.14 内核，无其他运行时依赖。

- 功能参考 SMBox / Open-Box 的同类产品形态，**代码为完全独立实现（MIT 开源）**
- 链式代理基于 sing-box v1.14 原生 outbound `detour` 实现

## 功能

| 模块 | 说明 |
|---|---|
| 节点 | 解析 vless / vmess / trojan / ss / hy2 / tuic / naive / socks / http 分享链接；手动编辑 outbound JSON；延迟测速（sing-box 无 Snell 出站，不支持 snell 链接） |
| 订阅 | 添加订阅 URL，一键拉取/全量更新，自动去重 |
| 链式代理 | 给出口节点指定前置节点（1 个或多个），流量依次经过 前置1 → 前置2 → … → 出口；链对外作为一个整体节点，可加入节点组、被自定义规则引用 |
| 节点组 | selector（手动）与 urltest（自动测速切换）两种组类型 |
| 分流 | 全局 / 代理（默认国内直连）/ 自定义模式；内置规则 + 自定义规则（domain / 后缀 / 关键词 / IP 段 / geoip / 端口 / 协议，其中 geoip 规则基于 geoip-&lt;国家&gt; rule-set，需对应 .srs 已下载，cn 为内置）；rule-set（.srs）驱动的中国域名库；可选广告拦截 |
| DNS | FakeIP / 常规模式；本地与海外（经代理）DNS 分离解析 |
| 内核管理 | 启动 / 停止 / 重启 / 配置校验 / 日志查看 / 链出口 IP 测试 |

## 快速开始

```bash
git clone https://github.com/a287926405/PR-Sing.git
cd PR-Sing
./install.sh            # 安装代码 + 下载 sing-box v1.14.3 内核 + 注册服务
```

安装后访问 `http://<设备IP>:3001`，默认密码 `pr-sing`（登录后请立即修改）。

> 要求：Linux（含 OpenWrt/iStoreOS 等路由系统）、python3、可访问 GitHub 下载内核。
> 不依赖 systemd 的环境（多数路由器）会自动改用 `/usr/local/bin/pr-sing-start` 启动。

### 不使用安装脚本

```bash
export PRSING_HOME=/path/to/data      # 数据目录（配置/节点/内核/日志）
python3 run.py --listen 0.0.0.0 --port 3001
```

手动下载内核放到 `$PRSING_HOME/bin/sing-box` 即可（`run.py` 启动时也会自检并提示）。

## 链式代理

面板「链式代理」页：按顺序点选 ≥2 个节点，**点选顺序即流量顺序，最后一个节点是出口**。

底层生成的 sing-box 结构（v1.14 语义）：

```
outbound pr-c-<id>-h1  (前置1 的 outbound 副本)
outbound pr-c-<id>-h2  (前置2, detour → pr-c-<id>-h1)
outbound pr-c-<id>-hN  (出口,  detour → pr-c-<id>-hN-1)   ← 对外 tag
```

每个 hop 复制对应节点的完整 outbound 配置，`detour` 指向上游 hop 的 tag。
链创建后可：加入 selector/urltest 组、被自定义分流规则按名称引用、在「状态」页做出口 IP 测试。

## 目录结构

```
PRSING_HOME/
├── config/            # settings.json / nodes.json / chains.json / groups.json /
│                      # subscriptions.json / sing-box.generated.json
├── data/
│   └── rule-sets/     # *.srs（中国域名/私有域/广告/中国IP段）
├── bin/sing-box       # 内核
└── logs/              # sing-box.log / prsing.log
```

## 安全

- 面板默认 `0.0.0.0:3001` 监听，**公网暴露前必须修改密码**，并建议将 `panel_listen` 改为 `127.0.0.1` 走 SSH 隧道
- 密码以 salt+SHA256 存储，会话 token 为 HMAC 签名（30 天有效）
- 所有面板 API 需 Bearer token

## 许可

MIT。本项目与 SMBox、Open-Box 无代码关系；功能形态受同类产品启发，所有代码为独立编写。

## 已知限制

- 节点组仅 selector / urltest（sing-box v1.14 无 fallback 组类型）
- 链的成员必须是已启用节点；节点被删除/禁用后对应链自动失效
- TUN 需要 root 权限（路由器场景默认满足）
