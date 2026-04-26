from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import pandas as pd
import re
import zipfile

app = Flask(__name__)

# ==========================================
# 🔑 LINE 兩把鑰匙已綁定完成！
# ==========================================
line_bot_api = LineBotApi(
    'D2ToqNMtl1tqK7MepVA1FAcxHktf4sbQksqTbskQTNTBThGJz2m1aCdsmtKFKmGkw036c31oEQbBr26c8boaHM8MmYj++oD0za7E672xFk3qbn0klWx7cZxGuIimrEgCXS8zWA6MY2LiqmW5W86LQgdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('22c3dcc8f543c87d53cde3e8291de9fa')

# ==========================================
# 1. 資料載入 (跟原本網頁版一樣的邏輯)
# ==========================================
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

# 在系統啟動時先載入資料，這樣機器人回覆才會快
addr_df = pd.DataFrame()
try:
    with zipfile.ZipFile("address.csv.zip", "r") as z:
        csv_filename = [name for name in z.namelist() if not name.startswith("__MACOSX") and name.endswith(".csv")][0]
        with z.open(csv_filename) as f:
            addr_df = pd.read_csv(f, dtype=str)
    addr_df.fillna('', inplace=True)
    addr_df['區'] = addr_df['鄉鎮市區代碼'].map(DISTRICT_MAP)


    def to_hw(t):
        return str(t).translate(str.maketrans('０１２３４５６７８９', '0123456789')).strip()


    for col in ['街、路段', '巷', '弄', '號', '鄰']: addr_df[col] = addr_df[col].apply(to_hw)
    addr_df['標準地址'] = addr_df['區'] + addr_df['街、路段'] + addr_df['巷'] + addr_df['弄'] + addr_df['號']
except:
    pass


def load_rules(file_name):
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
    except:
        return {}


elem_dict = load_rules("elementary school zone.csv")
juni_dict = load_rules("middle school zone.csv")


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
    if dist not in rules_data or vill not in rules_data[dist]: return "⚠️ 尚未建置規則", "無"
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
# 2. LINE 接線生 (Webhook) 接收訊息的通道
# ==========================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


# ==========================================
# 3. 處理使用者傳來的文字
# ==========================================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_input = event.message.text

    # 解析地址
    q = user_input.translate(str.maketrans('０１２３４５６７８９', '0123456789')).replace(" ", "").replace("台南市", "").replace(
        "臺南市", "")
    q = re.sub(r'^[\(\[]?\d{3,6}[\)\]]?', '', q)
    search_q = q
    if "號" in search_q:
        search_q = search_q.split("號")[0] + "號"
    elif "樓" in search_q:
        search_q = search_q.split("樓")[0]

    # 搜尋門牌
    match = addr_df[addr_df['標準地址'] == search_q]
    if match.empty:
        match = addr_df[addr_df['標準地址'].str.contains(search_q, na=False, regex=False)]
    if match.empty and search_q.endswith("號"):
        match = addr_df[addr_df['標準地址'].str.contains(search_q[:-1], na=False, regex=False)]

    if not match.empty:
        res = match.iloc[0]
        # 查國小
        e_basic, e_shared = find_school_info(res['區'], res['村里'], res['鄰'], elem_dict)
        # 查國中
        j_basic, j_shared = find_school_info(res['區'], res['村里'], res['鄰'], juni_dict)

        # 準備回覆給客人的文字
        reply_msg = f"🏠 【地址精準定位】\n台南市{res['標準地址']}\n行政區：{res['區']} / {res['村里']} / {res['鄰']}鄰\n"
        reply_msg += f"──────────\n"
        reply_msg += f"🎒 【國小學區】\n基本：{e_basic}\n共同：{e_shared}\n\n"
        reply_msg += f"🎓 【國中學區】\n基本：{j_basic}\n共同：{j_shared}\n"
        reply_msg += f"──────────\n💡 資料僅供參考，請以教育局最新公告為準。"

    else:
        reply_msg = f"❌ 找不到與「{user_input}」相符的門牌，請確認路名、巷弄是否輸入正確喔！"

    # 把訊息傳回去給客人
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_msg))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)