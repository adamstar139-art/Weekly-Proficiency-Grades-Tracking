import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import io
import copy
import urllib.parse
import requests
import streamlit.components.v1 as components

##### =========================================================
##### 0. ربط قاعدة البيانات السحابية الدائمة (Supabase Cloud)
##### =========================================================
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
        key = st.secrets.get("key") or st.secrets.get("SUPABASE_KEY") or st.secrets.get("anon_key")
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

##### =========================================================
##### 1. دالة الترويسة السعودية باللون الأخضر (Saudi Identity Header)
##### =========================================================
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

##### =========================================================
##### 2. دالة زر/أيقونة الطباعة المباشرة (Print Button Component)
##### =========================================================
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

##### =========================================================
##### 3. خدمات WhatsApp Direct API و Mora SMS
##### =========================================================
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

##### =========================================================
##### 4. قاعدة بيانات الطلاب الكاملة (جميع المراحل والشعب - 167 طالب)
##### =========================================================
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
            {"id": "1167893740", "name": "عبدالرحمن ربيع جابر خبراني", "grade": "الثاني المتوسط", "class": 1, "phone": "966535924655"},
            {"id": "1159740032", "name": "عبدالعزيز سعود بن فهد العتيبي", "grade": "الثاني المتوسط", "class": 1, "phone": "966544155592"},
            {"id": "1164747436", "name": "عبدالمجيد بن محمد بن مسعود ال عايض القحطاني", "grade": "الثاني المتوسط", "class": 1, "phone": "966555275591"},
            {"id": "1160901128", "name": "فيصل بن عبدالله بن سعود بن عبدالعزيز الجميعة", "grade": "الثاني المتوسط", "class": 1, "phone": "966554949948"},
            {"id": "1162168627", "name": "مبارك صالح مبارك هليل", "grade": "الثاني المتوسط", "class": 1, "phone": "966553663819"},
            {"id": "1163212978", "name": "محمد بن عبدالله بن حمد بن ناصر بن عمران", "grade": "الثاني المتوسط", "class": 1, "phone": "966544779170"},
            {"id": "1161858301", "name": "محمد عبدالمحسن ناصر الحزام", "grade": "الثاني المتوسط", "class": 1, "phone": "966505264075"},
            {"id": "1175902442", "name": "محمد فايز عبدالرحمن بن يوسف", "grade": "الثاني المتوسط", "class": 1, "phone": "966505482728"},
            {"id": "1165686179", "name": "مشاري سلطان سالم الشمراني", "grade": "الثاني المتوسط", "class": 1, "phone": "966553908888"},
            {"id": "1166040053", "name": "معاذ عبدالله سعود العريفي", "grade": "الثاني المتوسط", "class": 1, "phone": "966505473192"},
            {"id": "1167081981", "name": "ناصر حسين محمد ال جبران", "grade": "الثاني المتوسط", "class": 1, "phone": "966550004952"},
            {"id": "1171868639", "name": "وائل بن عبدالله بن عامر علي ال عبيد الغامدي", "grade": "الثاني المتوسط", "class": 1, "phone": "966548888663"},
            {"id": "1163191222", "name": "يزيد بن طارق بن علي الحديثي", "grade": "الثاني المتوسط", "class": 1, "phone": "966554084040"}
        ],
        2: [
            {"id": "1166753291", "name": "ابراهيم بن مبارك بن راشد بن عبدالرحمن السبعان آل موينع", "grade": "الثاني المتوسط", "class": 2, "phone": "966555212896"},
            {"id": "1163613795", "name": "ابراهيم ياسر ابراهيم الحلوي", "grade": "الثاني المتوسط", "class": 2, "phone": "966502220990"},
            {"id": "1167148251", "name": "حامد بن محمد بن حامد شباط", "grade": "الثاني المتوسط", "class": 2, "phone": "966595001616"},
            {"id": "1164599977", "name": "حسام حسن محمد الشهري", "grade": "الثاني المتوسط", "class": 2, "phone": "966557775278"},
            {"id": "1169057351", "name": "خالد تركي عايض القحطاني", "grade": "الثاني المتوسط", "class": 2, "phone": "966536201378"},
            {"id": "1164120600", "name": "خالد داود بن عابد الحارثي", "grade": "الثاني المتوسط", "class": 2, "phone": "966501076244"},
            {"id": "1165839455", "name": "سطام عبدالعزيز عبدالله العريفي", "grade": "الثاني المتوسط", "class": 2, "phone": "966599791658"},
            {"id": "1163778960", "name": "سعود سلطان بن هليل العتيبي", "grade": "الثاني المتوسط", "class": 2, "phone": "966554820082"},
            {"id": "1166582989", "name": "طلال محمد منير المهدرس", "grade": "الثاني المتوسط", "class": 2, "phone": "966531167666"},
            {"id": "1165143783", "name": "عبدالكريم مساعد عبدالعزيز الهزاع", "grade": "الثاني المتوسط", "class": 2, "phone": "966503210252"},
            {"id": "1164277830", "name": "عبداللطيف ابراهيم محمد الطمرة", "grade": "الثاني المتوسط", "class": 2, "phone": "966505404365"},
            {"id": "1165495258", "name": "عبدالله سامي سعد الحوشاني", "grade": "الثاني المتوسط", "class": 2, "phone": "966555219086"},
            {"id": "013609088", "name": "علي احمد علي عقيل", "grade": "الثاني المتوسط", "class": 2, "phone": "966546000184"},
            {"id": "1164825802", "name": "عمر بن سعد بن هلال الشبانات", "grade": "الثاني المتوسط", "class": 2, "phone": "966505213725"},
            {"id": "1163537838", "name": "فارس مشعل عبدالله بن موينع", "grade": "الثاني المتوسط", "class": 2, "phone": "966555200719"},
            {"id": "1162761306", "name": "فهد عيسى محمد العيسى", "grade": "الثاني المتوسط", "class": 2, "phone": "966554499908"},
            {"id": "1164997858", "name": "مازن خالد دخيل المطيري", "grade": "الثاني المتوسط", "class": 2, "phone": "966501110052"},
            {"id": "2348937422", "name": "مازن رفعت محمد حاج النيل", "grade": "الثاني المتوسط", "class": 2, "phone": "966501331089"},
            {"id": "1172720045", "name": "محمد بن علي محسن العثيميني", "grade": "الثاني المتوسط", "class": 2, "phone": "966506256254"},
            {"id": "1166803245", "name": "نايف بن بندر بن خلفان العلوي", "grade": "الثاني المتوسط", "class": 2, "phone": "966532225560"},
            {"id": "1165668417", "name": "نواف عبدالعزيز عبدالله المرزوق", "grade": "الثاني المتوسط", "class": 2, "phone": "966501100076"},
            {"id": "1164387977", "name": "هادي سلطان هادي القحطاني", "grade": "الثاني المتوسط", "class": 2, "phone": "966505936192"},
            {"id": "1165002153", "name": "يزيد بن حسين بن متعب بن محمد كعكم", "grade": "الثاني المتوسط", "class": 2, "phone": "966550117805"}
        ],
        3: [
            {"id": "1166911709", "name": "ثامر عمر ابراهيم عثمان", "grade": "الثاني المتوسط", "class": 3, "phone": "966538384444"},
            {"id": "008464815", "name": "جهاد فارس عبدالقادر حناوي", "grade": "الثاني المتوسط", "class": 3, "phone": "966562674178"},
            {"id": "1164830562", "name": "خالد محمد عبدالكريم الخفاجي", "grade": "الثاني المتوسط", "class": 3, "phone": "966533074601"},
            {"id": "1188914319", "name": "سعد ابن مسفر بن سعد القحطاني", "grade": "الثاني المتوسط", "class": 3, "phone": "966508057005"},
            {"id": "1165099498", "name": "سعود بن عبدالله بن سعود السحامي", "grade": "الثاني المتوسط", "class": 3, "phone": "966500650867"},
            {"id": "1167770468", "name": "سعود ناصر سيف العريفي", "grade": "الثاني المتوسط", "class": 3, "phone": "966505474606"},
            {"id": "2344500760", "name": "سعيد محمد باوزير", "grade": "الثاني المتوسط", "class": 3, "phone": "966553435135"},
            {"id": "1164983874", "name": "طلال بن فهد بن عطيه بالحكم الزهراني", "grade": "الثاني المتوسط", "class": 3, "phone": "966567837159"},
            {"id": "2362260263", "name": "عبدالرحمن احمد جاسم الحمدي", "grade": "الثاني المتوسط", "class": 3, "phone": "966503432054"},
            {"id": "1167153434", "name": "عبدالعزيز ماجد راشد الزير", "grade": "الثاني المتوسط", "class": 3, "phone": "966500933390"},
            {"id": "1164512566", "name": "عبدالعزيز وليد ناصر بن سعران", "grade": "الثاني المتوسط", "class": 3, "phone": "966556660555"},
            {"id": "1167267341", "name": "عبدالله بن بندر بن فهد المسيحل", "grade": "الثاني المتوسط", "class": 3, "phone": "966500155334"},
            {"id": "2358022958", "name": "عز الدين احمد محمد سعد", "grade": "الثاني المتوسط", "class": 3, "phone": "966561317507"},
            {"id": "1167515020", "name": "عزام خالد شلهوب بن شلهوب", "grade": "الثاني المتوسط", "class": 3, "phone": "966506404016"},
            {"id": "1164747014", "name": "عزام فهد احمد صلوي", "grade": "الثاني المتوسط", "class": 3, "phone": "966555796951"},
            {"id": "4533080448", "name": "عمر وليد ياسين درويش علي", "grade": "الثاني المتوسط", "class": 3, "phone": "966557790508"},
            {"id": "1163397811", "name": "فارس ابن محمد بن سالم بن نويشي الوهبي الحربي", "grade": "الثاني المتوسط", "class": 3, "phone": "966583228278"},
            {"id": "1166629798", "name": "يزيد بن حمد بن مترك بن محمد ال مسعود القحطاني", "grade": "الثاني المتوسط", "class": 3, "phone": "966505203795"},
            {"id": "1167371093", "name": "يوسف عايد عواد البلوي", "grade": "الثاني المتوسط", "class": 3, "phone": "966531066289"}
        ]
    },
    "الثالث المتوسط": {
        1: [
            {"id": "1158966166", "name": "أاصيل ناصر بن محمد مذكور", "grade": "الثالث المتوسط", "class": 1, "phone": "966552149044"},
            {"id": "1162308223", "name": "خالد محمد مسدف معافا", "grade": "الثالث المتوسط", "class": 1, "phone": "966552680201"},
            {"id": "1161109093", "name": "راكان بن عبدالله بن سالم اليافعي", "grade": "الثالث المتوسط", "class": 1, "phone": "966504234219"},
            {"id": "1160805899", "name": "زياد احمد بن علي اللحيد", "grade": "الثالث المتوسط", "class": 1, "phone": "966504432362"},
            {"id": "1160267124", "name": "سطام محمد سعود الدوسري", "grade": "الثالث المتوسط", "class": 1, "phone": "966555260669"},
            {"id": "1163270869", "name": "سلطان احمد صالح الفنتوخ", "grade": "الثالث المتوسط", "class": 1, "phone": "966555242266"},
            {"id": "1161085236", "name": "ضاري صالح مهنا العازمي", "grade": "الثالث المتوسط", "class": 1, "phone": "966531111140"},
            {"id": "1160585624", "name": "عبدالعزيز عبدالله شراز المالكي", "grade": "الثالث المتوسط", "class": 1, "phone": "966556999627"},
            {"id": "1160050678", "name": "عبدالعزيز عبدالله عايض الاسمري", "grade": "الثالث المتوسط", "class": 1, "phone": "966555992269"},
            {"id": "1161021314", "name": "عبدالله عبيد عبدالله العتيبي", "grade": "الثالث المتوسط", "class": 1, "phone": "966597882020"},
            {"id": "1160857700", "name": "عبدالله فهد جلوي سالم الشرعي", "grade": "الثالث المتوسط", "class": 1, "phone": "966555457732"},
            {"id": "2502333723", "name": "عماد الدين اسلام محمد دراز", "grade": "الثالث المتوسط", "class": 1, "phone": "966556124553"},
            {"id": "1161418593", "name": "فهد عبدالرحمن فهد العتيبي", "grade": "الثالث المتوسط", "class": 1, "phone": "966552270402"},
            {"id": "1163074592", "name": "فيصل بن عبدالمحسن بن عايض العصيمي العتيبي", "grade": "الثالث المتوسط", "class": 1, "phone": "966505552320"},
            {"id": "1171918236", "name": "مازن خالد عبدربه الزهراني", "grade": "الثالث المتوسط", "class": 1, "phone": "966540707365"},
            {"id": "1158815876", "name": "محمد سلطان عبدالعزيز العيد", "grade": "الثالث المتوسط", "class": 1, "phone": "966503167770"},
            {"id": "1166075653", "name": "محمد مقعد ساير العتيبي", "grade": "الثالث المتوسط", "class": 1, "phone": "966536655992"},
            {"id": "1160693949", "name": "مشاري ابراهيم عبداللطيف المغري", "grade": "الثالث المتوسط", "class": 1, "phone": "966542744245"},
            {"id": "1160803878", "name": "مشاري علي موسى عقيلي", "grade": "الثالث المتوسط", "class": 1, "phone": "966502259722"},
            {"id": "1161661846", "name": "مهند عبدالله فهد الزكري", "grade": "الثالث المتوسط", "class": 1, "phone": "966558794720"},
            {"id": "1159404795", "name": "نواف وليد حمد الشعالان", "grade": "الثالث المتوسط", "class": 1, "phone": "966555798074"},
            {"id": "1168385894", "name": "يوسف نايف مقعد العتيبي", "grade": "الثالث المتوسط", "class": 1, "phone": "966505290037"}
        ],
        2: [
            {"id": "1156933093", "name": "تركي عبدالعزيز عبدالله المرزوق", "grade": "الثالث المتوسط", "class": 2, "phone": "966501100076"},
            {"id": "1160223317", "name": "تركي عثمان عبدالعزيز العثمان", "grade": "الثالث المتوسط", "class": 2, "phone": "966505226153"},
            {"id": "1159683497", "name": "راشد احمد فهد ال سعيد", "grade": "الثالث المتوسط", "class": 2, "phone": "966555992829"},
            {"id": "2310646332", "name": "راكان ابراهيم محمد ديوان", "grade": "الثالث المتوسط", "class": 2, "phone": "966500030732"},
            {"id": "1161397599", "name": "ريان ناصر عبدالرحمن المرشود", "grade": "الثالث المتوسط", "class": 2, "phone": "966550666662"},
            {"id": "1163112129", "name": "صالح بن ممدوح بن صالح بن خالد الجويعي", "grade": "الثالث المتوسط", "class": 2, "phone": "966549887719"},
            {"id": "2508581135", "name": "عبد الرحمن محمد صلاح السيد بدر الدين", "grade": "الثالث المتوسط", "class": 2, "phone": "966507652707"},
            {"id": "1162188872", "name": "عبدالعزيز تركي عبدالعزيز اللهيم", "grade": "الثالث المتوسط", "class": 2, "phone": "966505256806"},
            {"id": "1161340763", "name": "عبدالعزيز عبدالمحسن فهد بن بديع", "grade": "الثالث المتوسط", "class": 2, "phone": "966554457163"},
            {"id": "1171845140", "name": "عبدالله متعب بن عبدالرحمن الجبرين", "grade": "الثالث المتوسط", "class": 2, "phone": "966559898559"},
            {"id": "1159200318", "name": "عبدالمحسن طارق بن عبدالرحمن العروان", "grade": "الثالث المتوسط", "class": 2, "phone": "966506291294"},
            {"id": "1162454266", "name": "عمر فهد محمد السقامي", "grade": "الثالث المتوسط", "class": 2, "phone": "966564234552"},
            {"id": "1165152107", "name": "فيصل محمد صالح الفنتوخ", "grade": "الثالث المتوسط", "class": 2, "phone": "966556488802"},
            {"id": "1162325722", "name": "ماجد فهد عبدالعزيز الكثيري", "grade": "الثالث المتوسط", "class": 2, "phone": "966557609015"},
            {"id": "1162461857", "name": "محمد خالد محمد بن مشرف", "grade": "الثالث المتوسط", "class": 2, "phone": "966551777559"},
            {"id": "1161288897", "name": "محمد سعد بن محمد العيشان", "grade": "الثالث المتوسط", "class": 2, "phone": "966504217660"},
            {"id": "1156334813", "name": "محمد عبدالعزيز محمد الخالدي", "grade": "الثالث المتوسط", "class": 2, "phone": "966500091387"},
            {"id": "1162044851", "name": "مهند ماجد علي كعبي", "grade": "الثالث المتوسط", "class": 2, "phone": "966533313738"},
            {"id": "1158021137", "name": "ناصر محمد عبدالله الزريعي", "grade": "الثالث المتوسط", "class": 2, "phone": "966505231121"},
            {"id": "1161363443", "name": "نواف سعد بن علي القاسم", "grade": "الثالث المتوسط", "class": 2, "phone": "966504200199"},
            {"id": "1162274086", "name": "ياسر تركي اسماعيل مسملي", "grade": "الثالث المتوسط", "class": 2, "phone": "966504261855"}
        ],
        3: [
            {"id": "1163525544", "name": "ثامر وليد بن عبدالعزيز الطليحي", "grade": "الثالث المتوسط", "class": 3, "phone": "966504437710"},
            {"id": "1160712996", "name": "خالد بن عبدالرؤوف بن عبدالله الشنيبر", "grade": "الثالث المتوسط", "class": 3, "phone": "966504173163"},
            {"id": "1162560054", "name": "خالد عبدالله خالد الخالدي", "grade": "الثالث المتوسط", "class": 3, "phone": "966558890881"},
            {"id": "1174188647", "name": "خالد محمد بن عبدالله ال درعان", "grade": "الثالث المتوسط", "class": 3, "phone": "966505556029"},
            {"id": "1159155223", "name": "راشد سعيد راشد عبدالسلام", "grade": "الثالث المتوسط", "class": 3, "phone": "966533177877"},
            {"id": "1174226389", "name": "راشد صالح بن عبدالعزيز الحلوان", "grade": "الثالث المتوسط", "class": 3, "phone": "966551112126"},
            {"id": "1167756897", "name": "رواد محمد ابراهيم الخليل", "grade": "الثالث المتوسط", "class": 3, "phone": "966502555411"},
            {"id": "1159394046", "name": "صالح بن محمد بن صالح الميموني المطيري", "grade": "الثالث المتوسط", "class": 3, "phone": "966555097811"},
            {"id": "1158551372", "name": "عبدالرحمن بدر عبدالرحمن الطريقي", "grade": "الثالث المتوسط", "class": 3, "phone": "966507004114"},
            {"id": "1195815558", "name": "عبدالرحمن خالد محمد سعيد", "grade": "الثالث المتوسط", "class": 3, "phone": "966504411393"},
            {"id": "1158561843", "name": "عبدالله تركي عبدالله الأحمد", "grade": "الثالث المتوسط", "class": 3, "phone": "966542800700"},
            {"id": "1159977451", "name": "عبدالله عبدالرحمن عبدالله النجراني", "grade": "الثالث المتوسط", "class": 3, "phone": "966546416395"},
            {"id": "1162387458", "name": "علي بن خالد بن علي العجيري", "grade": "الثالث المتوسط", "class": 3, "phone": "966505199500"},
            {"id": "1158128270", "name": "علي عبدالله علي ال حمود", "grade": "الثالث المتوسط", "class": 3, "phone": "966545555161"},
            {"id": "1161333677", "name": "فارس وليد بن عبدالله الحوطي", "grade": "الثالث المتوسط", "class": 3, "phone": "966552805550"},
            {"id": "1158198604", "name": "فهد بن خالد بن فهد بن عبدالعزيز الزيد", "grade": "الثالث المتوسط", "class": 3, "phone": "966555198633"},
            {"id": "1159551264", "name": "فيصل عبدالرحمن عزيز القحطاني", "grade": "الثالث المتوسط", "class": 3, "phone": "966556444082"},
            {"id": "1186515613", "name": "متعب مطر جمعان الدوسري", "grade": "الثالث المتوسط", "class": 3, "phone": "966530545913"},
            {"id": "1159852746", "name": "نواف فهد بن ناصر القحطاني", "grade": "الثالث المتوسط", "class": 3, "phone": "966556557210"},
            {"id": "1163072392", "name": "يوسف عبدالله عوض العتيبي", "grade": "الثالث المتوسط", "class": 3, "phone": "966506371377"}
        ]
    }
}

##### =========================================================
##### 5. إعدادات الصفحة والتنسيقات المخصصة الشاملة (CSS & Print Setup)
##### =========================================================
st.set_page_config(
    page_title="منصة مدرسة الثغر النموذجية - تقارير الإتقان والرسائل",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    /* 1. استيراد الخطوط العربية الرسمية المعتمدة من Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&family=Tajawal:wght@400;500;700;800&family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap');

    /* 2. ضبط الخط العربي والاتجاه RTL لكافة المكونات */
    html, body, [class*="css"], [class*="st-"], .stMarkdown, .stSelectbox, .stTextInput, .stNumberInput, .stButton, .stTabs, .stMetric, .stRadio, .stCheckbox {
        font-family: 'Cairo', 'Tajawal', 'IBM Plex Sans Arabic', -apple-system, BlinkMacSystemFont, sans-serif !important;
        direction: rtl !important;
        text-align: right !important;
    }

    /* 3. العناوين والنصوص */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Cairo', sans-serif !important;
        font-weight: 800 !important;
        color: #006C35;
        letter-spacing: -0.2px;
    }

    /* 4. تصميم ورقة التقرير المطبوع والعروض الرسمية (.report-paper) */
    .report-paper {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-top: 6px solid #006C35;
        border-radius: 12px;
        padding: 32px 36px;
        margin-top: 15px;
        margin-bottom: 30px;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);
        font-family: 'Cairo', 'Tajawal', sans-serif;
        color: #1e293b;
        direction: rtl;
    }

    /* 5. ترويسة التقرير الرسمية (.report-header-table) */
    .report-header-table {
        width: 100%;
        border-collapse: collapse;
        border-bottom: 2px solid #006C35;
        padding-bottom: 16px;
        margin-bottom: 22px;
    }
    .report-header-table td {
        border: none !important;
        vertical-align: middle;
        padding: 4px 8px;
    }

    /* 6. جدول التقرير القابل للطباعة (.printable-table) */
    .printable-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 15px;
        font-family: 'Cairo', sans-serif;
        font-size: 13.5px;
        background-color: #ffffff;
    }

    .printable-table th {
        background: linear-gradient(135deg, #006C35 0%, #004D25 100%);
        color: #ffffff !important;
        font-weight: 800;
        font-size: 14px;
        padding: 12px 10px;
        text-align: center;
        border: 1px solid #004D25;
        letter-spacing: 0.2px;
    }

    .printable-table td {
        padding: 10px 12px;
        border: 1px solid #cbd5e1;
        text-align: center;
        vertical-align: middle;
        color: #0f172a;
        font-weight: 600;
    }

    .printable-table tbody tr:nth-child(even) {
        background-color: #f8fafc;
    }

    .printable-table tbody tr:hover {
        background-color: #f1f5f9;
    }

    /* 7. وسوم الحالة الملونة داخل الجداول (.badge-status) */
    .badge-status {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12.5px;
        font-weight: 800;
        text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .badge-excellent {
        background-color: #dcfce7;
        color: #15803d;
        border: 1px solid #bbf7d0;
    }
    .badge-good {
        background-color: #dbeafe;
        color: #1d4ed8;
        border: 1px solid #bfdbfe;
    }
    .badge-warning {
        background-color: #fee2e2;
        color: #b91c1c;
        border: 1px solid #fecaca;
    }
    .badge-absent {
        background-color: #f1f5f9;
        color: #475569;
        border: 1px solid #cbd5e1;
    }

    /* 8. بطاقات الخطوات والرسائل المنسقة */
    .step-box {
        background-color: #ffffff;
        border-right: 6px solid #006C35;
        border-radius: 10px;
        padding: 18px 22px;
        margin-bottom: 22px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        border-top: 1px solid #f1f5f9;
        border-left: 1px solid #f1f5f9;
        border-bottom: 1px solid #f1f5f9;
    }
    .step-header {
        font-size: 17px;
        font-weight: 800;
        color: #006C35;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 8px;
        font-family: 'Cairo', sans-serif;
    }

    .msg-preview-card {
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        padding: 16px;
        margin-top: 10px;
        font-family: 'Cairo', sans-serif;
        line-height: 1.8;
        color: #1e293b;
        font-size: 14px;
    }

    /* 9. شارات حالة الاتصال بالشريط الجانبي */
    .status-badge-ok {
        background-color: #dcfce7;
        color: #15803d;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 700;
        border: 1px solid #bbf7d0;
        text-align: center;
    }
    .status-badge-off {
        background-color: #fee2e2;
        color: #b91c1c;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 700;
        border: 1px solid #fecaca;
        text-align: center;
    }

    /* 10. قواعد الطباعة المتقدمة الاحترافية (@media print) */
    @media print {
        @page {
            size: A4 portrait;
            margin: 10mm 8mm;
        }
        body {
            background-color: #ffffff !important;
            font-family: 'Cairo', sans-serif !important;
            color: #000000 !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }
        body.mode-print-full .print-class-section { display: none !important; }
        body.mode-print-class .print-full-section { display: none !important; }
        .no-print, header, footer, [data-testid="stSidebar"], .stButton, [data-testid="stHeader"] { 
            display: none !important; 
        }
        .report-paper {
            border: none !important;
            box-shadow: none !important;
            padding: 0 !important;
            margin: 0 !important;
            width: 100% !important;
        }
        .printable-table th {
            background-color: #006C35 !important;
            color: #ffffff !important;
            -webkit-print-color-adjust: exact !important;
        }
        .printable-table td {
            border: 1px solid #64748b !important;
            font-size: 12px !important;
            padding: 7px 9px !important;
        }
        tr { page-break-inside: avoid !important; }
    }
    </style>
""", unsafe_allow_html=True)


### الشريط الجانبي
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

##### =========================================================
##### الصفحة الأولى: صفحة الرصد (RECORDING SHEET)
##### =========================================================
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

##### =========================================================
##### الصفحة الثانية: إدارة المدرسة وتقارير أولياء الأمور (محدثة)
##### =========================================================
elif page == "🏫 إدارة المدرسة وتقارير أولياء الأمور":
    # الترويسة السعودية باللون الأخضر
    render_saudi_header("إدارة المدرسة وإرسال التقارير والطباعة")

    # ---------------------------------------------------------
    # تنسيقات CSS المخصصة للخطوات وفصل الطباعة تماماً
    # ---------------------------------------------------------
    st.markdown("""
    <style>
    /* تنسيق بطاقات الخطوات المتسلسلة */
    .step-box {
        background-color: #ffffff;
        border-right: 5px solid #006C35;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 20px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.05);
        border-top: 1px solid #f1f5f9;
        border-left: 1px solid #f1f5f9;
        border-bottom: 1px solid #f1f5f9;
    }
    .step-header {
        font-size: 16px;
        font-weight: 800;
        color: #006C35;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* تنسيق بطاقة الرسالة الموجهة لولي الأمر */
    .msg-preview-card {
        background-color: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 14px;
        margin-top: 8px;
        font-family: 'Cairo', sans-serif;
        line-height: 1.6;
        color: #1e293b;
    }

    /* قواعد طباعة صارمة تمنع تداخل التقارير تماماً */
    @media print {
        body.mode-print-full .print-class-section { display: none !important; }
        body.mode-print-class .print-full-section { display: none !important; }
        .no-print, header, footer, [data-testid="stSidebar"], .stButton { display: none !important; }
    }
    </style>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # الخطوة 1: تحديد الفصل الدراسي والأسبوع
    # ---------------------------------------------------------
    st.markdown("""
    <div class="step-box">
        <div class="step-header">📌 الخطوة الأولى: تحديد الفترة الزمنية للتقرير</div>
    </div>
    """, unsafe_allow_html=True)
    
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        weeks = [f"الأسبوع {i}" for i in range(1, 19)]
        selected_week = st.selectbox("اختر الأسبوع:", weeks, key="sel_wk_rep")
    with col_w2:
        selected_term = st.selectbox("اختر الفصل الدراسي:", ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"], key="sel_trm_rep")

    # تحميل البيانات بناءً على التحديد
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
                    "id": sid, "name": s_item["name"], "grade": g_name,
                    "class": c_num, "phone": p_num, "score": final_score,
                    "is_absent": is_abs, "message": msg
                }
                all_students_flat.append(row_dict)

                if is_abs == 1: cat_gray.append(row_dict)
                elif final_score < 50: cat_red.append(row_dict)
                elif final_score <= 75: cat_blue.append(row_dict)
                else: cat_green.append(row_dict)

    st.markdown("---")

    # ---------------------------------------------------------
    # الخطوة 2: اختيار نوع التقرير المطلوب (فصل العرض تماماً)
    # ---------------------------------------------------------
    st.markdown("""
    <div class="step-box">
        <div class="step-header">🖨️ الخطوة الثانية: اختيار التقرير المطلوب للطباعة والعرض</div>
    </div>
    """, unsafe_allow_html=True)

    report_type = st.radio(
        "اختر التقرير الذي تريد عرضه وطباعته:",
        ["📋 التقرير الشامل للمدرسة", "🏫 تقرير فصل دراسي محدد"],
        horizontal=True
    )

    st.markdown("---")

    # ---------------------------------------------------------
    # الخيار الأول: التقرير الشامل (يظهر ويطبع منفرداً)
    # ---------------------------------------------------------
    if report_type == "📋 التقرير الشامل للمدرسة":
        st.markdown("### 📊 التقرير الشامل للأسبوع المختار")
        col_rep1, col_rep2 = st.columns([3, 1])

        with col_rep1:
            st.info(f"**عرض التقرير الشامل:** {selected_term} - {selected_week} | إجمالي طلاب المدرسة: {len(all_students_flat)} طالب")

        with col_rep2:
            print_button(label="🖨️ طباعة التقرير الشامل", button_id="print_full_week", target_mode="mode-print-full")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔴 أقل من 50%", f"{len(cat_red)} طالب")
        m2.metric("🔵 50% - 75%", f"{len(cat_blue)} طالب")
        m3.metric("🟢 76% - 100%", f"{len(cat_green)} طالب")
        m4.metric("⚪ الغياب", f"{len(cat_gray)} طالب")

        today_str = datetime.now().strftime("%Y/%m/%d")

        rows_html = ""
        for idx, s in enumerate(all_students_flat):
            status_txt = (
                '<span class="badge-status badge-absent">غائب ⚪</span>' if s['is_absent'] == 1 else
                ('<span class="badge-status badge-excellent">متفوق 🟢</span>' if s['score'] >= 76 else
                ('<span class="badge-status badge-good">جيد 🔵</span>' if s['score'] >= 50 else
                '<span class="badge-status badge-warning">يحتاج متابعة 🔴</span>'))
            )
            score_txt = f"{s['score']}%" if s['is_absent'] == 0 else "-"
            rows_html += f"""
            <tr>
                <td>{idx+1}</td>
                <td>{s['id']}</td>
                <td style="text-align: right; padding-right: 14px; font-weight: 700; color: #0f172a; font-family: 'Cairo', sans-serif;">{s['name']}</td>
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

    # ---------------------------------------------------------
    # الخيار الثاني: تقرير الفصل المحدد (يظهر ويطبع منفرداً)
    # ---------------------------------------------------------
    else:
        st.markdown("### 🏫 تقرير تقييم الصف الدراسي المحدد")
        col_g1, col_g2, col_g3 = st.columns([2, 2, 2])

        with col_g1:
            selected_rep_grade = st.selectbox("اختر المرحلة الدراسية:", list(STUDENTS_DB_GRADES.keys()), key="rep_grade")
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
            today_str = datetime.now().strftime("%Y/%m/%d")
            class_rows_html = ""
            for idx, s in enumerate(class_students):
                status_txt = (
                '<span class="badge-status badge-absent">غائب ⚪</span>' if s['is_absent'] == 1 else
                ('<span class="badge-status badge-excellent">متفوق 🟢</span>' if s['score'] >= 76 else
                ('<span class="badge-status badge-good">جيد 🔵</span>' if s['score'] >= 50 else
                '<span class="badge-status badge-warning">يحتاج متابعة 🔴</span>'))
            )
                score_txt = f"{s['score']}%" if s['is_absent'] == 0 else "-"
                class_rows_html += f"""
                <tr>
                    <td>{idx+1}</td>
                    <td>{s['id']}</td>
                    <td style="text-align: right; padding-right: 14px; font-weight: 700; color: #0f172a; font-family: 'Cairo', sans-serif;">{s['name']}</td>
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
                        <td style="width: 33%; border: none;">وكيل شؤون الطلاب:<br/><br/>صالح بن عبدالله الدعجاني </td>
                        <td style="width: 33%; border: none;">وكيل الشؤون التعليمية:<br/><br/>محمد مبروك السيد </td>
                        <td style="width: 34%; border: none;">مدير المدرسة:<br/><br/>إبراهيم بن موسى التميمي </td>
                    </tr>
                </table>
            </div>
            """
            render_clean_html(class_report_html)
        else:
            st.warning("لا توجد بيانات متاحة لهذا الصف في الأسبوع المختار.")

    st.markdown("---")

    # ---------------------------------------------------------
    # الخطوة 3: إدارة وتنسيق رسائل أولياء الأمور
    # ---------------------------------------------------------
    st.markdown("""
    <div class="step-box">
        <div class="step-header">📱 الخطوة الثالثة: معاينة وتنسيق رسائل أولياء الأمور وحالة الإرسال</div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4 = st.tabs([
        f"🔴 أقل من 50% ({len(cat_red)})",
        f"🔵 50% - 75% ({len(cat_blue)})",
        f"🟢 76% - 100% ({len(cat_green)})",
        f"⚪ الغياب ({len(cat_gray)})"
    ])

    def show_category_tab_formatted(cat_list, cat_name):
        if not cat_list:
            st.info(f"لا يوجد طلاب في {cat_name} بهذا الأسبوع.")
        else:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                with st.expander(f"💬 إرسال واتساب جماعي مباشر ({len(cat_list)} طالب)"):
                    if st.button(f"⚡ إرسال واتساب لـ {cat_name}", key=f"bulk_wa_{cat_name}"):
                        with st.spinner("جاري الإرسال عبر WhatsApp API..."):
                            succ, fail, _ = send_bulk_messages(
                                cat_list, channel="wa_api", wa_creds={"instance_id": wa_instance, "api_token": wa_token}
                            )
                            st.success(f"✅ تم الإرسال! النجاح: {succ} | الفشل: {fail}")
            
            with col_b2:
                with st.expander(f"🚀 إرسال SMS جماعي عبر Mora ({len(cat_list)} طالب)"):
                    if st.button(f"⚡ إرسال SMS لـ {cat_name}", key=f"bulk_sms_{cat_name}"):
                        with st.spinner("جاري الإرسال عبر Mora SMS..."):
                            m_creds = {"username": mora_user, "password": mora_pass, "sender": mora_sender, "otp": mora_otp}
                            succ, fail, _ = send_bulk_messages(cat_list, channel="sms", mora_creds=m_creds)
                            st.success(f"✅ تم الإرسال! النجاح: {succ} | الفشل: {fail}")

            st.markdown("---")

            # عرض كل طالب مع تنسيق احترافي للرسالة
            for item in cat_list:
                with st.expander(f"👤 {item['name']} ── {item['grade']} (فصل {item['class']}) ── 📱 {item['phone']}"):
                    c_info1, c_info2 = st.columns(2)
                    with c_info1:
                        st.write(f"**رقم الهوية الوطنية:** `{item['id']}`")
                    with c_info2:
                        st.write(f"**النسبة المئوية:** `{item['score']}%`" if item['is_absent'] == 0 else "**الحالة:** غائب ⚪")
                    
                    # معاينة منسقة للرسالة بأسلوب البطاقات الرسمية
                    st.markdown(f"""
                    <div class="msg-preview-card">
                        <div style="font-weight: bold; color: #006C35; margin-bottom: 6px;">✉️ نص الرسالة الموجهة لولي الأمر:</div>
                        <div style="white-space: pre-wrap; background: #ffffff; padding: 10px; border-radius: 6px; border: 1px dashed #cbd5e1;">{item['message']}</div>
                    </div>
                    """, unsafe_allow_html=True)

    with tab1: show_category_tab_formatted(cat_red, "فئة أقل من 50%")
    with tab2: show_category_tab_formatted(cat_blue, "فئة 50% - 75%")
    with tab3: show_category_tab_formatted(cat_green, "فئة 76% - 100%")
    with tab4: show_category_tab_formatted(cat_gray, "فئة الغياب")
