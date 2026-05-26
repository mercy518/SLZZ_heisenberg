"""
漫威争锋 · 燃系列赛 BP 模拟器
启动: streamlit run bp_simulator.py
"""

import streamlit as st
import sqlite3, os, random

DB = os.path.join(os.path.dirname(__file__), "scrims.db")

# ── 自动初始化数据库 ──
def auto_init_db():
    if os.path.exists(DB):
        return
    conn = sqlite3.connect(DB)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, tag TEXT, is_our_team INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS players (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, team_id INTEGER REFERENCES teams(id), role TEXT, UNIQUE(name, team_id));
        CREATE TABLE IF NOT EXISTS heroes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, role TEXT NOT NULL, UNIQUE(name, role));
        CREATE TABLE IF NOT EXISTS maps (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, mode TEXT);
        CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, match_date DATE NOT NULL, opponent_id INTEGER REFERENCES teams(id), format TEXT NOT NULL DEFAULT 'BO5', notes TEXT);
        CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER REFERENCES matches(id), game_number INTEGER NOT NULL, map_id INTEGER REFERENCES maps(id), side TEXT, our_score INTEGER, opponent_score INTEGER, result TEXT, notes TEXT, UNIQUE(match_id, game_number));
        CREATE TABLE IF NOT EXISTS bp_actions (id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER REFERENCES games(id), team_side TEXT NOT NULL, bp_step INTEGER NOT NULL, bp_type TEXT NOT NULL DEFAULT 'ban', hero_id INTEGER REFERENCES heroes(id), UNIQUE(game_id, bp_step, team_side));
        CREATE TABLE IF NOT EXISTS picks (id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER REFERENCES games(id), team_side TEXT NOT NULL, player_id INTEGER REFERENCES players(id), hero_id INTEGER REFERENCES heroes(id), UNIQUE(game_id, team_side, player_id));
        CREATE TABLE IF NOT EXISTS player_stats (id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER REFERENCES games(id), player_id INTEGER REFERENCES players(id), hero_id INTEGER REFERENCES heroes(id), kills INTEGER DEFAULT 0, deaths INTEGER DEFAULT 0, assists INTEGER DEFAULT 0, damage INTEGER DEFAULT 0, healing INTEGER DEFAULT 0, damage_blocked INTEGER DEFAULT 0, eliminations INTEGER DEFAULT 0, final_hits INTEGER DEFAULT 0, ultimate_uses INTEGER DEFAULT 0, notes TEXT, UNIQUE(game_id, player_id));
        CREATE TABLE IF NOT EXISTS hero_swaps (id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER REFERENCES games(id), player_id INTEGER REFERENCES players(id), hero_id INTEGER REFERENCES heroes(id), swap_order INTEGER NOT NULL, UNIQUE(game_id, player_id, swap_order));
    """)
    heroes = [
        ("奇异博士","捍卫者"),("万磁王","捍卫者"),("浩克","捍卫者"),("格鲁特","捍卫者"),("雷神","捍卫者"),("毒液","捍卫者"),("潘妮·帕克","捍卫者"),("美国队长","捍卫者"),("石头人","捍卫者"),("死侍 (捍卫者)","捍卫者"),("恶魔恐龙","捍卫者"),("白皇后","捍卫者"),("安吉拉","捍卫者"),("小淘气","捍卫者"),
        ("黑豹","决斗"),("鹰眼","决斗"),("海拉","决斗"),("铁拳","决斗"),("钢铁侠","决斗"),("月光骑士","决斗"),("纳摩","决斗"),("灵蝶","决斗"),("惩罚者","决斗"),("猩红女巫","决斗"),("蜘蛛侠","决斗"),("松鼠女孩","决斗"),("星爵","决斗"),("暴风女","决斗"),("冬日战士","决斗"),("金刚狼","决斗"),("霹雳火","决斗"),("死侍 (决斗)","决斗"),("血石","决斗"),("黑猫","决斗"),("夜魔侠","决斗"),("刀锋战士","决斗"),("神奇先生","决斗"),("黑寡妇","决斗"),("凤凰女","决斗"),
        ("亚当术士","策略家"),("斗篷与匕首","策略家"),("隐形女","策略家"),("陆行鲨杰夫","策略家"),("洛基","策略家"),("螳螂女","策略家"),("火箭浣熊","策略家"),("死侍 (策略家)","策略家"),("冰月","策略家"),("奥创","策略家"),("牌皇","策略家"),("白狐","策略家"),
    ]
    maps = [
        ("黄金城","角逐"),("夏提厄冰山","角逐"),("克拉科","角逐"),("天神遗骸","角逐"),
        ("世界树","巡航"),("蜘蛛岛","巡航"),("中城区","巡航"),("阿拉寇","巡航"),("沉思藏馆","巡航"),
        ("新涩谷","融合"),("贾利亚神殿","融合"),("共生地表","融合"),("中央公园","融合"),("天都之心","融合"),("曼哈顿下城","融合"),
    ]
    conn.executemany("INSERT OR IGNORE INTO heroes (name, role) VALUES (?,?)", heroes)
    conn.executemany("INSERT OR IGNORE INTO maps (name, mode) VALUES (?,?)", maps)
    conn.commit()
    conn.close()

auto_init_db()

# ── 数据加载 ──
@st.cache_data
def load_data():
    conn = sqlite3.connect(DB)
    heroes = {}
    for name, role in conn.execute("SELECT name, role FROM heroes ORDER BY role, name"):
        heroes.setdefault(role, []).append(name)
    maps = [r[0] for r in conn.execute("SELECT name FROM maps ORDER BY name")]
    conn.close()
    return heroes, maps

HEROES, MAPS = load_data()
ALL_HEROES = [h for role in HEROES for h in HEROES[role]]

# 燃系列赛 BP 流程定义
# (步骤号, 描述, 蓝方动作, 红方动作)
BP_STEPS = [
    (1,  "双方同时 Ban",   "ban", "ban"),
    (2,  "红方 保",        None,  "protect"),
    (3,  "蓝方 Ban",       "ban", None),
    (4,  "蓝方 保",        "protect", None),
    (5,  "红方 Ban",       None,  "ban"),
    (6,  "双方同时 Ban",   "ban", "ban"),
    (7,  "蓝方 保",        "protect", None),
    (8,  "红方 Ban",       None,  "ban"),
    (9,  "红方 保",        None,  "protect"),
    (10, "蓝方 Ban",       "ban", None),
]

ROLE_COLORS = {
    "捍卫者": "#e74c3c",
    "决斗":   "#f39c12",
    "策略家": "#2ecc71",
}

# ── Session State 初始化 ──
DEFAULTS = {
    "phase": "setup",       # setup | bp | pick_blue | pick_red | done
    "bp_step_idx": 0,
    "map": None,
    "side": None,           # "蓝方(攻)" or "红方(守)"
    "blue_bans": [],        # list of hero names
    "red_bans": [],
    "blue_protects": [],
    "red_protects": [],
    "blue_picks": [],
    "red_picks": [],
    "opponent": "",
    "pick_order": 0,
    "bp_history": [],       # 最近10次BP记录
}

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ──
def reset():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    st.session_state._saved = False
    # 清理 pick toggle keys
    for k in list(st.session_state.keys()):
        if k.startswith("_pick_toggle_") or k.startswith("_hp_"):
            del st.session_state[k]
    st.rerun()

def is_banned(hero):
    return hero in st.session_state.blue_bans or hero in st.session_state.red_bans

def is_banned_by(hero, side):
    """side = 'blue' or 'red'"""
    if side == "blue":
        return hero in st.session_state.red_bans  # 对手ban的对我方生效
    return hero in st.session_state.blue_bans       # 我方ban的对对手生效

def is_protected(hero):
    return hero in st.session_state.blue_protects or hero in st.session_state.red_protects

def is_protected_by(hero, side):
    """hero被side保护了吗"""
    if side == "blue":
        return hero in st.session_state.blue_protects
    return hero in st.session_state.red_protects

def is_picked(hero):
    return hero in st.session_state.blue_picks or hero in st.session_state.red_picks

def can_ban(hero, side):
    """side 能否 Ban 这个英雄
    Ban只影响对方池子 → 对方Ban过的英雄，己方仍然可以Ban
    """
    # 自己不能重复Ban同一个英雄
    if side == "blue" and hero in st.session_state.blue_bans: return False
    if side == "red" and hero in st.session_state.red_bans: return False
    if is_picked(hero): return False
    # 被对方保护的不能Ban
    opp = "red" if side == "blue" else "blue"
    if is_protected_by(hero, opp): return False
    return True

def can_pick(hero, side):
    """side 能否选这个英雄（双方可镜像选相同英雄）"""
    # 己方不能重复选同一个英雄
    if side == "blue" and hero in st.session_state.blue_picks: return False
    if side == "red" and hero in st.session_state.red_picks: return False
    # 被对方Ban的不能选
    if is_banned_by(hero, side): return False
    return True

def can_ban_list(side):
    """side 当前能 Ban 的英雄列表"""
    return [h for h in ALL_HEROES if can_ban(h, side)]

def can_protect_list(side):
    """side 当前能 保 的英雄列表（未被对方Ban、未被选、未自保）"""
    opp = "red" if side == "blue" else "blue"
    return [h for h in ALL_HEROES
            if not is_banned_by(h, side)       # 只排除被对方Ban的
            and not is_picked(h)
            and not is_protected_by(h, side)]

def can_pick_list(side):
    """side 当前能选的英雄列表"""
    return [h for h in ALL_HEROES if can_pick(h, side)]

def current_step():
    idx = st.session_state.bp_step_idx
    if idx < len(BP_STEPS):
        return BP_STEPS[idx]
    return None

def our_color():
    return "🟢" if st.session_state.side == "蓝方(攻)" else "🔴"

def their_color():
    return "🔴" if st.session_state.side == "蓝方(攻)" else "🟢"

def our_side():
    return "我方" if "蓝方" in st.session_state.side else "我方"

def our_label():
    """我方是蓝方还是红方"""
    return "蓝方" if st.session_state.side == "蓝方(攻)" else "红方"

def their_label():
    return "红方" if st.session_state.side == "蓝方(攻)" else "蓝方"

def hero_picker(hero_list, picker_key, max_cols=3):
    """按角色分类显示英雄按钮，返回当前选中的英雄名"""
    sel_key = f"_hp_{picker_key}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = None

    # 按角色分组
    by_role = {}
    for h in hero_list:
        for role, names in HEROES.items():
            if h in names:
                by_role.setdefault(role, []).append(h)
                break

    cols = st.columns(len(by_role))
    for (role, names), col in zip(by_role.items(), cols):
        with col:
            st.markdown(f"**{role}** ({len(names)})")
            for h in names:
                is_sel = st.session_state[sel_key] == h
                label = f"✅ {h}" if is_sel else h
                if st.button(label, key=f"{picker_key}_{h}", use_container_width=True):
                    st.session_state[sel_key] = h
                    st.rerun()

    return st.session_state[sel_key]

def undo_bp():
    """撤销上一步 BP 操作"""
    if st.session_state.bp_step_idx == 0:
        return
    st.session_state.bp_step_idx -= 1
    prev_step = BP_STEPS[st.session_state.bp_step_idx]
    _, _, blue_act, red_act = prev_step

    # 蓝方动作
    if blue_act == "ban" and st.session_state.blue_bans:
        st.session_state.blue_bans.pop()
    elif blue_act == "protect" and st.session_state.blue_protects:
        st.session_state.blue_protects.pop()
    # 红方动作
    if red_act == "ban" and st.session_state.red_bans:
        st.session_state.red_bans.pop()
    elif red_act == "protect" and st.session_state.red_protects:
        st.session_state.red_protects.pop()

# ── UI ──
st.set_page_config(page_title="燃系列赛 BP 模拟器", layout="wide")
st.title("漫威争锋 · 燃系列赛 BP 模拟器")

# ─────── SETUP PHASE ───────
if st.session_state.phase == "setup":
    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state.opponent = st.text_input("对手队名", value=st.session_state.opponent)
    with col2:
        st.session_state.map = st.selectbox("地图", ["(随机)"] + MAPS, key="map_select")
        if st.session_state.map == "(随机)":
            st.session_state.map = random.choice(MAPS)
    with col3:
        st.session_state.side = st.selectbox("我方侧别", ["蓝方(攻)", "红方(守)"])

    st.markdown("---")
    st.markdown(f"### 对阵: 我方 ({our_label()}) vs {st.session_state.opponent or '???'} ({their_label()})")
    st.markdown(f"### 地图: {st.session_state.map}")

    if st.button("▶ 开始 BP", type="primary", use_container_width=True):
        st.session_state.phase = "bp"
        st.session_state.bp_step_idx = 0
        st.rerun()

    # 历史记录
    st.divider()
    n = len(st.session_state.bp_history)
    with st.expander(f"📋 BP 历史记录 ({n}/10)", expanded=n > 0):
        if n == 0:
            st.caption("暂无记录，完成一次 BP 模拟后自动出现在这里")
        else:
            for i, r in enumerate(st.session_state.bp_history):
                side_label = "蓝方" if "蓝方" in r["side"] else "红方"
                st.caption(
                    f"#{i+1} {r['map']} | {side_label} | vs {r['opponent'] or '?'} | "
                    f"🟢{','.join(r['blue_picks'])} vs 🔴{','.join(r['red_picks'])}"
                )

# ─────── BP PHASE ───────
elif st.session_state.phase == "bp":
    OC = our_color()
    TC = their_color()
    step = current_step()

    # 侧边栏
    with st.sidebar:
        st.header(f"地图: {st.session_state.map}")
        st.caption(f"我方 = {our_label()}  {OC}")
        st.caption(f"对手 = {their_label()}  {TC}")
        st.divider()
        st.subheader("已完成")
        for i in range(st.session_state.bp_step_idx):
            s = BP_STEPS[i]
            st.caption(f"步骤{s[0]}: {s[1]}")

        # 用实际侧别颜色显示
        if our_label() == "蓝方":
            if st.session_state.blue_bans: st.caption(f"{OC} Ban: {', '.join(st.session_state.blue_bans)}")
            if st.session_state.red_bans: st.caption(f"{TC} Ban: {', '.join(st.session_state.red_bans)}")
            if st.session_state.blue_protects: st.caption(f"{OC} 保: {', '.join(st.session_state.blue_protects)}")
            if st.session_state.red_protects: st.caption(f"{TC} 保: {', '.join(st.session_state.red_protects)}")
        else:
            if st.session_state.blue_bans: st.caption(f"{TC} Ban: {', '.join(st.session_state.blue_bans)}")
            if st.session_state.red_bans: st.caption(f"{OC} Ban: {', '.join(st.session_state.red_bans)}")
            if st.session_state.blue_protects: st.caption(f"{TC} 保: {', '.join(st.session_state.blue_protects)}")
            if st.session_state.red_protects: st.caption(f"{OC} 保: {', '.join(st.session_state.red_protects)}")
        st.divider()
        if st.button("↩ 撤销上一步", use_container_width=True):
            undo_bp()
            st.rerun()
        if st.button("🔄 重新开始", use_container_width=True):
            reset()

    if step is None:
        st.session_state.phase = "pick_blue"
        st.rerun()

    step_num, desc, blue_action, red_action = step
    our_action = blue_action if our_label() == "蓝方" else red_action
    their_action = red_action if our_label() == "蓝方" else blue_action

    st.subheader(f"步骤 {step_num}: {desc}")

    if our_action and their_action:
        # 双方同时操作 — 选好后一次确认
        act_word = "Ban" if our_action == "ban" else "保"
        st.info(f"⚡ 双方同时 {act_word} — 分别点击选择，然后一次确认")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(f"### {OC} 我方")
            av = can_ban_list("blue") if our_action=="ban" else can_protect_list("blue")
            our_sel = hero_picker(av, f"our_{step_num}")
        with col_b:
            st.markdown(f"### {TC} 对手")
            av = can_ban_list("red") if their_action=="ban" else can_protect_list("red")
            their_sel = hero_picker(av, f"their_{step_num}")

        if our_sel and their_sel:
            if st.button(f"✅ 确认双方 {act_word}", type="primary", use_container_width=True):
                if our_action == "ban":
                    (st.session_state.blue_bans if our_label()=="蓝方" else st.session_state.red_bans).append(our_sel)
                    (st.session_state.red_bans if their_label()=="红方" else st.session_state.blue_bans).append(their_sel)
                else:
                    (st.session_state.blue_protects if our_label()=="蓝方" else st.session_state.red_protects).append(our_sel)
                    (st.session_state.red_protects if their_label()=="红方" else st.session_state.blue_protects).append(their_sel)
                st.session_state.bp_step_idx += 1
                st.rerun()
        else:
            st.caption("👆 请先分别在左右两列中点击选择英雄")

    else:
        # 单人操作
        actor = "我方" if our_action else "对手"
        side_key = "blue" if our_action else "red"
        action = our_action or their_action
        act_word = "Ban" if action == "ban" else "保"
        color = OC if actor == "我方" else TC
        st.markdown(f"### {color} {actor} — {act_word}")
        av = can_ban_list(side_key) if action=="ban" else can_protect_list(side_key)
        sel = hero_picker(av, f"single_{step_num}")
        if sel and st.button(f"确认 {act_word}", type="primary", key=f"single_ok_{step_num}"):
            if action == "ban":
                (st.session_state.blue_bans if side_key=="blue" else st.session_state.red_bans).append(sel)
            else:
                (st.session_state.blue_protects if side_key=="blue" else st.session_state.red_protects).append(sel)
            st.session_state.bp_step_idx += 1
            st.rerun()

    # 英雄状态总览
    st.divider()
    st.caption("🟢 = 我方Ban | 🔴 = 对手Ban | 🟩 = 被保 | ✅ = 已选 | ⬜ = 可用")
    cols = st.columns(len(HEROES))
    for (role, hero_list), col in zip(HEROES.items(), cols):
        with col:
            st.markdown(f"**{role}**")
            for h in hero_list:
                banned_by_us = h in st.session_state.blue_bans
                banned_by_them = h in st.session_state.red_bans
                if banned_by_us and banned_by_them:
                    st.markdown(f"🟡 ~~{h}~~")
                elif banned_by_us:
                    st.markdown(f"🟢 ~~{h}~~  ←Ban对手")
                elif banned_by_them:
                    st.markdown(f"🔴 ~~{h}~~  ←Ban我方")
                elif h in st.session_state.blue_protects or h in st.session_state.red_protects:
                    prot_by = "我方" if h in st.session_state.blue_protects else "对手"
                    st.markdown(f"🟩 **{h}** ←{prot_by}保")
                elif h in st.session_state.blue_picks and h in st.session_state.red_picks:
                    st.markdown(f"🟡 👤{h}  (镜像)")
                elif h in st.session_state.blue_picks:
                    st.markdown(f"🟢 👤{h}")
                elif h in st.session_state.red_picks:
                    st.markdown(f"🔴 👤{h}")
                else:
                    st.markdown(f"⬜ {h}")

# ─────── PICK PHASE ───────
elif st.session_state.phase in ("pick_blue", "pick_red"):
    OC = our_color()
    TC = their_color()
    picking_blue = st.session_state.phase == "pick_blue"
    label = "我方" if picking_blue else "对手"
    color = OC if picking_blue else TC
    target = st.session_state.blue_picks if picking_blue else st.session_state.red_picks
    max_picks = 6

    with st.sidebar:
        st.header(f"地图: {st.session_state.map}")
        st.divider()
        st.subheader("已选阵容")
        if st.session_state.blue_picks:
            st.caption(f"{OC} 我方: {', '.join(st.session_state.blue_picks)}")
        if st.session_state.red_picks:
            st.caption(f"{TC} 对手: {', '.join(st.session_state.red_picks)}")

        if not picking_blue:
            if st.button("↩ 返回修改我方阵容", use_container_width=True):
                st.session_state.red_picks.clear()
                st.session_state.phase = "pick_blue"
                st.rerun()

        if st.button("🔄 重新开始", use_container_width=True):
            reset()

    # ── BP 结果总览 ──
    ban_col1, ban_col2 = st.columns(2)
    with ban_col1:
        st.markdown(f"### {OC} 我方 BP")
        st.markdown(f"**Ban:** {'、'.join(st.session_state.blue_bans) if st.session_state.blue_bans else '(无)'}")
        st.markdown(f"**保:** {'、'.join(st.session_state.blue_protects) if st.session_state.blue_protects else '(无)'}")
    with ban_col2:
        st.markdown(f"### {TC} 对手 BP")
        st.markdown(f"**Ban:** {'、'.join(st.session_state.red_bans) if st.session_state.red_bans else '(无)'}")
        st.markdown(f"**保:** {'、'.join(st.session_state.red_protects) if st.session_state.red_protects else '(无)'}")

    st.divider()

    # 多选模式
    toggle_key = f"_pick_toggle_{label}"
    if toggle_key not in st.session_state:
        st.session_state[toggle_key] = []

    st.subheader(f"{color} {label} 选人 ({len(st.session_state[toggle_key])}/{max_picks})")

    if st.session_state[toggle_key]:
        st.markdown("**当前选择:** " + " → ".join(st.session_state[toggle_key]))

    pick_side = "blue" if picking_blue else "red"
    available = can_pick_list(pick_side)

    st.caption(f"点击英雄切换选择，选满 6 个后确认 ({len(st.session_state[toggle_key])}/6)")

    by_role = {}
    for h in available:
        for role, names in HEROES.items():
            if h in names:
                by_role.setdefault(role, []).append(h)
                break

    cols = st.columns(len(by_role))
    for (role, names), col in zip(by_role.items(), cols):
        with col:
            st.markdown(f"**{role}** ({len(names)})")
            for h in names:
                is_sel = h in st.session_state[toggle_key]
                label = f"✅ {h}" if is_sel else h
                if st.button(label, key=f"pktog_{label}_{h}", use_container_width=True):
                    if is_sel:
                        st.session_state[toggle_key].remove(h)
                    elif len(st.session_state[toggle_key]) < 6:
                        st.session_state[toggle_key].append(h)
                    st.rerun()

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if len(st.session_state[toggle_key]) == 6:
            if st.button("✅ 确认阵容", type="primary", use_container_width=True):
                target.clear()
                target.extend(st.session_state[toggle_key])
                st.session_state[toggle_key] = []
                st.session_state.phase = "pick_red" if picking_blue else "done"
                st.rerun()
    with col_btn2:
        if len(st.session_state[toggle_key]) > 0:
            if st.button("↩ 清空重选", use_container_width=True):
                st.session_state[toggle_key] = []
                st.rerun()

# ─────── DONE ───────
elif st.session_state.phase == "done":
    OC = our_color()
    TC = their_color()
    # 保存到历史（只存一次）
    if not st.session_state.get("_saved"):
        record = {
            "map": st.session_state.map,
            "side": st.session_state.side,
            "opponent": st.session_state.opponent,
            "blue_bans": list(st.session_state.blue_bans),
            "red_bans": list(st.session_state.red_bans),
            "blue_protects": list(st.session_state.blue_protects),
            "red_protects": list(st.session_state.red_protects),
            "blue_picks": list(st.session_state.blue_picks),
            "red_picks": list(st.session_state.red_picks),
        }
        st.session_state.bp_history.insert(0, record)
        if len(st.session_state.bp_history) > 10:
            st.session_state.bp_history.pop()
        st.session_state._saved = True

    st.success("🎉 BP 完成！")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader(f"{OC} 我方 ({our_label()})")
        st.markdown("**Ban:** " + ", ".join(st.session_state.blue_bans))
        st.markdown("**保:** " + ", ".join(st.session_state.blue_protects))
        st.markdown("**阵容:** " + ", ".join(st.session_state.blue_picks))
    with col2:
        st.subheader(f"{TC} 对手 ({their_label()})")
        st.markdown("**Ban:** " + ", ".join(st.session_state.red_bans))
        st.markdown("**保:** " + ", ".join(st.session_state.red_protects))
        st.markdown("**阵容:** " + ", ".join(st.session_state.red_picks))

    st.divider()

    # 历史记录
    if st.session_state.bp_history:
        with st.expander(f"📋 历史记录 ({len(st.session_state.bp_history)}/10)", expanded=False):
            for i, r in enumerate(st.session_state.bp_history):
                st.caption(
                    f"#{i+1} {r['map']} | {our_label()} | "
                    f"🟢{','.join(r['blue_picks'])} vs 🔴{','.join(r['red_picks'])}"
                )

    st.caption(f"地图: {st.session_state.map} | 我方: {our_label()}")
    if st.button("🔄 新一轮模拟", type="primary"):
        st.session_state._saved = False
        reset()
