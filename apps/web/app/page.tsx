'use client';

import { useEffect, useState } from 'react';

const nav = [
  ['overview', '运行总览', '◈'],
  ['twin', '数字孪生', '◇'],
  ['alerts', '告警中心', '!'],
  ['orders', '工单中心', '✓'],
  ['assets', '设备台账', '▦'],
  ['insights', '数据洞察', '⌁'],
  ['audit', '审计追踪', '≡'],
  ['settings', '系统配置', '⚙'],
];

const labels: Record<string, string> = Object.fromEntries(nav.map(([id, label]) => [id, label]));
const metrics = [
  ['在线设备', '18', '/ 20', '90%', 'blue'],
  ['环境健康度', '96.8', '%', '+1.2%', 'mint'],
  ['待处置事件', '03', '项', '需关注', 'amber'],
  ['指令成功率', '99.4', '%', '24h', 'violet'],
];
const logs = [
  ['10:24:08', 'UT-ZB 湿度读数恢复稳定', 'HUM-02 · 67.2 %RH', 'good'],
  ['10:22:31', '生成巡检工单 WO-260826-08', '资产：FAN-01 · 优先级：普通', 'blue'],
  ['10:18:44', 'SEEP-W01 触发预警阈值', '待告警中心确认 · 水浸趋势上升', 'warn'],
  ['10:06:12', '控制器 CTRL-01 心跳正常', 'MQTT QoS 1 · 延迟 132 ms', 'good'],
];
const bars = [36, 43, 39, 54, 49, 62, 58, 72, 66, 75, 70, 84, 78, 69, 74, 64, 70, 56];

type ModuleProps = { active: string; go: (id: string) => void; notify: (text: string) => void };

function ModuleView({ active, go, notify }: ModuleProps) {
  const heading: Record<string, [string, string, string]> = {
    twin: ['DIGITAL TWIN', '数字孪生', '以空间为入口查看资产、区域与运行状态。'],
    alerts: ['ALERT MANAGEMENT', '告警中心', '仅处理异常事件的确认、升级、合并与关闭。'],
    orders: ['WORK ORDER FLOW', '工单中心', '以任务为单位组织派发、处置、复核与归档。'],
    assets: ['ASSET REGISTRY', '设备台账', '维护设备的身份、位置、能力和生命周期信息。'],
    insights: ['DATA INSIGHTS', '数据洞察', '面向历史数据的趋势、对比和运行统计。'],
    audit: ['AUDIT TRAIL', '审计追踪', '不可篡改地回看每一次关键业务与系统操作。'],
    settings: ['SYSTEM CONFIG', '系统配置', '集中维护规则、映射、角色和演示数据源。'],
  };
  const meta = heading[active];
  const Header = ({ action, onAction }: { action?: string; onAction?: () => void }) => <section className="module-hero"><div><small>{meta[0]}</small><h1>{meta[1]}</h1><p>{meta[2]}</p></div>{action && <button className="primary" onClick={onAction}>{action}</button>}</section>;

  if (active === 'twin') return <section className="module-page">
    <Header action="重置视角" onAction={() => notify('已回到管廊全景视角')} />
    <div className="twin-layout">
      <article className="twin-stage"><div className="stage-toolbar"><button className="active">全景</button><button>UT-ZA</button><button>UT-ZB</button><button>UT-ZC</button><span>⌘ 拖动旋转 · 滚轮缩放</span></div><div className="twin-map"><i className="lane l1" /><i className="lane l2" /><i className="lane l3" /><i className="pipe-line pl1" /><i className="pipe-line pl2" /><i className="map-tag t1">FAN-01</i><i className="map-tag watch t2">SEEP-W01</i><i className="map-tag t3">GAS-01</i><div className="map-compass">N<br /><b>⌃</b></div></div><div className="stage-foot"><span><i className="good-dot" />运行正常</span><span><i className="watch-dot" />关注点 1</span><span>模型 V0.1 · 演示数据</span></div></article>
      <aside className="inspector"><small>SELECTED ASSET</small><div className="asset-orb">F</div><h2>FAN-01</h2><p>UT-ZB · 通风设备</p><div className="inspector-state"><i />运行中 <span>1,248 rpm</span></div><dl><div><dt>供电状态</dt><dd>正常</dd></div><div><dt>最近心跳</dt><dd>10:26:12</dd></div><div><dt>映射网格</dt><dd>MESH_FAN_01</dd></div></dl><button className="outline" onClick={() => go('assets')}>查看设备台账　→</button></aside>
    </div>
  </section>;

  if (active === 'alerts') return <section className="module-page">
    <Header action="创建演示告警" onAction={() => notify('已创建一条模拟预警事件')} />
    <div className="alert-summary"><article><i className="critical" /> <b>01</b><span>紧急告警</span></article><article><i className="warning" /> <b>02</b><span>待确认预警</span></article><article><i className="closed" /> <b>14</b><span>今日已关闭</span></article><div><span>筛选范围</span><button>全部区域⌄</button><button>最近 24 小时⌄</button></div></div>
    <article className="card table-card"><div className="table-head"><span>事件</span><span>位置 / 资产</span><span>触发时间</span><span>状态</span><span>处置</span></div>{[['ALM-260826-003', '水浸趋势异常', 'UT-ZB / SEEP-W01', '10:18:44', '待确认', 'warning'], ['ALM-260826-002', '风机反馈丢失', 'UT-ZA / FAN-01', '09:42:18', '处理中', 'critical'], ['ALM-260826-001', '通信瞬断恢复', 'UT-ZC / CTRL-02', '08:25:31', '已恢复', 'closed']].map((row) => <div className="alert-row" key={row[0]}><div><b>{row[0]}</b><small>{row[1]}</small></div><span>{row[2]}</span><time>{row[3]}</time><em className={row[5]}>{row[4]}</em><button className="row-action" onClick={() => notify(row[0] + ' 已完成事件确认')}>确认</button></div>)}</article>
  </section>;

  if (active === 'orders') return <section className="module-page">
    <Header action="新建工单" onAction={() => notify('工单编辑面板已准备就绪')} />
    <div className="kanban"><article><div className="kanban-head"><span>待派发</span><b>02</b></div><div className="ticket high"><small>WO-260826-08 · 巡检</small><h3>检查 UT-ZB 接水盘与水位探针</h3><p>关联资产　SEEP-W01</p><footer><span>今天 14:00</span><i>未分配</i></footer></div><div className="ticket"><small>WO-260826-09 · 维护</small><h3>核验风机转速反馈接线</h3><p>关联资产　FAN-01</p><footer><span>今天 16:00</span><i>未分配</i></footer></div></article><article><div className="kanban-head"><span>处理中</span><b>01</b></div><div className="ticket active-ticket"><small>WO-260826-06 · 处置</small><h3>复核湿度预警与现场状态</h3><p>执行人　运维组 A</p><footer><span>进行中</span><i>60%</i></footer></div></article><article><div className="kanban-head"><span>待复核</span><b>01</b></div><div className="ticket review"><small>WO-260826-04 · 检修</small><h3>CTRL-02 通信恢复确认</h3><p>提交于　09:48</p><footer><span>等待复核</span><i>胡雨皓</i></footer></div></article><article><div className="kanban-done"><span>今日闭环</span><b>09</b><p>平均处置时长<br /><strong>18 分钟</strong></p></div></article></div>
  </section>;

  if (active === 'assets') return <section className="module-page">
    <Header action="登记资产" onAction={() => notify('资产登记表单已准备就绪')} />
    <div className="asset-filters"><div className="search">⌕ <span>搜索资产编码、名称或位置</span></div><button>全部区域⌄</button><button>全部状态⌄</button><span>共 20 项资产</span></div>
    <article className="card table-card asset-table"><div className="table-head"><span>资产</span><span>区域</span><span>类型</span><span>运行状态</span><span>最后更新</span></div>{[['FAN-01', '送风机 #01', 'UT-ZB', '执行器', '运行中', 'good'], ['SEEP-W01', '渗水监测点', 'UT-ZB', '测点', '预警', 'warning'], ['GAS-01', '甲烷监测节点', 'UT-ZC', '测点', '正常', 'good'], ['CTRL-01', '现场控制器', 'UT-ZA', '控制器', '在线', 'blue']].map((row) => <div className="asset-row" key={row[0]}><div className="asset-cell"><i>{row[0].slice(0, 1)}</i><span><b>{row[0]}</b><small>{row[1]}</small></span></div><span>{row[2]}</span><span>{row[3]}</span><em className={row[5]}>{row[4]}</em><time>刚刚</time></div>)}</article>
  </section>;

  if (active === 'insights') return <section className="module-page">
    <Header action="导出演示报表" onAction={() => notify('报表导出已加入本地下载队列')} />
    <div className="insight-grid"><article className="card line-chart"><div className="card-head"><div><small>TELEMETRY TREND</small><h2>UT-ZB 环境温湿度</h2></div><button>最近 6 小时⌄</button></div><div className="line-area"><i /><i /><i /><i /><b /><em /></div><div className="chart-axis"><span>04:00</span><span>06:00</span><span>08:00</span><span>10:00</span></div></article><article className="card composition"><small>EVENT COMPOSITION</small><h2>今日事件构成</h2><div className="donut"><b>17<small>事件</small></b></div><p><i />设备 53%　<i />环境 29%　<i />通信 18%</p></article></div>
    <section className="metrics insight-metrics"><article className="metric blue"><div><span>遥测完整率</span><i>↗</i></div><b>99.1<small>%</small></b><p>+0.6%<span> 相较昨日</span></p></article><article className="metric mint"><div><span>平均响应</span><i>↗</i></div><b>1.4<small>s</small></b><p>达标<span> P95 ≤ 2s</span></p></article><article className="metric violet"><div><span>告警闭环率</span><i>↗</i></div><b>94<small>%</small></b><p>+8%<span> 本周</span></p></article></section>
  </section>;

  if (active === 'audit') return <section className="module-page">
    <Header />
    <div className="audit-filter"><button className="selected-filter">全部操作</button><button>控制命令</button><button>告警流转</button><button>配置变更</button><button>登录与会话</button><span>⌕ 检索审计记录</span></div>
    <article className="card audit-card">{[['10:24:08', '系统', '遥测状态更新', 'HUM-02 数值由 68.1 %RH 更新为 67.2 %RH', 'data'], ['10:22:31', '王露帆', '创建工单', '创建 WO-260826-08，关联 SEEP-W01', 'order'], ['10:18:56', '值班员', '确认预警', '确认 ALM-260826-003，填写初步处置说明', 'alert'], ['10:06:12', 'CTRL-01', '设备心跳', '在线状态保持，固件 0.1.0', 'data']].map((row) => <div className="audit-row" key={row[0]}><time>{row[0]}</time><i className={row[4]}>{row[1].slice(0, 1)}</i><div><b>{row[2]} <small>· {row[1]}</small></b><p>{row[3]}</p></div><button onClick={() => notify('该条审计记录已锁定展示')}>查看</button></div>)}</article>
  </section>;

  return <section className="module-page">
    <Header action="保存草稿" onAction={() => notify('配置草稿已保存到本地演示环境')} />
    <div className="settings-layout"><article className="card settings-nav"><b>规则与策略</b><button className="current">报警阈值</button><button>联动策略</button><button>数据质量</button><b>模型与权限</b><button>资产映射</button><button>角色权限</button></article><article className="card setting-form"><div className="card-head"><div><small>ALARM THRESHOLDS</small><h2>报警阈值</h2></div><span>版本 v0.1</span></div>{[['环境温度', '预警 28 °C', '报警 32 °C'], ['环境湿度', '预警 75 %RH', '报警 85 %RH'], ['水浸趋势', '持续 20 秒', '报警持续 45 秒']].map((item) => <div className="setting-row" key={item[0]}><b>{item[0]}</b><span>{item[1]}</span><span>{item[2]}</span><button onClick={() => notify(item[0] + ' 编辑模式已开启')}>编辑</button></div>)}</article></div>
  </section>;
}

export default function Home() {
  const [active, setActive] = useState('overview');
  const [now, setNow] = useState('');
  const [toast, setToast] = useState('');
  const notify = (text: string) => { setToast(text); window.setTimeout(() => setToast(''), 2600); };

  useEffect(() => {
    const tick = () => setNow(new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date()));
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return <main className="app">
    <aside className="side">
      <div className="brand"><span className="mark"><i /><i /><i /></span><span><b>UT / OPS</b><small>UTILITY TUNNEL</small></span></div>
      <nav>
        <p className="caption">运行工作台</p>
        {nav.slice(0, 4).map(([id, label, icon]) => <button key={id} className={'nav ' + (active === id ? 'selected' : '')} onClick={() => setActive(id)}><i>{icon}</i>{label}{id === 'alerts' && <em>3</em>}{id === 'orders' && <em>2</em>}</button>)}
        <p className="caption lower">资产与系统</p>
        {nav.slice(4).map(([id, label, icon]) => <button key={id} className={'nav ' + (active === id ? 'selected' : '')} onClick={() => setActive(id)}><i>{icon}</i>{label}</button>)}
      </nav>
      <div className="user"><span>WL</span><div><b>王露帆</b><small>软件工程师</small></div><button>···</button></div>
    </aside>
    <section className="work">
      <header><div className="crumb">综合管廊 <i>/</i> <b>{labels[active]}</b></div><div className="top-actions"><span className="env"><i />演示环境</span><button className="bell" onClick={() => notify('目前有 3 项待处置告警')}>♧<b>3</b></button><span className="face">WL</span></div></header>
      <div className="page">
        {active === 'overview' ? <>
        <section className="hero"><div><small>CONTROL ROOM · {now}</small><h1>运行，一眼掌握</h1><p>全域设备与环境状态的实时概览。处置操作请进入对应业务模块。</p></div><button className="primary" onClick={() => notify('已生成今日运行快照')}><i>＋</i>生成运行快照</button></section>
        <section className="metrics">{metrics.map(([label, value, suffix, delta, tone]) => <article className={'metric ' + tone} key={label}><div><span>{label}</span><i>↗</i></div><b>{value}<small>{suffix}</small></b><p>{delta}<span> 相较上一统计周期</span></p></article>)}</section>
        <section className="two">
          <article className="card tunnel-card"><div className="card-head"><div><small>TWIN PULSE</small><h2>管廊实时态势</h2></div><button onClick={() => setActive('twin')}>进入孪生视图　<span>→</span></button></div><div className="tunnel"><div className="grid" /><i className="arch a1" /><i className="arch a2" /><i className="arch a3" /><i className="pipe p1" /><i className="pipe p2" /><i className="pipe p3" /><b className="node n1">CTRL-01</b><b className="node watch n2">SEEP-W01</b><b className="node n3">FAN-01</b><div className="legend"><span><i />正常 16</span><span><i />预警 1</span><span><i />离线 2</span></div></div></article>
          <article className="card signal"><div className="card-head"><div><small>LIVE SIGNAL</small><h2>环境信号</h2></div><span className="live">实时</span></div><div className="temp"><b>24.8</b><span>°C</span><small>UT-ZB · 环境温度</small></div><div className="bars">{bars.map((height, index) => <i key={index} className={index > 11 ? 'new' : ''} style={{ height: height + '%' }} />)}</div><div className="range"><span>10:00</span><b>稳定区间 22–27°C</b><span>当前</span></div></article>
        </section>
        <section className="two bottom">
          <article className="card stream"><div className="card-head"><div><small>ACTIVITY STREAM</small><h2>最新运行动态</h2></div><button onClick={() => setActive('audit')}>审计追踪　<span>→</span></button></div><div className="log-list">{logs.map(([time, title, detail, tone]) => <div className="log" key={time}><i className={tone} /><time>{time}</time><div><b>{title}</b><p>{detail}</p></div></div>)}</div></article>
          <article className="readiness"><small>SYSTEM READINESS</small><h2>演示就绪度</h2><div><b>86</b><span>/ 100</span></div><i className="progress"><em /></i><p>软件模拟链路正常，等待硬件数据源接入。</p><button onClick={() => notify('检查清单已准备完成')}>查看就绪清单　<span>→</span></button></article>
        </section>
        </> : <ModuleView active={active} go={setActive} notify={notify} />}
      </div>
    </section>
    {toast && <div className="toast">{toast}</div>}
  </main>;
}
