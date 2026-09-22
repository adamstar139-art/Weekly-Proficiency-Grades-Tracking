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
### 1. دالة الترويسة السعودية باللون الأخضر (Saudi Identity Header)
### =========================================================
def render_saudi_header(page_title=""):
    """عرض ترويسة باللون الأخضر بالهوية السعودية الرسمية لمدرسة الثغر النموذجية"""
    header_html = f"""
    <div style="
        background: linear-gradient(135deg, #005027 0%, #006C35 50%, #004D25 100%);
        color: #ffffff;
        border-radius: 12px;
        padding: 20px 25px;
        margin-bottom: 25px;
        border-bottom: 4px solid #D4AF37;
        box-shadow: 0 6px 18px rgba(0, 108, 53, 0.25);
        text-align: center;
        direction: rtl;
        font-family: 'Cairo', sans-serif;
    ">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 15px;">
            <div style="text-align: right;">
                <div style="font-size: 13px; color: #E2E8F0; opacity: 0.95; font-weight: 600;">المملكة العربية السعودية • وزارة التعليم</div>
                <div style="font-size: 22px; font-weight: 800; color: #FFFFFF; margin-top: 2px;">مدرسة الثغر النموذجية الأهلية المتوسطة</div>
            </div>
            <div style="
                background: rgba(0, 0, 0, 0.2);
                padding: 8px 20px;
                border-radius: 25px;
                border: 1px solid rgba(212, 175, 55, 0.6);
                text-align: center;
            ">
                <div style="font-size: 17px; font-weight: 800; color: #FDE047;">🌴⚔️ برنامج لرصد درجات الإتقان الأسبوعي</div>
                <div style="font-size: 12px; color: #FFFFFF; font-weight: 700; margin-top:3px; background: rgba(0,0,0,0.25); padding: 2px 10px; border-radius: 12px; display: inline-block;">✨ تصميم أ/ محمد سامي السعيد</div>
                {f'<div style="font-size: 13px; color: #FFFFFF; font-weight: 600; margin-top:2px;">{page_title}</div>' if page_title else ''}
            </div>
            <div style="text-align: left; font-size: 13px; color: #E2E8F0; font-weight: 600;">
                <div>إدارة التعليم بمحافظة الرياض</div>
                <div style="color: #FDE047; font-weight: bold; margin-top: 2px;">🇸🇦 الهوية الوطنية المعتمدة</div>
            </div>
        </div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

### =========================================================
### 2. دالة زر/أيقونة الطباعة المباشرة (Print Button Component)
### =========================================================
def print_button(label="🖨️ طباعة التقرير", button_id="print_btn", target_mode="mode-print-full"):
    """مكون جافاسكريبت لإطلاق أمر الطباعة المباشر مع تحديد التقرير المستهدف فقط"""
    js_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@600;700&display=swap" rel="stylesheet">
        <style>
            body {{ margin: 0; padding: 0; background: transparent; text-align: right; direction: rtl; }}
            .print-btn-style {{
                background-color: #006C35;
                color: #ffffff;
                padding: 10px 18px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-size: 15px;
                font-weight: 700;
                font-family: 'Cairo', sans-serif;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                box-shadow: 0 4px 8px rgba(0,0,0,0.15);
                transition: all 0.2s ease;
                width: 100%;
            }}
            .print-btn-style:hover {{
                background-color: #004d25;
                box-shadow: 0 6px 12px rgba(0,0,0,0.2);
            }}
        </style>
    </head>
    <body>
        <button class="print-btn-style" id="{button_id}" onclick="triggerPrint()">{label}</button>
        <script>
            function triggerPrint() {{
                try {{
                    var parentDoc = window.parent.document;
                    parentDoc.body.classList.remove('mode-print-full', 'mode-print-class');
                    parentDoc.body.classList.add('{target_mode}');
                }} catch(e) {{
                    console.log("Setting print mode error:", e);
                }}
                setTimeout(function() {{
                    if (window.parent && window.parent.print) {{
                        window.parent.print();
                    }} else {{
                        window.print();
                    }}
                }}, 150);
            }}
        </script>
    </body>
    </html>
    """
    components.html(js_code, height=52)

def render_clean_html(html_str):
    """تنظيف وتجريد المسافات البادئة لضمان عدم تحول HTML إلى كتل كود نصية"""
    lines = [line.strip() for line in html_str.strip().splitlines() if line.strip()]
    cleaned_html = "".join(lines)
    st.markdown(cleaned_html, unsafe_allow_html=True)

# =========================================================
# 2. دوال إرسال الرسائل (Mora SMS + WhatsApp Gateway API)
# =========================================================
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

def send_mora_sms(phone, message, username, password, sender_name, otp_code=""):
    phone_clean = str(phone).strip().replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("05"):
        phone_clean = "966" + phone_clean[1:]
    elif phone_clean.startswith("5"):
        phone_clean = "966" + phone_clean

    url = "https://mora-sa.com/api/v1/sendsms"
    payload = {
        "username": username,
        "password": password,
        "sender": sender_name,
        "numbers": phone_clean,
        "message": message,
        "otp": otp_code
    }
    try:
        res = requests.post(url, data=payload, timeout=10)
        if res.status_code == 200:
            return True, "تم إرسال SMS بنجاح عبر Mora!"
        else:
            return False, f"خطأ Mora: {res.text}"
    except Exception as ex:
        return False, f"تعذر الإرسال: {ex}"

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
        details.append((st_item['name'], phone, status, resp))
    return succ, fail, details

def create_whatsapp_web_url(phone, text):
    phone_clean = str(phone).strip().replace("+", "").replace(" ", "").replace("-", "")
    if phone_clean.startswith("05"):
        phone_clean = "966" + phone_clean[1:]
    elif phone_clean.startswith("5"):
        phone_clean = "966" + phone_clean
    encoded_text = urllib.parse.quote(text)
    return f"https://api.whatsapp.com/send?phone={phone_clean}&text={encoded_text}"

def generate_parent_message(student_name, score, is_absent):
    if is_absent:
        return (
            f"المكرم ولي أمر الطالب/ {student_name}، نود التنبيه على غياب الطالب هذا اليوم، "
            f"ونحثكم على متابعة الانتظام وحضور الاختبارات لتجنب حسم الدرجات والتأثير على مستواه التحصيلي: متوسطة الثغر النموذجية الأهلية."
        )
    sc_str = f"{score}%" if score is not None else "أقل من 50%"
    if score is None or score < 50:
        return (
            f"المكرم ولي أمر الطالب/ {student_name}، نفيدكم بأن نسبة إتقان الطالب هذا الأسبوع هي ({sc_str}). "
            f"حرصاً منا على مصلحة ابنكم ومستقبله الدراسي، نود إشعاركم بوجود تراجع ملحوظ في مستواه التحصيلي مؤخراً، "
            f"ونرجو منكم تكثيف المتابعة المنزلية والتواصل معنا للوقوف على أسباب هذا التراجع ووضع خطة لتحسين أدائه. مع تحياتنا متوسطة الثغر النموذجية الأهلية."
        )
    elif score <= 75:
        return (
            f"المكرم ولي أمر الطالب/ {student_name}، نفيدكم بأن نسبة إتقان الطالب هذا الأسبوع هي ({sc_str}). "
            f"نود إحاطتكم علماً بأن المستوى التحصيلي لابنكم جيد ومستقر بشكل عام، ولكنه يمتلك قدرات أعلى تؤهله لتحقيق درجات أفضل. "
            f"نأمل منكم التركيز معه في الفترة القادمة لرفع كفاءته الدراسية. شاكرين لكم تعاونكم الدائم. مع تحياتنا متوسطة الثغر النموذجية الأهلية."
        )
    else:
        return (
            f"المكرم ولي أمر الطالب/ {student_name}، نتقدم بخالص الشكر والتقدير لكم وللطالب على الاهتمام والتفوق بنسبة إتقان ممتازة ({sc_str})، "
            f"يسعدنا إبلاغكم بأن ابنكم قدم أداءً تحصيلياً متميزاً وسلوكاً رائعاً داخل الفصل، وحصل على درجات ممتازة في التقييمات الأخيرة. "
            f"نشكر لكم حسن المتابعة والاهتمام، ونرجو الاستمرار في هذا الدعم المتبادل للحفاظ على هذا المستوى المتفوق. مع تحياتنا متوسطة الثغر النموذجية الأهلية."
        )

### =========================================================
### 4. قاعدة بيانات الطلاب الكاملة (جميع المراحل والشعب - 167 طالب)
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
            {"id": "1164269209", "name": "ذياب بن محمد بن ذياب بن محمد ال مربط القحطاني", "grade": "الثاني المتوسط", "class": 1, "phone": "966561169999"},
            {"id": "1163187972", "name": "راكان سالم بن محمد بن مسفر القحطاني", "grade": "الثاني المتوسط", "class": 1, "phone": "966556609291"},
            {"id": "1171617069", "name": "سعود خالد عبدالله الحمد", "grade": "الثاني المتوسط", "class": 1, "phone": "966555242944"},
            {"id": "1163458878", "name": "سعود مشعل بن ابراهيم الشثري", "grade": "الثاني المتوسط", "class": 1, "phone": "966598887996"},
            {"id": "1167623758", "name": "سلطان عبدالله حسن القحطاني", "grade": "الثاني المتوسط", "class": 1, "phone": "966563484825"},
            {"id": "1164769430", "name": "عبدالرحمن حمد بن محمد العريفي", "grade": "الثاني المتوسط", "class": 1, "phone": "966555556856"},
            {"id": "1162391039", "name": "عبدالعزيز خالد علي القحطاني", "grade": "الثاني المتوسط", "class": 1, "phone": "966533036660"},
            {"id": "1163162702", "name": "عبدالله احمد عبد المحسن المقرن", "grade": "الثاني المتوسط", "class": 1, "phone": "966555411786"},
            {"id": "1163539826", "name": "عبدالله محمد عبدالله الشنيفي", "grade": "الثاني المتوسط", "class": 1, "phone": "966503463375"},
            {"id": "1163777558", "name": "علي سلطان بن محمد العثيم", "grade": "الثاني المتوسط", "class": 1, "phone": "966556778899"},
            {"id": "1163435165", "name": "فراس تركي محمد التويجري", "grade": "الثاني المتوسط", "class": 1, "phone": "966555228811"},
            {"id": "1162817454", "name": "فيصل محمد مسحل الحارثي", "grade": "الثاني المتوسط", "class": 1, "phone": "966504221144"},
            {"id": "1163391210", "name": "مبارك عبدالله مبارك الدوسري", "grade": "الثاني المتوسط", "class": 1, "phone": "966505112233"},
            {"id": "1162888125", "name": "محمد خالد محمد الشهري", "grade": "الثاني المتوسط", "class": 1, "phone": "966554119988"},
            {"id": "1162919102", "name": "مشاري سعد فهد الدوسري", "grade": "الثاني المتوسط", "class": 1, "phone": "966501122445"},
            {"id": "1163012111", "name": "مقرن عبدالعزيز مقرن المقرن", "grade": "الثاني المتوسط", "class": 1, "phone": "966553322110"},
            {"id": "1162818197", "name": "نايف فهد ناصر القحطاني", "grade": "الثاني المتوسط", "class": 1, "phone": "966509988776"},
            {"id": "1162981881", "name": "وليد خالد وليد العتيبي", "grade": "الثاني المتوسط", "class": 1, "phone": "966558877665"},
            {"id": "1163112233", "name": "ياسر محمد علي الغامدي", "grade": "الثاني المتوسط", "class": 1, "phone": "966501144778"}
        ],
        2: [
            {"id": "1163888901", "name": "إبراهيم خالد إبراهيم السبيعي", "grade": "الثاني المتوسط", "class": 2, "phone": "966501112233"},
            {"id": "1163999812", "name": "أحمد عبدالله أحمد العتيبي", "grade": "الثاني المتوسط", "class": 2, "phone": "966552223344"},
            {"id": "1164111723", "name": "بدر ناصر بدر القحطاني", "grade": "الثاني المتوسط", "class": 2, "phone": "966503334455"},
            {"id": "1164222634", "name": "تركي فهد تركي الدوسري", "grade": "الثاني المتوسط", "class": 2, "phone": "966554445566"},
            {"id": "1164333545", "name": "جاسم محمد جاسم الشمري", "grade": "الثاني المتوسط", "class": 2, "phone": "966505556677"},
            {"id": "1164444456", "name": "حسام علي حسام الغامدي", "grade": "الثاني المتوسط", "class": 2, "phone": "966556667788"},
            {"id": "1164555367", "name": "خالد سعد خالد الزهراني", "grade": "الثاني المتوسط", "class": 2, "phone": "966507778899"},
            {"id": "1164666278", "name": "راكان سلطان راكان المطيري", "grade": "الثاني المتوسط", "class": 2, "phone": "966558889900"},
            {"id": "1164777189", "name": "زياد وليد زياد الشهري", "grade": "الثاني المتوسط", "class": 2, "phone": "966509990011"},
            {"id": "1164888090", "name": "سعود عبدالعزيز سعود الحربي", "grade": "الثاني المتوسط", "class": 2, "phone": "966550001122"},
            {"id": "1164999001", "name": "سلمان فيصل سلمان العتيبي", "grade": "الثاني المتوسط", "class": 2, "phone": "966501113344"},
            {"id": "1165110912", "name": "عبدالمحسن حمد عبدالمحسن القحطاني", "grade": "الثاني المتوسط", "class": 2, "phone": "966552224455"},
            {"id": "1165221823", "name": "علي حسين علي المالكي", "grade": "الثاني المتوسط", "class": 2, "phone": "966503335566"},
            {"id": "1165332734", "name": "عمر مشاري عمر السهلي", "grade": "الثاني المتوسط", "class": 2, "phone": "966554446677"},
            {"id": "1165443645", "name": "فارس تركي فارس الخالدي", "grade": "الثاني المتوسط", "class": 2, "phone": "966505557788"},
            {"id": "1165554556", "name": "فهد نايف فهد العنزي", "grade": "الثاني المتوسط", "class": 2, "phone": "966556668899"},
            {"id": "1165665467", "name": "ماجد بندر ماجد العتيبي", "grade": "الثاني المتوسط", "class": 1, "phone": "966507779900"},
            {"id": "1165776378", "name": "محمد سامي محمد القحطاني", "grade": "الثاني المتوسط", "class": 2, "phone": "966558880011"},
            {"id": "1165887289", "name": "مشعل بدر مشعل الدوسري", "grade": "الثاني المتوسط", "class": 2, "phone": "966509991122"},
            {"id": "1165998190", "name": "منصور طلال منصور الشمري", "grade": "الثاني المتوسط", "class": 2, "phone": "966550002233"},
            {"id": "1166109091", "name": "ناصر خالد ناصر القحطاني", "grade": "الثاني المتوسط", "class": 2, "phone": "966501114455"},
            {"id": "1166219992", "name": "وليد سلطان وليد الشهري", "grade": "الثاني المتوسط", "class": 2, "phone": "966552225566"},
            {"id": "1166330893", "name": "يوسف أحمد يوسف الغامدي", "grade": "الثاني المتوسط", "class": 2, "phone": "966503336677"}
        ],
        3: [
            {"id": "1166441794", "name": "أحمد خليل أحمد الغامدي", "grade": "الثاني المتوسط", "class": 3, "phone": "966504447788"},
            {"id": "1166552695", "name": "إياد رائد إياد الثبيتي", "grade": "الثاني المتوسط", "class": 3, "phone": "966555558899"},
            {"id": "1166663596", "name": "بندر زياد بندر العتيبي", "grade": "الثاني المتوسط", "class": 3, "phone": "966506669900"},
            {"id": "1166774497", "name": "حسن طارق حسن الشهري", "grade": "الثاني المتوسط", "class": 3, "phone": "966557770011"},
            {"id": "1166885398", "name": "حمزة عادل حمزة الزهراني", "grade": "الثاني المتوسط", "class": 3, "phone": "966508881122"},
            {"id": "1166996299", "name": "ريان فواز ريان القحطاني", "grade": "الثاني المتوسط", "class": 3, "phone": "966559992233"},
            {"id": "1167107200", "name": "سعد ماجد سعد المطيري", "grade": "الثاني المتوسط", "class": 3, "phone": "966500003344"},
            {"id": "1167218101", "name": "سعود هشام سعود الدوسري", "grade": "الثاني المتوسط", "class": 3, "phone": "966551114455"},
            {"id": "1167329002", "name": "سلطان ياسر سلطان الحربي", "grade": "الثاني المتوسط", "class": 3, "phone": "966502225566"},
            {"id": "1167439903", "name": "صالح يوسف صالح الخالدي", "grade": "الثاني المتوسط", "class": 3, "phone": "966553336677"},
            {"id": "1167550804", "name": "طاهر عبدالملك طاهر البقمي", "grade": "الثاني المتوسط", "class": 3, "phone": "966504447799"},
            {"id": "1167661705", "name": "عبدالله إبراهيم عبدالله السبيعي", "grade": "الثاني المتوسط", "class": 3, "phone": "966555558800"},
            {" proposal_id": "1167772606", "id": "1167772606", "name": "عثمان جابر عثمان الفيفي", "grade": "الثاني المتوسط", "class": 3, "phone": "966506669911"},
            {"id": "1167883507", "name": "عزام حامد عزام الشمري", "grade": "الثاني المتوسط", "class": 3, "phone": "966557770022"},
            {"id": "1167994408", "name": "فارس خالد فارس العتيبي", "grade": "الثاني المتوسط", "class": 3, "phone": "966508881133"},
            {"id": "1168105309", "name": "فيصل ذياب فيصل القحطاني", "grade": "الثاني المتوسط", "class": 3, "phone": "966559992244"},
            {"id": "1168216210", "name": "ماجد سالم ماجد الزهراني", "grade": "الثاني المتوسط", "class": 3, "phone": "966500003355"},
            {"id": "1168327111", "name": "محمد سلمان محمد الشهري", "grade": "الثاني المتوسط", "class": 3, "phone": "966551114466"},
            {"id": "1168438012", "name": "يزيد شرف يزيد الغامدي", "grade": "الثاني المتوسط", "class": 3, "phone": "966502225577"}
        ]
    },
    "الثالث المتوسط": {
        1: [
            {"id": "1151122334", "name": "أحمد بندر أحمد القحطاني", "grade": "الثالث المتوسط", "class": 1, "phone": "966501118899"},
            {"id": "1152233445", "name": "إبراهيم تركي إبراهيم العتيبي", "grade": "الثالث المتوسط", "class": 1, "phone": "966552229900"},
            {"id": "1153344556", "name": "باسم ثامر باسم الدوسري", "grade": "الثالث المتوسط", "class": 1, "phone": "966503330011"},
            {"id": "1154455667", "name": "تميم جابر تميم المطيري", "grade": "الثالث المتوسط", "class": 1, "phone": "966554441122"},
            {"id": "1155566778", "name": "ثامر حامد ثامر الحربي", "grade": "الثالث المتوسط", "class": 1, "phone": "966505552233"},
            {"id": "1156677889", "name": "جاسم خالد جاسم الشهري", "grade": "الثالث المتوسط", "class": 1, "phone": "966556663344"},
            {"id": "1157788990", "name": "حسام رائد حسام الزهراني", "grade": "الثالث المتوسط", "class": 1, "phone": "966507774455"},
            {"id": "1158899001", "name": "راكان زياد راكان الغامدي", "grade": "الثالث المتوسط", "class": 1, "phone": "966558885566"},
            {"id": "1159900112", "name": "زياد سالم زياد العتيبي", "grade": "الثالث المتوسط", "class": 1, "phone": "966509996677"},
            {"id": "1160011223", "name": "سعود سعد سعود القحطاني", "grade": "الثالث المتوسط", "class": 1, "phone": "966550007788"},
            {"id": "1161122334", "name": "سلمان سلطان سلمان الدوسري", "grade": "الثالث المتوسط", "class": 1, "phone": "966501118800"},
            {"id": "1162233445", "name": "عبدالعزيز طارق عبدالعزيز الحربي", "grade": "الثالث المتوسط", "class": 1, "phone": "966552229911"},
            {"id": "1163344556", "name": "عبدالله عادل عبدالله الشهري", "grade": "الثالث المتوسط", "class": 1, "phone": "966503330022"},
            {"id": "1164455667", "name": "على فهد علي الزهراني", "grade": "الثالث المتوسط", "class": 1, "phone": "966554441133"},
            {"id": "1165566778", "name": "عمر فيصل عمر الغامدي", "grade": "الثالث المتوسط", "class": 1, "phone": "966505552244"},
            {"id": "1166677889", "name": "فارس ماجد فارس العتيبي", "grade": "الثالث المتوسط", "class": 1, "phone": "966556663355"},
            {"id": "1167788990", "name": "فهد محمد فهد القحطاني", "grade": "الثالث المتوسط", "class": 1, "phone": "966507774466"},
            {"id": "1168899001", "name": "فيصل مشاري فيصل الدوسري", "grade": "الثالث المتوسط", "class": 1, "phone": "966558885577"},
            {"id": "1169900112", "name": "ماجد نايف ماجد المطيري", "grade": "الثالث المتوسط", "class": 1, "phone": "966509996688"},
            {"id": "1170011223", "name": "محمد وليد محمد الحربي", "grade": "الثالث المتوسط", "class": 1, "phone": "966550007799"},
            {"id": "1171122334", "name": "مشاري ياسر مشاري الشهري", "grade": "الثالث المتوسط", "class": 1, "phone": "966501118811"},
            {"id": "1172233445", "name": "يزيد يوسف يزيد الزهراني", "grade": "الثالث المتوسط", "class": 1, "phone": "966552229922"}
        ],
        2: [
            {"id": "1141122334", "name": "أنس أحمد أنس العتيبي", "grade": "الثالث المتوسط", "class": 2, "phone": "966503331122"},
            {"id": "1142233445", "name": "بشر بدر بشر القحطاني", "grade": "الثالث المتوسط", "class": 2, "phone": "966554442233"},
            {"id": "1143344556", "name": "تركي تركي تركي الدوسري", "grade": "الثالث المتوسط", "class": 2, "phone": "966505553344"},
            {"id": "1144455667", "name": "ثامر ثامر ثامر المطيري", "grade": "الثالث المتوسط", "class": 2, "phone": "966556664455"},
            {"id": "1145566778", "name": "جابر جاسم جابر الحربي", "grade": "الثالث المتوسط", "class": 2, "phone": "966507775566"},
            {"id": "1146677889", "name": "حاتم حسام حاتم الشهري", "grade": "الثالث المتوسط", "class": 2, "phone": "966558886677"},
            {"id": "1147788990", "name": "خالد خالد خالد الزهراني", "grade": "الثالث المتوسط", "class": 2, "phone": "966509997788"},
            {"id": "1148899001", "name": "رائد راكان رائد الغامدي", "grade": "الثالث المتوسط", "class": 2, "phone": "966550008899"},
            {"id": "1149900112", "name": "زياد زياد زياد العتيبي", "grade": "الثالث المتوسط", "class": 2, "phone": "966501119900"},
            {"id": "1150011223", "name": "سعد سعود سعد القحطاني", "grade": "الثالث المتوسط", "class": 2, "phone": "966552220011"},
            {"id": "1151122335", "name": "سلطان سلمان سلطان الدوسري", "grade": "الثالث المتوسط", "class": 2, "phone": "966503331122"},
            {"id": "1152233446", "name": "سهيل طارق سهيل الحربي", "grade": "الثالث المتوسط", "class": 2, "phone": "966554442233"},
            {"id": "1153344557", "name": "صالح عادل صالح الشهري", "grade": "الثالث المتوسط", "class": 2, "phone": "966505553344"},
            {"id": "1154455668", "name": "طارق فهد طارق الزهراني", "grade": "الثالث المتوسط", "class": 2, "phone": "966556664455"},
            {"id": "1155566779", "name": "عبدالمجيد فيصل عبدالمجيد الغامدي", "grade": "الثالث المتوسط", "class": 2, "phone": "966507775566"},
            {"id": "1156677890", "name": "فراس ماجد فراس العتيبي", "grade": "الثالث المتوسط", "class": 2, "phone": "966558886677"},
            {"id": "1157788991", "name": "مالك محمد مالك القحطاني", "grade": "الثالث المتوسط", "class": 2, "phone": "966509997788"},
            {"id": "1158899002", "name": "مؤيد مشاري مؤيد الدوسري", "grade": "الثالث المتوسط", "class": 2, "phone": "966550008899"},
            {"id": "1159900113", "name": "نايف نايف نايف المطيري", "grade": "الثالث المتوسط", "class": 2, "phone": "966501119900"},
            {"id": "1160011224", "name": "وليد وليد وليد الحربي", "grade": "الثالث المتوسط", "class": 2, "phone": "966552220011"},
            {"id": "1161122335", "name": "ياسر ياسر ياسر الشهري", "grade": "الثالث المتوسط", "class": 2, "phone": "966503331122"}
        ],
        3: [
            {"id": "1131122334", "name": "أصيل أحمد أصيل العتيبي", "grade": "الثالث المتوسط", "class": 3, "phone": "966504442233"},
            {"id": "1132233445", "name": "براء بدر براء القحطاني", "grade": "الثالث المتوسط", "class": 3, "phone": "966555553344"},
            {"id": "1133344556", "name": "تامر تركي تامر الدوسري", "grade": "الثالث المتوسط", "class": 3, "phone": "966506664455"},
            {"id": "1134455667", "name": "جلال جاسم جلال المطيري", "grade": "الثالث المتوسط", "class": 3, "phone": "966557775566"},
            {"id": "1135566778", "name": "حامد حسام حامد الحربي", "grade": "الثالث المتوسط", "class": 3, "phone": "966508886677"},
            {"id": "1136677889", "name": "خليل خالد خليل الشهري", "grade": "الثالث المتوسط", "class": 3, "phone": "966559997788"},
            {"id": "1137788990", "name": "دانيال راكان دانيال الزهراني", "grade": "الثالث المتوسط", "class": 3, "phone": "966500008899"},
            {"id": "1138899001", "name": "رامي زياد رامي الغامدي", "grade": "الثالث المتوسط", "class": 3, "phone": "966551119900"},
            {"id": "1139900112", "name": "سامر سعود سامر العتيبي", "grade": "الثالث المتوسط", "class": 3, "phone": "966502220011"},
            {"id": "1140011223", "name": "سراج سلمان سراج القحطاني", "grade": "الثالث المتوسط", "class": 3, "phone": "966553331122"},
            {"id": "1141122335", "name": "شرف طارق شرف الدوسري", "grade": "الثالث المتوسط", "class": 3, "phone": "966504442233"},
            {"id": "1142233446", "name": "صفوان عادل صفوان الحربي", "grade": "الثالث المتوسط", "class": 3, "phone": "966555553344"},
            {"id": "1143344557", "name": "ضياء فهد ضياء الشهري", "grade": "الثالث المتوسط", "class": 3, "phone": "966506664455"},
            {"id": "1144455668", "name": "عاصم فيصل عاصم الزهراني", "grade": "الثالث المتوسط", "class": 3, "phone": "966557775566"},
            {"id": "1145566779", "name": "عمار ماجد عمار الغامدي", "grade": "الثالث المتوسط", "class": 3, "phone": "966508886677"},
            {"id": "1146677890", "name": "فادي محمد فادي العتيبي", "grade": "الثالث المتوسط", "class": 3, "phone": "966559997788"},
            {"id": "1147788991", "name": "قصي مشاري قصي القحطاني", "grade": "الثالث المتوسط", "class": 3, "phone": "966500008899"},
            {"id": "1148899002", "name": "كريم نايف كريم الدوسري", "grade": "الثالث المتوسط", "class": 3, "phone": "966551119900"},
            {"id": "1149900113", "name": "لؤي وليد لؤي المطيري", "grade": "الثالث المتوسط", "class": 3, "phone": "966502220011"},
            {"id": "1150011224", "name": "مؤمن ياسر مؤمن الحربي", "grade": "الثالث المتوسط", "class": 3, "phone": "966553331122"}
        ]
    }
}

### =========================================================
### 5. إعدادات الصفحة والتنسيقات المخصصة الشاملة (CSS & Print Setup)
### =========================================================
st.set_page_config(
    page_title="منصة مدرسة الثغر النموذجية - تقارير الإتقان والرسائل",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');

html, body, .stApp {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl !important;
    text-align: right !important;
    background-color: #f8fafc;
}

/* الحفاظ على خط الأيقونات لتجنب تداخل النصوص مثل keyboard_arrow */
[data-testid="stIcon"], [class*="material-symbols"], [class*="Material"], [class*="icon"], i {
    font-family: 'Material Symbols Outlined', 'Material Icons' !important;
}
.stApp {
    background-color: #F8FAFC;
}
.national-day-banner {
    background: linear-gradient(135deg, #046A38 0%, #004B23 100%);
    color: #FFFFFF;
    padding: 18px;
    border-radius: 12px;
    text-align: center;
    margin-bottom: 20px;
    box-shadow: 0 4px 12px rgba(4, 106, 56, 0.2);
    border: 2px solid #D4AF37;
}
.national-day-title {
    font-size: 22px;
    font-weight: 800;
    color: #FFFFFF;
    margin-bottom: 4px;
}
.national-day-sub {
    font-size: 14px;
    color: #F3F4F6;
    font-weight: 600;
}
.status-badge-ok {
    background-color: #DCFCE7;
    color: #15803D;
    padding: 6px 12px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 13px;
    display: inline-block;
}
.status-badge-off {
    background-color: #FEE2E2;
    color: #B91C1C;
    padding: 6px 12px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 13px;
    display: inline-block;
}
.student-card {
    background: white;
    padding: 12px 16px;
    border-radius: 8px;
    border-right: 4px solid #1E3C72;
    margin-bottom: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
</style>
""", unsafe_allow_html=True)

/* شارات حالة الاتصال */
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

/* حاوية التقرير القابل للطباعة على الشاشة وفي أوراق A4 */
.report-paper {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 10px;
    padding: 25px;
    margin-top: 15px;
    margin-bottom: 25px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}

.report-header-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 15px;
    border-bottom: 2px solid #006C35;
    padding-bottom: 10px;
}
.report-header-table td {
    border: none !important;
    padding: 4px 8px !important;
    vertical-align: middle;
}

/* جداول التقارير المطبوعة */
table.printable-table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin-top: 10px !important;
    font-size: 13px !important;
    direction: rtl !important;
}
table.printable-table th {
    background-color: #006C35 !important;
    color: #ffffff !important;
    padding: 10px 8px !important;
    text-align: center !important;
    font-weight: bold !important;
    border: 1px solid #006C35 !important;
}
table.printable-table td {
    border: 1px solid #d1d5db !important;
    padding: 8px 6px !important;
    text-align: center !important;
    color: #1f2937 !important;
    vertical-align: middle !important;
}
table.printable-table tr:nth-child(even) {
    background-color: #f8fafc !important;
}

/* قواعد الطباعة الشاملة عند الضغط على زر الطباعة @media print */
@media print {
    /* إخفاء واجهة Streamlit والمقابض والتنبيهات والتبويبات عند الطباعة */
    section[data-testid="stSidebar"], 
    header[data-testid="stHeader"], 
    footer, 
    .stButton, 
    .no-print,
    [data-testid="stSelectbox"],
    [data-testid="stRadio"],
    [data-testid="stTab"],
    div[data-testid="stToolbar"],
    .stTabs,
    iframe {
        display: none !important;
    }
    
    /* عند طباعة التقرير الشامل: إخفاء تقرير الصف */
    body.mode-print-full .print-class-section {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        overflow: hidden !important;
    }
    body.mode-print-full .print-full-section {
        display: block !important;
        visibility: visible !important;
    }

    /* عند طباعة تقرير الصف: إخفاء التقرير الشامل */
    body.mode-print-class .print-full-section {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        overflow: hidden !important;
    }
    body.mode-print-class .print-class-section {
        display: block !important;
        visibility: visible !important;
    }

    @page {
        size: A4 portrait;
        margin: 8mm 10mm 8mm 10mm;
    }
    
    body, .stApp, .main, .block-container {
        background-color: white !important;
        color: black !important;
        padding: 0 !important;
        margin: 0 !important;
        width: 100% !important;
        overflow: visible !important;
    }
    
    .report-paper {
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        margin: 0 !important;
        width: 100% !important;
    }
    
    table.printable-table {
        width: 100% !important;
        border-collapse: collapse !important;
        page-break-inside: auto;
    }
    table.printable-table tr {
        page-break-inside: avoid;
        page-break-after: auto;
    }
    table.printable-table th {
        background-color: #006C35 !important;
        color: white !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }
    table.printable-table tr:nth-child(even) {
        background-color: #f1f5f9 !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
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

with st.sidebar.expander("💬 إعدادات WhatsApp Direct API (إرسال تلقائي دون فتح التطبيق)"):
    wa_instance = st.text_input("Instance ID:", value="", key="wa_inst_inp")
    wa_token = st.text_input("API Token:", value="", type="password", key="wa_tok_inp")
    st.caption("💡 باستخدام هذه الإعدادات، يتم إرسال رسائل الواتساب مباشرة للطلاب في الخلفية فور الضغط على زر الإرسال بنقرة واحدة.")

with st.sidebar.expander("📱 إعدادات Mora SMS"):
    mora_user = st.text_input("اسم المستخدم / الرقم:", value="966508634881", key="mora_u")
    mora_pass = st.text_input("كلمة المرور:", value="THA@0508634881", type="password", key="mora_p")
    mora_sender = st.text_input("اسم المرسل المعتمد:", value="THAGHR-S", key="mora_s")
    mora_otp = st.text_input("كود التحقق / OTP (إذا طلب):", value="", key="mora_otp_input")

st.sidebar.markdown("---")
page = st.sidebar.radio("اختر الصفحة:", ["📝 صفحة الرصد", "🏫 إدارة المدرسة وتقارير أولياء الأمور"])
st.sidebar.markdown("---")
st.sidebar.markdown("<div style='text-align: center; color: #006C35; font-weight: bold; font-size: 13px; background-color: #e6f4ea; padding: 8px; border-radius: 8px; border: 1px solid #c3e6cb;'>✨ تصميم أ/ محمد سامي السعيد</div>", unsafe_allow_html=True)

### =========================================================
### الصفحة الأولى: صفحة الرصد (RECORDING SHEET)
### =========================================================
if page == "📝 صفحة الرصد":
    # الترويسة السعودية باللون الأخضر
    render_saudi_header("صفحة رصد درجات الإتقان الأسبوعية")
    
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

        c1, c2, c3, c4 = st.columns([1, 3, 2, 2])
        with c1:
            st.write(f"**#{idx+1}**")
        with c2:
            st.write(f"**{student['name']}**\n*(هوية: {sid})*")
        with c3:
            sc_val = st.number_input(
                f"الدرجة ({student['name']})",
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
    # الترويسة السعودية باللون الأخضر
    render_saudi_header("إدارة المدرسة وإرسال التقارير والطباعة")

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

                final_score = sc if (sc is not None and is_abs == 0) else 100.0

                msg = generate_parent_message(s_item["name"], final_score if is_abs == 0 else None, is_abs == 1)

                row_dict = {
                    "id": sid,
                    "name": s_item["name"],
                    "grade": g_name,
                    "class": c_num,
                    "phone": p_num,
                    "score": final_score,
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
        print_button(label="🖨️ طباعة تقرير الأسبوع الشامل", button_id="print_full_week", target_mode="mode-print-full")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🔴 أقل من 50%", f"{len(cat_red)} طالب")
    m2.metric("🔵 50% - 75%", f"{len(cat_blue)} طالب")
    m3.metric("🟢 76% - 100%", f"{len(cat_green)} طالب")
    m4.metric("⚪ الغياب", f"{len(cat_gray)} طالب")

    # توليد التقرير الشامل بصيغة HTML جاهزة وموثقة للطباعة والعرض
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
    <div class="report-paper print-full-section">
        <table class="report-header-table">
            <tr>
                <td style="width: 30%; text-align: right; font-size: 12px; line-height: 1.4;">
                    <strong>المملكة العربية السعودية</strong><br/>
                    وزارة التعليم<br/>
                    إدارة التعليم بمحافظة الرياض<br/>
                    <strong>مدرسة الثغر النموذجية الأهلية المتوسطة</strong>
                </td>
                <td style="width: 40%; text-align: center;">
                    <h3 style="margin:0; color:#006C35; font-family:'Cairo'; font-weight:bold;">📋 التقرير الشامل لدرجات الإتقان الأسبوعية</h3>
                    <div style="font-size: 13px; color:#475569; margin-top:4px;">{selected_term} - {selected_week}</div>
                </td>
                <td style="width: 30%; text-align: left; font-size: 12px; line-height: 1.4;">
                    <strong>تاريخ التقرير:</strong> {today_str}<br/>
                    <strong>إجمالي الطلاب:</strong> {len(all_students_flat)} طالب<br/><strong>تصميم:</strong> أ/ محمد سامي السعيد<br/>
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
                <td style="width: 33%; border: none;">وكيل شؤون الطلاب:<br/><br/>صالح بن عبدالله الدعجاني </td>
                <td style="width: 33%; border: none;">وكيل الشؤون التعليمية:<br/><br/>محمد مبروك السيد </td>
                <td style="width: 34%; border: none;">مدير المدرسة:<br/><br/>إبراهيم بن موسى التميمي </td>
            </tr>
        </table>
    </div>
    """

    render_clean_html(full_report_html)

    st.markdown("---")

    # ---------------------------------------------------------
    # 2. قسم طباعة تقرير الصف الدراسي المحدد
    # ---------------------------------------------------------
    st.markdown("### 🏫 تقرير الصف وإتقان الدرجات (طباعة حسب الصف)")
    
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
        print_button(label=f"🖨️ طباعة تقرير {selected_rep_grade} ({selected_rep_class})", button_id="print_class_rep", target_mode="mode-print-class")

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
        <div class="report-paper print-class-section">
            <table class="report-header-table">
                <tr>
                    <td style="width: 30%; text-align: right; font-size: 12px; line-height: 1.4;">
                        <strong>المملكة العربية السعودية</strong><br/>
                        وزارة التعليم<br/>
                        إدارة التعليم بمحافظة الرياض<br/>
                        <strong>مدرسة الثغر النموذجية الأهلية المتوسطة</strong>
                    </td>
                    <td style="width: 40%; text-align: center;">
                        <h3 style="margin:0; color:#006C35; font-family:'Cairo'; font-weight:bold;">🏫 تقرير تقييم الصف الدراسي</h3>
                        <div style="font-size: 14px; color:#1e293b; font-weight:bold; margin-top:4px;">{selected_rep_grade} - فصل ({selected_rep_class})</div>
                        <div style="font-size: 12px; color:#64748b;">{selected_term} - {selected_week}</div>
                    </td>
                    <td style="width: 30%; text-align: left; font-size: 12px; line-height: 1.4;">
                        <strong>تاريخ التقرير:</strong> {today_str}<br/>
                        <strong>عدد طلاب الفصل:</strong> {len(class_students)} طالب<br/><strong>تصميم:</strong> أ/ محمد سامي السعيد
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
                with st.expander(f"👤 {item['name']} ── {item['grade']} (فصل {item['class']}) ── جوال ولي الأمر: {item['phone']}"):
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
