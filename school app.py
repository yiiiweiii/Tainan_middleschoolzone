import streamlit as st
import pandas as pd
import re
import os
import zipfile  # 🌟 新增：專門用來處理壓縮檔的工具

# ==========================================
# 0. 網頁組態設定 (Canva 風格美感基礎)
# ==========================================
st.set_page_config(
    page_title="台南市國中小學區查詢",
    page_icon="🏫",
    layout="wide",  # 使用寬版佈局
    initial_sidebar_state="expanded"
)

# 自定義 CSS (調整 metrics 顏色與卡片陰影，增加美感)
st.markdown("""
<style>
    [data-testid="stMetricValue"] {
        color: #4F46E5; /* 使用現代感的靛藍色 */
    }
    .st_stContainer {
        border-radius: 15px; /* 圓角卡片 */
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); /* 淡淡的陰影 */
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 1. 資料載入與智慧快取
# ==========================================
@st.cache_data
def load_all_data():
    # 鄉鎮市區代碼對應表
    DISTRICT_MAP = {
        '6700100': '新營區', '6700200': '鹽水區', '6700300': '白河區', '6700400': '柳營區', '6700500': '後壁區',
        '6700600': '東山區', '6700700': '麻豆區', '6700800': '下營區', '6700900': '六甲區', '6701000': '官田區',
        '6701100': '大內區', '6701200': '佳里區', '6701300': '學甲區', '6701400': '西港區', '6701500': '七股區',
        '6701600': '將軍區', '6701700': '北門區', '6701800': '新化區', '6701900': '善化區', '6702000': '新市區',
        '6702100': '安定區', '6702200': '山上區', '6702300': '玉井區', '6702400': '楠西區', '6702500': '南化區',
        '6702600': '左鎮區', '6702700': '仁德區', '6702800': '歸仁區', '6702900': '關廟區', '6703000': '龍崎區',
        '6703100': '永康區', '6703200': '東區', '6703300': '南區', '6703400': '北區', '6703500': '安南區',
        '6703600': '安平區', '6703700': '中西區'
    }

    # A. 載入門牌資料 (處理 Mac 隱藏檔問題)
    addr_df = pd.DataFrame()
    try:
        # 🌟 破解法：手動打開 ZIP，忽略 __MACOSX，只讀取真的 csv
        with zipfile.ZipFile("address.csv.zip", "r") as z:
            csv_filename = [name for name in z.namelist() if not name.startswith("__MACOSX") and name.endswith(".csv")][
                0]
            with z.open(csv_filename) as f:
                addr_df = pd.read_csv(f, dtype=str)

        addr_df.fillna('', inplace=True)
        addr_df['區'] = addr_df['鄉鎮市區代碼'].map(DISTRICT_MAP)

        def to_hw(t):
            return str(t).translate(str.maketrans('０１２３４５６７８９', '0123456789')).strip()

        for col in ['街、路段', '巷', '弄', '號', '鄰']: addr_df[col] = addr_df[col].apply(to_hw)
        addr_df['標準地址'] = addr_df['區'] + addr_df['街、路段'] + addr_df['巷'] + addr_df['弄'] + addr_df['號']
    except Exception as e:
        st.error(f"⚠️ 門牌資料庫讀取失敗：{e}")

    # B. 通用學區規則載入器
    def load_rules(file_name, school_type):
        rules_data = {}
        try:
            try:
                rules_df = pd.read_csv(file_name, encoding='utf-8-sig')
            except:
                rules_df = pd.read_csv(file_name, encoding='big5')

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
            return rules_data
        except Exception as e:
            st.error(f"⚠️ {school_type}學區資料 ({file_name}) 讀取失敗：{e}")
            return {}

    # 載入國中與國小規則
    elem_rules = load_rules("elementary school zone.csv", "國小")
    juni_rules = load_rules("middle school zone.csv", "國中")

    return addr_df, elem_rules, juni_rules


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
        return "⚠️ 尚未建置規則", "無"
    try:
        query_n = int(n_num_str)
    except:
        query_n = -1

    for n_rule_str, school_name in rules_data[dist][vill].items():
        valid_list = parse_neigh_list(n_rule_str)
        if valid_list == "全部" or (isinstance(valid_list, list) and query_n in valid_list):
            if "共同" in school_name: return "無", school_name
            return school_name, "無"
    return "未知鄰別", "未知"


# ==========================================
# 3. 網頁 UI 設計 (Canva 風格)
# ==========================================

# A. 資料載入
df_addr, elem_dict, juni_dict = load_all_data()

# B. 側邊欄 (個人名片與提示)
with st.sidebar:
    st.markdown("# 👩‍💼 掃QR code 快買")

    # 🌟 智慧判斷名片圖片 (更新為最新語法 use_container_width)
    if os.path.exists("my_card.jpg"):
        st.image("my_card.jpg", use_container_width=True)
    elif os.path.exists("my_card.png"):
        st.image("my_card.png", use_container_width=True)
    else:
        st.info("💡 將您的名片圖檔命名為 `my_card.jpg` 並放入資料夾，就會自動顯示在這裡喔！")

    st.markdown("### 我是 weiii")
    st.markdown("""
    本系統資料更新日期：**1150324**
    *(資料僅供參考，實際請以教育局最新公告為準)*
    """)
    st.divider()
    st.caption("powered by Streamlit & weiii")

# C. 主頁面標題
st.title("🏫 台南市學區智慧查詢系統")
st.markdown("##### 🚀 我做得好辛苦")

# D. 地址輸入 (使用較大的輸入框)
user_input = st.text_input(
    "🔍 請輸入地址（預設是阿琛家）：",
    placeholder="例如：(700)台南市中西區大同路一段70巷23號",
    help="支援郵遞區號與樓層自動剔除，請安心輸入最完整的地址。"
)

# E. 查詢結果顯示
if user_input:
    # 智慧解析邏輯 (保留)
    q = user_input.translate(str.maketrans('０１２３４５６７８９', '0123456789')).replace(" ", "").replace("台南市", "").replace(
        "臺南市", "")
    q = re.sub(r'^[\(\[]?\d{3,6}[\)\]]?', '', q)
    search_q = q
    if "號" in search_q:
        search_q = search_q.split("號")[0] + "號"
    elif "樓" in search_q:
        search_q = search_q.split("樓")[0]

    with st.spinner('正在從數十萬筆門牌中精準比對，請稍候...'):
        match = df_addr[df_addr['標準地址'] == search_q]
        if match.empty:
            match = df_addr[df_addr['標準地址'].str.contains(search_q, na=False, regex=False)]
        if match.empty and search_q.endswith("號"):
            match = df_addr[df_addr['標準地址'].str.contains(search_q[:-1], na=False, regex=False)]

    if not match.empty:
        res = match.iloc[0]
        st.success(f"🎉 **成功精準配對地址**：台南市{res['標準地址']}")
        st.markdown("---")

        # 結果佈局：使用卡片設計
        # 第一張卡片：行政定位
        st.markdown("### 🗺️ 行政定位結果")
        loc_card = st.container(border=True)
        with loc_card:
            col1, col2, col3 = st.columns(3)
            col1.metric("📌 行政區", res['區'])
            col2.metric("🏘️ 里別", res['村里'])
            col3.metric("🔢 鄰別", f"{res['鄰']} 鄰")

        st.markdown("---")

        # 第二張卡片與第三張卡片：學區結果 (並排顯示)
        col_es, col_js = st.columns(2)

        # 國小卡片
        with col_es:
            st.markdown("#### 🎒 國小學區")
            es_card = st.container(border=True)
            with es_card:
                # 執行國小查詢邏輯
                e_basic, e_shared = find_school_info(res['區'], res['村里'], res['鄰'], elem_dict)
                if e_basic != "無":
                    st.markdown(f"**基本學區**：\n<h2 style='color:#16a34a;'>{e_basic}</h2>", unsafe_allow_html=True)
                if e_shared != "無":
                    st.markdown(f"**共同學區**：\n<h4 style='color:#ca8a04;'>{e_shared}</h4>", unsafe_allow_html=True)

        # 國中卡片
        with col_js:
            st.markdown("#### 🎓 國中學區")
            js_card = st.container(border=True)
            with js_card:
                # 執行國中查詢邏輯
                j_basic, j_shared = find_school_info(res['區'], res['村里'], res['鄰'], juni_dict)
                if j_basic != "無":
                    st.markdown(f"**基本學區**：\n<h2 style='color:#1d4ed8;'>{j_basic}</h2>", unsafe_allow_html=True)
                if j_shared != "無":
                    st.markdown(f"**共同學區**：\n<h4 style='color:#ca8a04;'>{j_shared}</h4>", unsafe_allow_html=True)

    else:
        st.error(f"❌ 找不到與「{search_q}」相符的門牌，請確認路名、巷弄是否正確。")
else:
    # 預設歡迎畫面 (Canva 簡約風格)
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; padding: 50px; color: #6b7280; background-color: #f9fafb; border-radius: 15px;">
        <h2>🏠 Welcome to system </h2>
        <p>在上方輸入框，貼上您的物件地址，小精靈會找到對應的學區。</p>
        <p><i>搜尋完記得找我買房子</i></p>
    </div>
    """, unsafe_allow_html=True)
