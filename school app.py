import streamlit as st
import pandas as pd
import re
import time

# 設定網頁標題與分頁圖示
st.set_page_config(page_title="台南市國中學區查詢系統", page_icon="🏠", layout="centered")


# ==========================================
# 1. 資料載入與快取 (優化效能)
# ==========================================
@st.cache_data
def load_data():
    # 鄉鎮市區代碼對應表
    DISTRICT_MAP = {
        '6700100': '新營區', '6700200': '鹽水區', '6700300': '白河區', '6700400': '柳營區', '6700500': '後壁區',
        '6700600': '東山區',
        '6700700': '麻豆區', '6700800': '下營區', '6700900': '六甲區', '6701000': '官田區', '6701100': '大內區',
        '6701200': '佳里區',
        '6701300': '學甲區', '6701400': '西港區', '6701500': '七股區', '6701600': '將軍區', '6701700': '北門區',
        '6701800': '新化區',
        '6701900': '善化區', '6702000': '新市區', '6702100': '安定區', '6702200': '山上區', '6702300': '玉井區',
        '6702400': '楠西區',
        '6702500': '南化區', '6702600': '左鎮區', '6702700': '仁德區', '6702800': '歸仁區', '6702900': '關廟區',
        '6703000': '龍崎區',
        '6703100': '永康區', '6703200': '東區', '6703300': '南區', '6703400': '北區', '6703500': '安南區',
        '6703600': '安平區',
        '6703700': '中西區'
    }

    # 載入門牌資料
    try:
        df = pd.read_csv("address.csv", dtype=str)
        df.fillna('', inplace=True)
        df['區'] = df['鄉鎮市區代碼'].map(DISTRICT_MAP)

        # 全形轉半形工具
        def to_hw(t):
            return str(t).translate(str.maketrans('０１２３４５６７８９', '0123456789')).strip()

        for col in ['街、路段', '巷', '弄', '號', '鄰']:
            df[col] = df[col].apply(to_hw)
        df['標準地址'] = df['區'] + df['街、路段'] + df['巷'] + df['弄'] + df['號']
    except Exception as e:
        st.error(f"門牌資料庫 (address.csv) 讀取失敗：{e}")
        df = pd.DataFrame()

    # 載入學區規則
    rules_data = {}
    try:
        try:
            rules_df = pd.read_csv("middle school zone.csv", encoding='utf-8-sig')
        except:
            rules_df = pd.read_csv("middle school zone.csv", encoding='big5')

        rules_df.columns = rules_df.columns.str.strip()
        for _, row in rules_df.iterrows():
            if pd.isna(row.get('行政區')): continue
            dist = str(row['行政區']).strip()
            vill = str(row['里別']).strip()
            if not vill.endswith('里'): vill += '里'
            neigh = str(row['鄰別']).strip()
            school_text = str(row['基本學區']).strip()

            if dist not in rules_data: rules_data[dist] = {}
            if vill not in rules_data[dist]: rules_data[dist][vill] = {}
            rules_data[dist][vill][neigh] = school_text
    except Exception as e:
        st.error(f"學區資料 (middle school zone.csv) 讀取失敗：{e}")

    return df, rules_data


# ==========================================
# 2. 核心邏輯
# ==========================================
def parse_neigh_list(s):
    s = str(s).strip()
    if "全" in s: return "全部"
    clean = s.replace(" ", "").replace("至", "-").replace("鄰", "").replace("、", ",")
    res = []
    for p in clean.split(','):
        if '-' in p:
            try:
                start, end = map(int, p.split('-'))
                res.extend(list(range(start, end + 1)))
            except:
                pass
        else:
            try:
                res.append(int(p))
            except:
                pass
    return res


def find_school_info(dist, vill, n_num_str, rules_data):
    if dist not in rules_data or vill not in rules_data[dist]:
        return "尚未建置", "無"
    try:
        query_n = int(n_num_str)
    except:
        query_n = -1

    for n_rule_str, school_name in rules_data[dist][vill].items():
        valid_list = parse_neigh_list(n_rule_str)
        if valid_list == "全部" or (isinstance(valid_list, list) and query_n in valid_list):
            if "共同" in school_name:
                return "無", school_name
            return school_name, "無"
    return "未知", "未知"


# ==========================================
# 3. 網頁 UI 設計
# ==========================================
st.title("🏠 台南市國中學區查詢系統")
st.markdown("---")

df_addr, rules_dict = load_data()

# 地址輸入區
user_input = st.text_input("🔍 請輸入或貼上地址：", placeholder="例如：台南市中西區五妃街15號",
                           help="支援郵遞區號過濾、自動樓層切除")

if user_input:
    # 智慧解析 Step 1: 全形轉半形 & 去空白 & 去台南市贅字
    q = user_input.translate(str.maketrans('０１２３４５６７８９', '0123456789')).replace(" ", "").replace("台南市", "").replace(
        "臺南市", "")

    # 智慧解析 Step 2: 剃除郵遞區號 (704, (704), [704] 等)
    q = re.sub(r'^[\(\[]?\d{3,6}[\)\]]?', '', q)

    # 智慧解析 Step 3: 自動去尾巴 (保留到「號」為止)
    search_q = q
    if "號" in search_q:
        search_q = search_q.split("號")[0] + "號"
    elif "樓" in search_q:
        search_q = search_q.split("樓")[0]

    # 在資料庫中搜尋
    with st.spinner('正在比對門牌資料...'):
        match = df_addr[df_addr['標準地址'] == search_q]
        if match.empty:
            match = df_addr[df_addr['標準地址'].str.contains(search_q, na=False, regex=False)]

        # 容錯處理：如果輸入有「號」但資料庫沒有（例如之1號）
        if match.empty and search_q.endswith("號"):
            match = df_addr[df_addr['標準地址'].str.contains(search_q[:-1], na=False, regex=False)]

    if not match.empty:
        res = match.iloc[0]
        basic, shared = find_school_info(res['區'], res['村里'], res['鄰'], rules_dict)

        # 顯示結果介面
        st.success(f"📌 **系統配對地址**：台南市{res['標準地址']}")

        c1, c2, c3 = st.columns(3)
        c1.metric("行政區", res['區'])
        c2.metric("里別", res['村里'])
        c3.metric("鄰別", f"{res['鄰']} 鄰")

        st.markdown("### 🎓 學區查詢結果")
        container = st.container(border=True)
        with container:
            if basic != "無":
                st.write(f"✅ **基本學區**：{basic}")
            if shared != "無":
                st.write(f"🤝 **共同學區**：{shared}")
            if basic == "無" and shared == "無":
                st.write("⚠️ 查無此鄰里的學區資料，請確認 CSV 內容。")
    else:
        st.error(f"❌ 找不到與「{search_q}」相符的門牌，請確認路名、巷弄是否正確。")

st.markdown("---")
st.caption("weiii專屬工具 | 資料更新日期：1150324")