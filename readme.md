# KTV Control  (KTV 前台控制系统)

KTV 包厢前台管理系统，基于 FastAPI 构建，实现房间开台/关台、会员管理、套餐计费、酒水管理、结账等功能。

## 功能概览

- **房间管理** — 查看房间通电状态，开台/关台/续时，自动倒计时显示
- **包厢预订** — 预约开台时间，到时自动开台
- **会员管理** — 新增/编辑会员，充值，密码管理
- **套餐管理** — 开台/续时套餐，统一零售价
- **库存管理** — 简单库存和消费记录
- **店内人员管理** — 维护姓名、手机号、岗位和在职状态（不参与登录权限）
- **收银记账** — 收银台、结账记录，以及营业报表菜单占位
- **结账** — 自动计费、折扣优惠，支持现金、微信、支付宝和会员余额
- **操作日志** — 所有操作记录可查

## 技术栈

| 层面 | 技术 |
|------|------|
| 后端 | Python 3.12, FastAPI, uvicorn |
| 数据库 | SQLite (WAL 模式) |
| 前端 | 原生 HTML/CSS/JS，单页面应用 |
| 外部对接 | KTV 硬件 API (HTTP) |

## 项目结构

```text
KTVControl/
  main.py           # FastAPI 应用，所有 API 路由
  models.py         # Pydantic 请求模型
  database.py       # SQLite 初始化、连接、迁移、日志
  scheduler.py      # 设备指令、失败重试、定时关台、预订调度
  state_manager.py  # SQLite 预订与定时状态管理、房间 IP 缓存
  requirements.txt  # Python 依赖
  data/             # 运行时数据 (ktv.db, config.json, room_ip_map.json)
  static/
    index.html      # 前端页面
    app.js          # 前端逻辑
    style.css       # 样式表
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. 访问界面

浏览器打开 http://localhost:8000

## 配置

默认管理密码为 admin123，可在 data/config.json 中修改。

KTV 硬件 API 地址在 scheduler.py 中配置：

`python
KTV_API_BASE = "http://192.168.110.201:18888"
`

## API 接口

### 房间管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/rooms | 获取所有房间列表 |
| GET | /api/rooms/status | 房间通电状态 |
| POST | /api/rooms/open | 开台 |
| POST | /api/rooms/close | 关台 |
| POST | /api/rooms/extend | 续时 |

### 预订
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/bookings | 预订列表 |
| POST | /api/bookings | 创建预订 |
| DELETE | /api/bookings/{id} | 取消预订 |

### 会员
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/members | 会员列表 |
| POST | /api/members | 新增会员 |
| PUT | /api/members/{id} | 编辑会员 |
| POST | /api/members/verify | 验证会员 |
| POST | /api/members/{id}/recharge | 充值 |
| POST | /api/members/{id}/reset-password | 重置密码 |

### 套餐 & 库存
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /api/packages | 套餐列表/新增 |
| PUT/DELETE | /api/packages/{id} | 编辑/删除套餐 |
| GET/POST | /api/inventory | 库存列表/新增 |
| PUT/DELETE | /api/inventory/{id} | 编辑/删除库存 |


### 店内人员
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /api/staff | 人员列表/新增 |
| PUT/DELETE | /api/staff/{id} | 编辑/删除人员 |
### 结账
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/billing/active | 当前开台账单 |
| POST | /api/billing/add-drink | 添加酒水 |
| DELETE | /api/billing/drink/{id} | 删除酒水明细 |
| POST | /api/billing/settle | 结账 |
| GET | /api/billing/history | 结账历史 |
| DELETE | /api/billing/{id} | 删除账单 |

### 其他
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/operation-logs | 操作日志 |
| POST | /api/admin/verify | 验证管理密码 |

## 数据库表结构

| 表名 | 说明 |
|------|------|
| members | 会员信息（姓名、手机、密码、余额） |
| recharge_logs | 充值记录 |
| packages | 套餐（名称、时长、零售价） |
| inventory | 酒水库存（类别、名称、单价、库存） |
| billing_records | 账单（房间、套餐、时长、费用、状态） |
| drink_orders | 酒水消费明细 |
| operation_logs | 操作日志 |
| auto_close_schedules | 定时关台任务 |
| bookings | 包厢预订 |
| device_commands | 设备指令、执行状态和失败信息 |
| staff | 店内人员资料 |

数据库文件位于 data/ktv.db，启动时自动创建并迁移。

预订、定时关台和设备指令均保存在 SQLite；data/room_ip_map.json 只缓存房间 IP 映射。旧版 data/state.json 会在启动时自动迁移并删除。

## 会员与套餐计价

所有会员统一管理；套餐仅使用 price_normal 一个零售价字段计费。

新建会员默认密码为手机号后 4 位。

## 结账逻辑

1. 选择套餐计算房间费
2. 酒水费自动汇总
3. 最高支持 20% 折扣优惠
4. 支持现金、微信、支付宝、会员余额支付
5. 不支持混合支付；会员余额不足时需先充值或改用其他支付方式


## 权限说明

当前为单店默认管理账号模式，不区分员工角色和权限；店内人员资料不作为登录账号。
