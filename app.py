import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import io
import copy
import urllib.parse
import requests
import streamlit.components.v1 as components

### =========================================================
### 0. ربط قاعدة البيانات السحابية الدائمة (Supabase Cloud)
### =========================================================
try:
    from supabase import create_client, Client
    _SUPABASE_LIB = True
except Exception:
    _SUPABASE_LIB = False

@st.cache_resource(show_spinner=False)
def get_supabase():
    """إنشاء اتصال واحد مع Supabase وإعادة استخدامه للسرعة"""
    if not _SUPABASE_LIB:
        return None
    url, key = None, None
    if "supabase" in st.secrets:
        sec = st.secrets["supabase"]
        if hasattr(sec, "get"):
            url = sec.get("url") or sec.get("URL") or sec.get("SUPABASE_URL")
            key = sec.get("key") or sec.get("KEY") or sec.get("SUPABASE_KEY") or sec.get("anon_key")
    if not url and hasattr(st.secrets, "get"):
        url = st.secrets.get("url") or st.secrets.get("SUPABASE_URL")
    if not key and hasattr(st.secrets, "get"):
        key = st.secrets.get("key") or sec.get("SUPABASE_KEY") or st.secrets.get("anon_key")
    if url and key:
        try:
            return create_client(url, key)
        except Exception:
            return None
    return None

def supabase_ready():
    return get_supabase() is not None

@st.cache_data(ttl=15, show_spinner=False)
def fetch_all_grades_db(term, week):
    sb = get_supabase()
    if sb is None:
        return []
    try:
        res = sb.table("thaghr_grades").select("student_id, term, week, score, is_absent").eq("term", term).eq("week", week).execute()
        return res.data or []
    except Exception:
        return []

def save_grades_to_db(term, week, grades_list):
    sb = get_supabase()
    if sb is None:
        st.error("⚠️ لم يتم الاتصال بـ Supabase. يرجى التأكد من إعداد Secrets.")
        return False
    try:
        for g in grades_list:
            sb.table("thaghr_grades").delete().eq("student_id", str(g['student_id'])).eq("term", term).eq("week", week).execute()
        
        payload = [{
            "student_id": str(g['student_id']),
            "term": term,
            "week": week,
            "score": float(g['score']),
            "is_absent": int(g['is_absent'])
        } for g in grades_list]
        
        if payload:
            sb.table("thaghr_grades").insert(payload).execute()
        return True
    except Exception as ex:
        st.error(f"حدث خطأ أثناء حفظ الدرجات: {ex}")
        return False
    finally:
        st.cache_data.clear()

@st.cache_data(ttl=30, show_spinner=False)
def fetch_student_phones_db():
    sb = get_supabase()
    if sb is None:
        return {}
    try:
        res = sb.table("thaghr_students_info").select("student_id, phone").execute()
        out = {}
        for r in (res.data or []):
            if r.get("phone"):
                out[str(r["student_id"])] = str(r["phone"])
        return out
    except Exception:
        return {}

### =========================================================
### 1. دالة زر/أيقونة الطباعة المباشرة (Print Button Component)
### =========================================================
def print_button(label="🖨️ طباعة التقرير", button_id="print_btn"):
    """مكون جافاسكريبت لإضافة زر طباعة مباشر عبر المتصفح"""
    js_code = f"""
        <button onclick="window.print()" style="
            background-color: #1f77b4;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 15px;
            font-weight: bold;
            font-family: 'Cairo', sans-serif;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.12);
            transition: all 0.2s ease;
            width: 100%;
        " onmouseover="this.style.backgroundColor='#145a8d'" onmouseout="this.style.backgroundColor='#1f77b4'">
            {label}
        </button>
    """
    components.html(js_code, height=50)


def render_clean_html(html_content):
    """تنظيف كود HTML من أي مسافات بادئة لمنع ظهوره كأكواد في streamlit"""
    lines = [line.strip() for line in html_content.splitlines() if line.strip()]
    st.markdown("".join(lines), unsafe_allow_html=True)


### =========================================================
### 2. خدمات WhatsApp Direct API و Mora SMS
### =========================================================
def send_whatsapp_direct_api(phone, message, instance_id="", api_token=""):
    if not api_token or not instance_id:
        return False, "يرجى إدخال Instance ID و API Token الخاص بخدمة WhatsApp Gateway في القائمة الجانبية."
    
    phone_clean = str(phone).strip().replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("05"):
        phone_clean = "966" + phone_clean[1:]
    elif phone_clean.startswith("5"):
        phone_clean = "966" + phone_clean
        
    url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
    payload = {
        "token": api_token,
        "to": phone_clean,
        "body": message
    }
    headers = {'content-type': 'application/x-www-form-urlencoded'}
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            return True, "تم إرسال رسالة الواتساب بنجاح في الخلفية دون فتح التطبيق!"
        else:
            return False, f"خطأ في الاستجابة: {response.text}"
    except Exception as e:
        return False, f"فشل الاتصال بـ API: {e}"

def create_whatsapp_web_url(phone, message):
    phone_clean = str(phone).strip().replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("05"):
        phone_clean = "966" + phone_clean[1:]
    elif phone_clean.startswith("5"):
        phone_clean = "966" + phone_clean
    msg_encoded = urllib.parse.quote(message)
    return f"https://api.whatsapp.com/send?phone={phone_clean}&text={msg_encoded}"

def send_mora_sms(phone, message, username="966508634881", password="", sender="THAGHR-S", otp=""):
    if not username or not password:
        return False, "يرجى التأكد من إعدادات حساب Mora SMS."
    phone_clean = str(phone).strip().replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("05"):
        phone_clean = "966" + phone_clean[1:]
    elif phone_clean.startswith("5"):
        phone_clean = "966" + phone_clean
        
    url = "https://www.mora-sms.com/api/sendsms.php"
    params = {
        "username": username,
        "password": password,
        "sender": sender,
        "numbers": phone_clean,
        "message": message,
        "unicode": "E",
        "return": "json"
    }
    if otp:
        params["otp"] = otp
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            return True, "تم إرسال الرسالة النصية بنجاح عبر Mora SMS."
        else:
            return False, f"خطأ في الإرسال: {resp.text}"
    except Exception as e:
        return False, f"فشل الاتصال بـ Mora SMS: {e}"

def send_bulk_messages(students_list, channel="sms", mora_creds={}, wa_creds={}):
    succ, fail = 0, 0
    details = []
    for st_item in students_list:
        phone = st_item['phone']
        msg = st_item['message']
        if channel == "wa_api":
            status, resp = send_whatsapp_direct_api(phone, msg, wa_creds.get("instance_id", ""), wa_creds.get("api_token", ""))
        else:
            status, resp = send_mora_sms(phone, msg, mora_creds.get("username", ""), mora_creds.get("password", ""), mora_creds.get("sender", ""), mora_creds.get("otp", ""))
        if status:
            succ += 1
        else:
            fail += 1
        details.append({"name": st_item['name'], "status": status, "response": resp})
    return succ, fail, details

def generate_parent_message(student_name, score, is_absent=False):
    if is_absent:
        return (
            f"المحترم ولي أمر الطالب/ {student_name}\n"
            f"السلام عليكم ورحمة الله وبركاته،،\n"
            f"نحيطكم علماً بأن ابنكم كان غائباً عن اختبار التقييم الأسبوعي لهذا الأسبوع في مدرسة الثغر النموذجية الأهلية.\n"
            f"نرجو التواصل مع إدارة المدرسة لمتابعة حالة الطالب.\n"
            f"شاكرين حسن تعاونكم."
        )
    elif score is None or score < 50:
        return (
            f"المحترم ولي أمر الطالب/ {student_name}\n"
            f"السلام عليكم ورحمة الله وبركاته،،\n"
            f"نود إشعاركم بأن مستوى الطالب في تقييم هذا الأسبوع بحاجة إلى متابعة واهتمام، حيث حصل على نسبة ({score}%).\n"
            f"نأمل حث الطالب على الاستذكار والمراجعة لرفع مستواه.\n"
            f"شاكرين اهتمامكم الدائم."
        )
    elif score <= 75:
        return (
            f"المحترم ولي أمر الطالب/ {student_name}\n"
            f"السلام عليكم ورحمة الله وبركاته،،\n"
            f"نحيطكم علماً بأن ابنكم حقق مستوى جيداً في التقييم الأسبوعي بنسبة ({score}%).\n"
            f"نتطلع إلى مزيد من الجهد للوصول إلى مستوى الإتقان العالي.\n"
            f"شاكرين لكم حسن المتابعة."
        )
    else:
        return (
            f"المحترم ولي أمر الطالب/ {student_name}\n"
            f"السلام عليكم ورحمة الله وبركاته،،\n"
            f"يسر إدارة مدرسة الثغر النموذجية الأهلية تهنئتكم بالمستوى المتميز لابنكم في التقييم الأسبوعي، حيث حصل على نسبة إتقان ({score}%).\n"
            f"نبارك لكم هذا التفوق ونتمنى له دوام النجاح والتميز.\n"
            f"مع تحيات إدارة المدرسة."
        )

### =========================================================
### 3. قاعدة بيانات الطلاب الثابتة
### =========================================================
STUDENTS_DB_GRADES = {
    "الأول المتوسط": {
        1: [
            {"id": "1167628468", "name": "ابراهيم بن محمد بن علي الوهيبي", "grade": "الأول المتوسط", "class": 1, "phone": "966504158122"},
            {"id": "2395664317", "name": "بلال عبدالرزاق عيسى العيسى", "grade": "الأول المتوسط", "class": 1, "phone": "966507448712"},
            {"id": "1170582165", "name": "حسام بن محمد بن علي ال رايان البارقي", "grade": "الأول المتوسط", "class": 1, "phone": "966504445699"},
            {"id": "1169004353", "name": "ريان عبدالله جابر الاسمري", "grade": "الأول المتوسط", "class": 1, "phone": "966554260960"},
            {"id": "2446713998", "name": "زيد زياد عبد اللطيف ابو قبع", "grade": "الأول المتوسط", "class": 1, "phone": "966590123455"},
            {"id": "2527104554", "name": "سامي سعد عباس حمد", "grade": "الأول المتوسط", "class": 1, "phone": "966591781701"},
            {"id": "1170111759", "name": "سعد ناصر سعد السيف", "grade": "الأول المتوسط", "class": 1, "phone": "966503219351"},
            {"id": "1195559479", "name": "عبدالعزيز عبدالله عبدالعزيز العمار", "grade": "الأول المتوسط", "class": 1, "phone": "966555838394"},
            {"id": "1153310501", "name": "عبدالله بن سليمان بن عبدالله الراجحي", "grade": "الأول المتوسط", "class": 1, "phone": "0551418881"},
            {"id": "1170836520", "name": "عبدالله سعد بن محمد العيشان", "grade": "الأول المتوسط", "class": 1, "phone": "966504217660"},
            {"id": "1171448515", "name": "علي احمد علي كريري", "grade": "الأول المتوسط", "class": 1, "phone": "966558885481"},
            {"id": "1170853053", "name": "علي سعد علي القحطاني", "grade": "الأول المتوسط", "class": 1, "phone": "966505466546"},
            {"id": "1172018036", "name": "عمر عبدالله سعد الجبرين", "grade": "الأول المتوسط", "class": 1, "phone": "966555249420"},
            {"id": "2552851368", "name": "مازن اسلام احمد ابراهيم موسى", "grade": "الأول المتوسط", "class": 1, "phone": "966550490495"},
            {"id": "013609321", "name": "محمد أحمد علي عقيل", "grade": "الأول المتوسط", "class": 1, "phone": "966546000184"},
            {"id": "2394606749", "name": "محمد اشرف مسعود ابوخاطر", "grade": "الأول المتوسط", "class": 1, "phone": "966501276888"},
            {"id": "1170042046", "name": "محمد بن فيصل بن مصلح الشمراني", "grade": "الأول المتوسط", "class": 1, "phone": "966555832145"},
            {"id": "1169174164", "name": "محمد نايف فراج الدعجاني", "grade": "الأول المتوسط", "class": 1, "phone": "966554444782"},
            {"id": "2380890976", "name": "وائل بولعيش", "grade": "الأول المتوسط", "class": 1, "phone": "966591534495"}
        ],
        2: [
            {"id": "1170348286", "name": "الوليد ابن خالد بن فهد العتيبي", "grade": "الأول المتوسط", "class": 2, "phone": "966558522229"},
            {"id": "1172433185", "name": "باسل محمد فرج الدوسري", "grade": "الأول المتوسط", "class": 2, "phone": "966537589781"},
            {"id": "1173391556", "name": "بسام بن عبدالكريم بن عبدالله الحرقان الدوسري", "grade": "الأول المتوسط", "class": 2, "phone": "966534467820"},
            {"id": "1169185053", "name": "تركي عبدالله مسفر الدوسري", "grade": "الأول المتوسط", "class": 2, "phone": "966505258369"},
            {"id": "1170108078", "name": "تميم فهد عبدالعزيز العزاز", "grade": "الأول المتوسط", "class": 2, "phone": "966554435692"},
            {"id": "1170970741", "name": "جاسر بن عبدالله بن منصور المطاطحة الحارثي", "grade": "الأول المتوسط", "class": 2, "phone": "966559455545"},
            {"id": "1168982427", "name": "راكان عبدالله يحي كريري", "grade": "الأول المتوسط", "class": 2, "phone": "966581727444"},
            {"id": "1172590968", "name": "ريان عبدالله منصور السبر", "grade": "الأول المتوسط", "class": 2, "phone": "966566959670"},
            {"id": "2392863888", "name": "ريان وليد حلاق", "grade": "الأول المتوسط", "class": 2, "phone": "966530527662"},
            {"id": "1170420473", "name": "سيف عبدالكريم بريك العصيمي", "grade": "الأول المتوسط", "class": 2, "phone": "966504277904"},
            {"id": "1168942108", "name": "صالح حسن فتحي سندي", "grade": "الأول المتوسط", "class": 2, "phone": "966557553922"},
            {"id": "1173182138", "name": "عبدالرحمن ابراهيم عبدالله الحضيف", "grade": "الأول المتوسط", "class": 2, "phone": "966558822674"},
            {"id": "1172448548", "name": "عبدالله صالح حمد الصفيان", "grade": "الأول المتوسط", "class": 2, "phone": "966558889978"},
            {"id": "1170000945", "name": "فهد ابن احمد بن فهد العثمان", "grade": "الأول المتوسط", "class": 2, "phone": "966504484898"},
            {"id": "1167092616", "name": "فهد عويض ثعيل المطيري", "grade": "الأول المتوسط", "class": 2, "phone": "966508271056"},
            {"id": "1170413171", "name": "فهد نايف فهد الحسينان", "grade": "الأول المتوسط", "class": 2, "phone": "966504140616"},
            {"id": "1170294118", "name": "فيصل موينع عبدالله بن موينع", "grade": "الأول المتوسط", "class": 2, "phone": "966541600918"},
            {"id": "1171524604", "name": "فيصل ناصر سيف العريفي", "grade": "الأول المتوسط", "class": 2, "phone": "966505474606"},
            {"id": "2502333707", "name": "محمد اسلام محمد دراز", "grade": "الأول المتوسط", "class": 2, "phone": "966556124553"},
            {"id": "1170374993", "name": "مشاري عثمان سعد ناصر السعد", "grade": "الأول المتوسط", "class": 2, "phone": "966500330693"},
            {"id": "1170884165", "name": "يزن محمد علي اليحيا", "grade": "الأول المتوسط", "class": 2, "phone": "966557072133"},
            {"id": "1170548737", "name": "يوسف محمد عبدالله الدوسري", "grade": "الأول المتوسط", "class": 2, "phone": "966556666176"}
        ]
    },
    "الثاني المتوسط": {
        1: [
            {"id": "1163760935", "name": "احمد سامي بن احمد العمران", "grade": "الثاني المتوسط", "class": 1, "phone": "966551501503"},
            {"id": "1153756612", "name": "الوليد عبدالله بن ابراهيم المبدل", "grade": "الثاني المتوسط", "class": 1, "phone": "966505241627"},
            {"id": "1163187972", "name": "راكان سالم بن محمد بن مسفر القحطاني", "grade": "الثاني المتوسط", "class": 1, "phone": "966556609291"},
            {"id": "1171617069", "name": "سعود خالد عبدالله الحمد", "grade": "الثاني المتوسط", "class": 1, "phone": "966555242944"},
            {"id": "1163458878", "name": "سعود مشعل بن ابراهيم الشثري", "grade": "الثاني المتوسط", "class": 1, "phone": "966598887996"},
            {"id": "1167623758", "name": "سلطان عبدالله حسن القحطاني", "grade": "الثاني المتوسط", "class": 1, "phone": "966563484825"},
            {"id": "1164769430", "name": "عبدالرحمن حمد بن محمد العريفي", "grade": "الثاني المتوسط", "class": 1, "phone": "966555556856"}
        ]
    }
}

### =========================================================
### 4. إعدادات الصفحة والتنسيقات المخصصة (Custom CSS & Print Setup)
### =========================================================
st.set_page_config(
    page_title="منصة مدرسة الثغر النموذجية - تقارير الإتقان والرسائل",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# حل مشكلة تداخل النصوص (Text Overlap Fix) وتصميم التقارير للطباعة (Print CSS)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');

/* تنسيقات العامة لمنع تداخل النصوص وارتفاع الأسطر */
html, body, [class*="css"], div, span, p, label, button, input, select {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl !important;
    text-align: right !important;
    line-height: 1.8 !important;
}

/* ضبط العناوين والبطاقات لمنع التداخل */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Cairo', sans-serif !important;
    line-height: 1.6 !important;
    margin-bottom: 8px !important;
    padding-top: 4px !important;
}

/* تنسيق بطاقات الإحصائيات Metrics */
[data-testid="stMetric"] {
    background-color: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    padding: 12px 16px !important;
    border-radius: 10px !important;
    min-height: 90px !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
    font-weight: 800 !important;
    line-height: 1.5 !important;
    color: #1e293b !important;
    margin-top: 4px !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.95rem !important;
    font-weight: 700 !important;
    line-height: 1.5 !important;
    color: #475569 !important;
}

.status-badge-ok {
    background-color: #d4edda;
    color: #155724;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: bold;
    text-align: center;
    border: 1px solid #c3e6cb;
}
.status-badge-off {
    background-color: #f8d7da;
    color: #721c24;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: bold;
    text-align: center;
    border: 1px solid #f5c6cb;
}

/* حاوية التقرير المطبوع */
.report-paper {
    background-color: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
    padding: 24px !important;
    margin: 20px 0 !important;
    box-shadow: 0 4px 15px rgba(0,0,0,0.06) !important;
}

table.report-header-table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin-bottom: 20px !important;
    border-bottom: 2px solid #1f4e78 !important;
    padding-bottom: 12px !important;
}
table.report-header-table td {
    border: none !important;
    padding: 6px 10px !important;
    vertical-align: middle !important;
    line-height: 1.6 !important;
    font-size: 13px !important;
}

/* جداول التقارير المطبوعة - تمنع تداخل النص بالجداول */
table.printable-table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin-top: 15px !important;
    font-size: 13px !important;
    direction: rtl !important;
}
table.printable-table th {
    background-color: #1f4e78 !important;
    color: #ffffff !important;
    padding: 12px 8px !important;
    text-align: center !important;
    font-weight: 700 !important;
    border: 1px solid #1f4e78 !important;
    line-height: 1.5 !important;
    vertical-align: middle !important;
}
table.printable-table td {
    border: 1px solid #cbd5e1 !important;
    padding: 10px 8px !important;
    text-align: center !important;
    color: #0f172a !important;
    line-height: 1.6 !important;
    vertical-align: middle !important;
    font-size: 13px !important;
}
table.printable-table tr:nth-child(even) {
    background-color: #f8fafc !important;
}

/* تنسيقات الطباعة الخاصة بـ @media print */
@media print {
    section[data-testid="stSidebar"], 
    header, 
    footer, 
    .stButton, 
    .no-print,
    iframe {
        display: none !important;
    }
    
    @page {
        size: A4 portrait;
        margin: 12mm 10mm 12mm 10mm;
    }
    
    body, .stApp, .main .block-container {
        background-color: white !important;
        color: black !important;
        padding: 0 !important;
        margin: 0 !important;
        width: 100% !important;
    }
    
    .report-paper {
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    
    table.printable-table th {
        background-color: #1f4e78 !important;
        color: white !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }
    table.printable-table tr:nth-child(even) {
        background-color: #f1f5f9 !important;
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
    }
}
</style>
""", unsafe_allow_html=True)

# الشريط الجانبي
st.sidebar.title("📌 القائمة الرئيسية")

if supabase_ready():
    st.sidebar.markdown('<div class="status-badge-ok">🟢 متصل بقاعدة بيانات Supabase الدائمة</div>', unsafe_allow_html=True)
else:
    st.sidebar.markdown('<div class="status-badge-off">🔴 غير متصل بـ Supabase (يعمل محلياً)</div>', unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📱 إعدادات البوابات والرسائل")

with st.sidebar.expander("💬 إعدادات WhatsApp Direct API"):
    wa_instance = st.text_input("Instance ID:", value="", key="wa_inst_inp")
    wa_token = st.text_input("API Token:", value="", type="password", key="wa_tok_inp")
    st.caption("💡 إرسال إشعارات الواتساب مباشرة لولي الأمر دون الحاجة لفتح تطبيق الواتساب.")

with st.sidebar.expander("📱 إعدادات Mora SMS"):
    mora_user = st.text_input("اسم المستخدم / الرقم:", value="966508634881", key="mora_u")
    mora_pass = st.text_input("كلمة المرور:", value="THA@0508634881", type="password", key="mora_p")
    mora_sender = st.text_input("اسم المرسل المعتمد:", value="THAGHR-S", key="mora_s")
    mora_otp = st.text_input("كود التحقق / OTP (إذا طلب):", value="", key="mora_otp_input")

st.sidebar.markdown("---")
page = st.sidebar.radio("اختر الصفحة:", ["📝 صفحة الرصد", "🏫 إدارة المدرسة وتقارير أولياء الأمور"])

### =========================================================
### الصفحة الأولى: صفحة الرصد (RECORDING SHEET)
### =========================================================
if page == "📝 صفحة الرصد":
    st.subheader("📝 صفحة رصد درجات الإتقان الأسبوعية")
    
    col_sel1, col_sel2, col_sel3 = st.columns(3)
    with col_sel1:
        selected_grade = st.selectbox("اختر المرحلة / الصف الدراسي:", list(STUDENTS_DB_GRADES.keys()))
    with col_sel2:
        classes_list = list(STUDENTS_DB_GRADES[selected_grade].keys())
        selected_class = st.selectbox("اختر الفصل:", classes_list)
    with col_sel3:
        terms_list = ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"]
        selected_term = st.selectbox("اختر الفصل الدراسي:", terms_list)

    col_w1, col_w2 = st.columns(2)
    with col_w1:
        weeks = [f"الأسبوع {i}" for i in range(1, 19)]
        selected_week = st.selectbox("اختر الأسبوع:", weeks)
    with col_w2:
        st.write("") 
        st.info(f"📍 يتم الرصد لـ: **{selected_grade} (فصل {selected_class})** - **{selected_week}**")

    st.markdown("---")
    
    students_list = STUDENTS_DB_GRADES[selected_grade][selected_class]
    db_grades_list = fetch_all_grades_db(selected_term, selected_week)
    db_grades_map = {str(g['student_id']): g for g in db_grades_list}

    st.markdown("##### 📋 قائمة الطلاب وتعديل الدرجات:")
    
    form_grades = []
    
    for idx, student in enumerate(students_list):
        sid = str(student["id"])
        saved_rec = db_grades_map.get(sid, {})
        default_score = float(saved_rec.get("score", 100.0))
        default_absent = bool(saved_rec.get("is_absent", 0))

        c1, c2, c3, c4 = st.columns([1, 4, 2, 2])
        with c1:
            st.write(f"**#{idx+1}**")
        with c2:
            st.markdown(f"**{student['name']}**<br/><span style='color:#6c757d; font-size:12px;'>رقم الهوية: {sid}</span>", unsafe_allow_html=True)
        with c3:
            sc_val = st.number_input(
                f"الدرجة",
                min_value=0.0,
                max_value=100.0,
                value=default_score,
                step=1.0,
                key=f"score_{sid}_{selected_term}_{selected_week}"
            )
        with c4:
            is_abs = st.checkbox(
                "غائب ⚪",
                value=default_absent,
                key=f"abs_{sid}_{selected_term}_{selected_week}"
            )

        form_grades.append({
            "student_id": sid,
            "score": sc_val,
            "is_absent": 1 if is_abs else 0
        })

    st.markdown("---")
    if st.button("💾 حفظ الدرجات في قاعدة البيانات السحابية (Supabase)", use_container_width=True, type="primary"):
        with st.spinner("جاري حفظ البيانات في Supabase..."):
            ok = save_grades_to_db(selected_term, selected_week, form_grades)
            if ok:
                st.success("✅ تم حفظ درجات الطلاب بنجاح وبشكل دائم!")

### =========================================================
### الصفحة الثانية: إدارة المدرسة وتقارير أولياء الأمور
### =========================================================
elif page == "🏫 إدارة المدرسة وتقارير أولياء الأمور":
    st.subheader("🏫 إدارة المدرسة وإرسال تقارير أولياء الأمور والطباعة")

    col_w1, col_w2 = st.columns(2)
    with col_w1:
        weeks = [f"الأسبوع {i}" for i in range(1, 19)]
        selected_week = st.selectbox("اختر الأسبوع لعرض التقرير والرسائل:", weeks)
    with col_w2:
        selected_term = st.selectbox("اختر الفصل الدراسي:", ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"])
        
    st.markdown("---")

    db_grades_list = fetch_all_grades_db(selected_term, selected_week)
    db_grades_map = {str(g['student_id']): g for g in db_grades_list}
    phone_db_map = fetch_student_phones_db()

    cat_red, cat_blue, cat_green, cat_gray = [], [], [], []
    all_students_flat = []

    for g_name, g_data in STUDENTS_DB_GRADES.items():
        for c_num, s_list in g_data.items():
            for s_item in s_list:
                sid = str(s_item["id"])
                p_num = phone_db_map.get(sid, s_item.get("phone", ""))
                rec = db_grades_map.get(sid, {})
                sc = rec.get("score", None)
                is_abs = rec.get("is_absent", 0)

                # إذا لم تكن هناك درجات محفوظة في الداتابيز، نضع الدرجة الافتراضية 100 لتفادي الحقول الفارغة
                final_score = float(sc) if (sc is not None) else 100.0

                msg = generate_parent_message(s_item["name"], final_score, is_abs == 1)

                row_dict = {
                    "id": sid,
                    "name": s_item["name"],
                    "grade": g_name,
                    "class": c_num,
                    "phone": p_num,
                    "score": final_score if is_abs == 0 else 0.0,
                    "is_absent": is_abs,
                    "message": msg
                }
                all_students_flat.append(row_dict)

                if is_abs == 1:
                    cat_gray.append(row_dict)
                elif final_score < 50:
                    cat_red.append(row_dict)
                elif final_score <= 75:
                    cat_blue.append(row_dict)
                else:
                    cat_green.append(row_dict)

    # ---------------------------------------------------------
    # 1. قسم التقرير الشامل للأسبوع المختار (معد ومصمم للطباعة)
    # ---------------------------------------------------------
    st.markdown("### 📊 التقرير الشامل للأسبوع المختار")
    col_rep1, col_rep2 = st.columns([3, 1])

    with col_rep1:
        st.info(f"**تقرير شامل:** {selected_term} - {selected_week} | إجمالي طلاب المدرسة: {len(all_students_flat)} طالب")

    with col_rep2:
        print_button(label="🖨️ طباعة تقرير الأسبوع الشامل", button_id="print_full_week")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🔴 أقل من 50%", f"{len(cat_red)} طالب")
    m2.metric("🔵 50% - 75%", f"{len(cat_blue)} طالب")
    m3.metric("🟢 76% - 100%", f"{len(cat_green)} طالب")
    m4.metric("⚪ الغياب", f"{len(cat_gray)} طالب")

    # توليد التقرير الشامل بصيغة HTML جاهزة وموثقة للطباعة والعرض (بدون Canvas)
    today_str = datetime.now().strftime("%Y/%m/%d")
    
    rows_html = ""
    for idx, s in enumerate(all_students_flat):
        status_txt = "غائب ⚪" if s['is_absent'] == 1 else ("متفوق 🟢" if s['score'] >= 76 else ("جيد 🔵" if s['score'] >= 50 else "يحتاج متابعة 🔴"))
        score_txt = f"{s['score']}%" if s['is_absent'] == 0 else "-"
        rows_html += f"""
        <tr>
            <td>{idx+1}</td>
            <td>{s['id']}</td>
            <td style="text-align: right; padding-right: 12px; font-weight: 600;">{s['name']}</td>
            <td>{s['grade']}</td>
            <td>فصل {s['class']}</td>
            <td style="font-weight: bold;">{score_txt}</td>
            <td>{status_txt}</td>
        </tr>
        """

    full_report_html = f"""
    <div class="report-paper">
        <table class="report-header-table">
            <tr>
                <td style="width: 30%; text-align: right; font-size: 12px; line-height: 1.4;">
                    <strong>المملكة العربية السعودية</strong><br/>
                    وزارة التعليم<br/>
                    إدارة التعليم بمحافظة جدة<br/>
                    <strong>مدرسة الثغر النموذجية الأهلية المتوسطة</strong>
                </td>
                <td style="width: 40%; text-align: center;">
                    <h3 style="margin:0; color:#1f4e78; font-family:'Cairo'; font-weight:bold;">📋 التقرير الشامل لدرجات الإتقان</h3>
                    <div style="font-size: 13px; color:#475569; margin-top:4px;">{selected_term} - {selected_week}</div>
                </td>
                <td style="width: 30%; text-align: left; font-size: 12px; line-height: 1.4;">
                    <strong>تاريخ التقرير:</strong> {today_str}<br/>
                    <strong>إجمالي الطلاب:</strong> {len(all_students_flat)} طالب<br/>
                    <strong>عدد الغياب:</strong> {len(cat_gray)} طالب
                </td>
            </tr>
        </table>

        <table class="printable-table">
            <thead>
                <tr>
                    <th style="width: 5%;">#</th>
                    <th style="width: 15%;">رقم الهوية</th>
                    <th style="width: 30%;">اسم الطالب</th>
                    <th style="width: 18%;">المرحلة الدراسية</th>
                    <th style="width: 10%;">الفصل</th>
                    <th style="width: 11%;">النسبة %</th>
                    <th style="width: 11%;">الحالة</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <br/>
        <table style="width: 100%; margin-top: 25px; border: none; text-align: center; font-size: 13px; font-weight: bold;">
            <tr>
                <td style="width: 33%; border: none;">معلم المادة:<br/><br/>...........................</td>
                <td style="width: 33%; border: none;">وكيل الشؤون التعليمية:<br/><br/>...........................</td>
                <td style="width: 34%; border: none;">مدير المدرسة:<br/><br/>...........................</td>
            </tr>
        </table>
    </div>
    """

    render_clean_html(full_report_html)

    st.markdown("---")

    # ---------------------------------------------------------
    # 2. قسم طباعة تقرير الصف الدراسي المحدد
    # ---------------------------------------------------------
    st.markdown("### 🏫 تقرير الصف المالي والدرجات (طباعة حسب الصف)")
    
    col_g1, col_g2, col_g3 = st.columns([2, 2, 2])

    with col_g1:
        selected_rep_grade = st.selectbox("اختر المرحلة / الصف الدراسي للطباعة:", list(STUDENTS_DB_GRADES.keys()), key="rep_grade")

    with col_g2:
        available_classes = list(STUDENTS_DB_GRADES[selected_rep_grade].keys())
        selected_rep_class = st.selectbox("اختر الفصل:", available_classes, key="rep_class")

    class_students = [
        s for s in all_students_flat 
        if s["grade"] == selected_rep_grade and s["class"] == selected_rep_class
    ]

    with col_g3:
        st.write("")
        print_button(label=f"🖨️ طباعة تقرير {selected_rep_grade} ({selected_rep_class})", button_id="print_class_rep")

    if class_students:
        class_rows_html = ""
        for idx, s in enumerate(class_students):
            status_txt = "غائب ⚪" if s['is_absent'] == 1 else ("متفوق 🟢" if s['score'] >= 76 else ("جيد 🔵" if s['score'] >= 50 else "يحتاج متابعة 🔴"))
            score_txt = f"{s['score']}%" if s['is_absent'] == 0 else "-"
            class_rows_html += f"""
            <tr>
                <td>{idx+1}</td>
                <td>{s['id']}</td>
                <td style="text-align: right; padding-right: 12px; font-weight: 600;">{s['name']}</td>
                <td style="font-weight: bold;">{score_txt}</td>
                <td>{status_txt}</td>
            </tr>
            """

        class_report_html = f"""
        <div class="report-paper">
            <table class="report-header-table">
                <tr>
                    <td style="width: 30%; text-align: right; font-size: 12px; line-height: 1.4;">
                        <strong>المملكة العربية السعودية</strong><br/>
                        وزارة التعليم<br/>
                        إدارة التعليم بمحافظة جدة<br/>
                        <strong>مدرسة الثغر النموذجية الأهلية المتوسطة</strong>
                    </td>
                    <td style="width: 40%; text-align: center;">
                        <h3 style="margin:0; color:#1f4e78; font-family:'Cairo'; font-weight:bold;">🏫 تقرير تقييم الصف الدراسي</h3>
                        <div style="font-size: 14px; color:#1e293b; font-weight:bold; margin-top:4px;">{selected_rep_grade} - فصل ({selected_rep_class})</div>
                        <div style="font-size: 12px; color:#64748b;">{selected_term} - {selected_week}</div>
                    </td>
                    <td style="width: 30%; text-align: left; font-size: 12px; line-height: 1.4;">
                        <strong>تاريخ التقرير:</strong> {today_str}<br/>
                        <strong>عدد طلاب الفصل:</strong> {len(class_students)} طالب
                    </td>
                </tr>
            </table>

            <table class="printable-table">
                <thead>
                    <tr>
                        <th style="width: 8%;">#</th>
                        <th style="width: 22%;">رقم الهوية</th>
                        <th style="width: 45%;">اسم الطالب</th>
                        <th style="width: 12%;">النسبة %</th>
                        <th style="width: 13%;">الحالة</th>
                    </tr>
                </thead>
                <tbody>
                    {class_rows_html}
                </tbody>
            </table>

            <br/>
            <table style="width: 100%; margin-top: 25px; border: none; text-align: center; font-size: 13px; font-weight: bold;">
                <tr>
                    <td style="width: 50%; border: none;">معلم الفصل / المادة:<br/><br/>...........................</td>
                    <td style="width: 50%; border: none;">مدير المدرسة:<br/><br/>...........................</td>
                </tr>
            </table>
        </div>
        """

        render_clean_html(class_report_html)
    else:
        st.warning("لا توجد بيانات متاحة لهذا الصف في الأسبوع المختار.")

    st.markdown("---")

    # ---------------------------------------------------------
    # تبويبات إرسال الرسائل حسب الفئات (WhatsApp API + Mora SMS)
    # ---------------------------------------------------------
    st.markdown("##### 📱 قناتا الإرسال المتاحتان لولي الأمر (WhatsApp API + Mora SMS):")
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.success("💬 **واتساب المباشر (WhatsApp API):** إرسال تلقائي مباشر في الخلفية فور الضغط دون فتح تطبيق الواتساب.")
    with col_info2:
        st.info("📱 **Mora SMS (مورا):** إرسال مباشر عبر البوابة المدرسية المعتمدة مع دعم الإرسال الفردي والجماعي.")

    tab1, tab2, tab3, tab4 = st.tabs([
        f"🔴 أقل من 50% ({len(cat_red)})",
        f"🔵 50% - 75% ({len(cat_blue)})",
        f"🟢 76% - 100% ({len(cat_green)})",
        f"⚪ الغياب ({len(cat_gray)})"
    ])

    def show_category_tab(cat_list, cat_name):
        if not cat_list:
            st.info(f"لا يوجد طلاب في {cat_name} بهذا الأسبوع.")
        else:
            st.markdown(f"##### 📲 قائمة رسائل {cat_name} الموجهة لولي الأمر:")
            
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                with st.expander(f"💬 إرسال واتساب جماعي في الخلفية ({len(cat_list)} طالب)"):
                    st.write("سيتم إرسال الرسائل تلقائياً عبر WhatsApp Direct API دون فتح أي تطبيق.")
                    if st.button(f"⚡ إرسال واتساب جماعي لـ {cat_name}", key=f"bulk_wa_{cat_name}"):
                        with st.spinner("جاري الإرسال الجماعي عبر WhatsApp API..."):
                            succ, fail, details = send_bulk_messages(
                                cat_list, channel="wa_api", wa_creds={"instance_id": wa_instance, "api_token": wa_token}
                            )
                            st.success(f"✅ اكتملت عملية إرسال الواتساب! النجاح: {succ} | الفشل: {fail}")
            
            with col_b2:
                with st.expander(f"🚀 إرسال SMS جماعي عبر Mora ({len(cat_list)} طالب)"):
                    st.write("سيتم إرسال الرسائل النصية القصيرة تلقائياً عبر منصة Mora.")
                    if st.button(f"⚡ إرسال SMS جماعي لـ {cat_name}", key=f"bulk_sms_{cat_name}"):
                        with st.spinner("جاري الإرسال الجماعي عبر Mora SMS..."):
                            m_creds = {"username": mora_user, "password": mora_pass, "sender": mora_sender, "otp": mora_otp}
                            succ, fail, details = send_bulk_messages(cat_list, channel="sms", mora_creds=m_creds)
                            st.success(f"✅ اكتملت عملية الإرسال! النجاح: {succ} | الفشل: {fail}")

            st.markdown("---")

            for item in cat_list:
                wa_manual_url = create_whatsapp_web_url(item['phone'], item['message'])
                with st.expander(f"👤 {item['name']} ({item['grade']} - فصل {item['class']}) | جوال ولي الأمر: {item['phone']}"):
                    st.write(f"**رقم الهوية:** {item['id']}")
                    st.write(f"**النسبة المئوية / الدرجة:** {item['score']}%" if item['is_absent'] == 0 else "**الحالة:** غائب ⚪")
                    st.info(f"💬 **نص الرسالة الموجهة:**\n\n```\n{item['message']}\n```")

    with tab1:
        show_category_tab(cat_red, "فئة أقل من 50%")
    with tab2:
        show_category_tab(cat_blue, "فئة 50% - 75%")
    with tab3:
        show_category_tab(cat_green, "فئة 76% - 100%")
    with tab4:
        show_category_tab(cat_gray, "فئة الغياب")
