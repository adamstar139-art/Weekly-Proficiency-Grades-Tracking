import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import io
import copy
import urllib.parse
import requests
try:
    import plotly.express as px
    import plotly.graph_objects as go
    _PLOTLY_AVAILABLE = True
except ImportError:
    _PLOTLY_AVAILABLE = False

# =========================================================
# 0. ربط قاعدة البيانات السحابية الدائمة (Supabase Cloud)
# =========================================================
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
        key = st.secrets.get("key") or st.secrets.get("SUPABASE_KEY") or sec.get("anon_key") if 'sec' in locals() else None

    if not url or not key:
        return None
    try:
        clean_url = str(url).strip().strip('"').strip("'")
        clean_key = str(key).strip().strip('"').strip("'")
        if not clean_url or not clean_key:
            return None
        return create_client(clean_url, clean_key)
    except Exception:
        return None

def supabase_ready():
    return get_supabase() is not None

# =========================================================
# 1. دوال قاعدة البيانات (Supabase Integration)
# =========================================================
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

def update_student_phone_db(student_id, new_phone):
    sb = get_supabase()
    if sb is None:
        return False
    try:
        sb.table("thaghr_students_info").upsert({
            "student_id": str(student_id),
            "phone": str(new_phone).strip()
        }).execute()
        return True
    except Exception as ex:
        st.error(f"خطأ في تحديث رقم الجوال: {ex}")
        return False
    finally:
        st.cache_data.clear()

def delete_student_from_db(student_id):
    sb = get_supabase()
    if sb is None:
        return False
    try:
        sb.table("thaghr_students_info").delete().eq("student_id", str(student_id)).execute()
        sb.table("thaghr_grades").delete().eq("student_id", str(student_id)).execute()
        return True
    except Exception as ex:
        st.error(f"خطأ أثناء حذف الطالب من قاعدة البيانات: {ex}")
        return False
    finally:
        st.cache_data.clear()

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

# =========================================================
# 3. قائمة الطلاب الأساسية وإدارتها في Session State
# =========================================================
INITIAL_STUDENTS_DB = {
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

if "students_db" not in st.session_state:
    st.session_state["students_db"] = copy.deepcopy(INITIAL_STUDENTS_DB)

STUDENTS_DB_GRADES = st.session_state["students_db"]

# =========================================================
# 4. إعداد واجهة التطبيق والتنسيق العربي
# =========================================================
st.set_page_config(
    page_title="برنامج رصد الدرجات - متوسطة الثغر النموذجية الأهلية",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    /* RTL and Cairo Font Fixes */
    html, body, [class*="css"], div, span, h1, h2, h3, h4, h5, h6, p, label, button, input {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl !important;
        text-align: right !important;
    }
    .main {
        background-color: #f8fafc;
    }
    .stMarkdown, p, div {
        line-height: 1.8 !important;
    }
    
    /* Button Styling Fixes to prevent text wrapping/overlap */
    .stButton>button {
        border-radius: 8px !important;
        font-weight: 700 !important;
        font-family: 'Cairo', sans-serif !important;
        padding: 8px 12px !important;
        line-height: 1.5 !important;
        width: 100% !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    }
    .stButton>button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
    }

    /* Expander Title Styling */
    /* إصلاح تشابك وتباعد خطوط القوائم المنسدلة (st.expander) */
    [data-testid="stExpander"] details summary p, 
    [data-testid="stExpander"] summary,
    .streamlit-expanderHeader {
        direction: rtl !important;
        text-align: right !important;
        font-family: 'Cairo', sans-serif !important;
        line-height: 1.8 !important;
        font-size: 15px !important;
        font-weight: 700 !important;
        padding-top: 6px !important;
        padding-bottom: 6px !important;
    }
    .streamlit-expanderHeader {
        font-size: 15px !important;
        font-weight: 700 !important;
        color: #1e293b !important;
        background-color: #f8fafc !important;
        border-radius: 8px !important;
        padding: 10px 15px !important;
        border: 1px solid #e2e8f0 !important;
    }

    .status-badge-ok {
        background-color: #dcfce7;
        color: #15803d;
        padding: 6px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 13px;
        text-align: center;
    }
    .status-badge-off {
        background-color: #fee2e2;
        color: #b91c1c;
        padding: 6px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 13px;
        text-align: center;
    }
    .report-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 22px;
        margin-bottom: 22px;
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.03);
    }
    .report-title {
        color: #005A2B;
        font-weight: 800;
        font-size: 20px;
        margin-bottom: 15px;
        border-bottom: 2px solid #005A2B;
        padding-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
# 0.1 مكونات الترويسة والتوقيعات بالهوية السعودية
# =========================================================
def render_saudi_header():
    st.markdown('''
    <div style="
        background: linear-gradient(135deg, #005A2B 0%, #007A3D 50%, #004D25 100%);
        color: #ffffff;
        padding: 20px 25px;
        border-radius: 14px;
        box-shadow: 0 6px 20px rgba(0, 90, 43, 0.22);
        margin-bottom: 25px;
        border-top: 5px solid #D4AF37;
        border-bottom: 3px solid #D4AF37;
        font-family: 'Cairo', sans-serif;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; direction: rtl; text-align: right;">
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="font-size: 38px; line-height: 1;">🇸🇦</div>
                <div>
                    <div style="font-size: 13px; opacity: 0.95; font-weight: 600; letter-spacing: 0.3px; color: #E2E8F0;">المملكة العربية السعودية • وزارة التعليم</div>
                    <div style="font-size: 13px; opacity: 0.9; margin-top: 2px; color: #CBD5E1;">إدارة التعليم بمنطقة الرياض | مكتب التعليم الخاص</div>
                    <div style="font-size: 22px; font-weight: 800; margin-top: 4px; color: #FFFFFF; text-shadow: 0 2px 4px rgba(0,0,0,0.3);">متوسطة الثغر النموذجية الأهلية</div>
                </div>
            </div>
            <div style="background: rgba(255, 255, 255, 0.15); backdrop-filter: blur(5px); border: 1px solid rgba(255, 255, 255, 0.3); padding: 8px 18px; border-radius: 30px; font-size: 13px; font-weight: 700; color: #F8FAFC; white-space: nowrap;">
                👨‍💻 تصميم وتطوير: أ/ محمد سامي السعيد
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

def render_signatures_card():
    st.markdown('''
    <div style="background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin-top: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
        <div style="font-size: 16px; font-weight: 800; color: #005A2B; margin-bottom: 15px; border-bottom: 2px solid #005A2B; padding-bottom: 6px;">
            ✍️ الاعتماد والتوقيعات الرسمية للقيادة المدرسية
        </div>
        <div style="display: flex; justify-content: space-around; flex-wrap: wrap; gap: 15px; text-align: center;">
            <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 10px; padding: 12px 18px; min-width: 200px; flex: 1;">
                <div style="color: #64748b; font-size: 13px; font-weight: 700;">وكيل شؤون الطلاب</div>
                <div style="color: #0f172a; font-size: 15px; font-weight: 800; margin-top: 4px;">أ/ صالح بن عبدالله الدعجاني</div>
            </div>
            <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 10px; padding: 12px 18px; min-width: 200px; flex: 1;">
                <div style="color: #64748b; font-size: 13px; font-weight: 700;">وكيل الشؤون التعليمية</div>
                <div style="color: #0f172a; font-size: 15px; font-weight: 800; margin-top: 4px;">أ/ محمد مبروك السيد</div>
            </div>
            <div style="background: #f8fafc; border: 1px dashed #cbd5e1; border-radius: 10px; padding: 12px 18px; min-width: 200px; flex: 1;">
                <div style="color: #64748b; font-size: 13px; font-weight: 700;">مدير المدرسة</div>
                <div style="color: #0f172a; font-size: 15px; font-weight: 800; margin-top: 4px;">أ/ إبراهيم بن موسى التميمي</div>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)


# الشريط الجانبي
st.sidebar.title("📌 القائمة الرئيسية")

if supabase_ready():
    st.sidebar.markdown('<div class="status-badge-ok">🟢 متصل بقاعدة بيانات Supabase الدائمة</div>', unsafe_allow_html=True)
else:
    st.sidebar.markdown('<div class="status-badge-off">🔴 غير متصل بـ Supabase (يعمل محلياً)</div>', unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.subheader("📱 إعدادات البوابات والرسائل")

with st.sidebar.expander("💬 إعدادات WhatsApp Direct API (إرسال تلقائي بدون فتح التطبيق)"):
    wa_instance = st.text_input("Instance ID:", value="", key="wa_inst_inp")
    wa_token = st.text_input("API Token:", value="", type="password", key="wa_tok_inp")
    st.caption("💡 باستخدام هذه الإعدادات، يتم إرسال رسائل الواتساب مباشرة للطلاب في الخلفية فور الضغط على زر الإرسال بنقرة واحدة.")

with st.sidebar.expander("📱 إعدادات Mora SMS"):
    mora_user = st.text_input("اسم المستخدم / الرقم:", value="966508634881", key="mora_u")
    mora_pass = st.text_input("كلمة المرور:", value="THA@0508634881", type="password", key="mora_p")
    mora_sender = st.text_input("اسم المرسل المعتمد:", value="THAGHR-S", key="mora_s")
    mora_otp = st.text_input("كود التحقق / OTP (إذا طلب):", value="", key="mora_otp_input")

st.sidebar.markdown("---")
render_saudi_header()

page = st.sidebar.radio("اختر الصفحة:", [
    "📝 صفحة الرصد", 
    "🏫 إدارة المدرسة وتقارير أولياء الأمور",
    "🁻 طباعة التقارير والتحليلات",
    "👥 إدارة الطلاب (إضافة / حذف / نقل)"
])

# =========================================================
# الصفحة الأولى: صفحة الرصد (RECORDING SHEET)
# =========================================================
if page == "📝 صفحة الرصد":
    st.subheader("📝 صفحة رصد درجات الإتقان الأسبوعية")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        term = st.selectbox("الفصل الدراسي:", ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"])
    with col2:
        grade = st.selectbox("الصف الدراسي:", ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"])
    with col3:
        available_classes = list(STUDENTS_DB_GRADES.get(grade, {}).keys()) or [1]
        class_num = st.selectbox("الفصل / الشعبة:", available_classes)
    with col4:
        weeks = [f"الأسبوع {i}" for i in range(1, 19)]
        week = st.selectbox("الأسبوع المستهدف:", weeks)

    st.markdown("---")

    raw_students = STUDENTS_DB_GRADES.get(grade, {}).get(class_num, [])
    db_grades_list = fetch_all_grades_db(term, week)
    db_grades_map = {str(g['student_id']): g for g in db_grades_list}

    if not raw_students:
        st.warning("لا يوجد طلاب مسجلين في هذا الصف والشعبة حالياً.")
    else:
        st.info(f"📊 عدد الطلاب في {grade} - فصل ({class_num}): **{len(raw_students)} طالب** | {term} - {week}")
        
        with st.form("recording_form"):
            st.markdown("##### 📥 أدخل/عدّل درجات الطلاب وحالة الغياب:")
            
            updated_data = []
            for idx, st_item in enumerate(raw_students, 1):
                sid = str(st_item["id"])
                saved_rec = db_grades_map.get(sid, {})
                default_sc = float(saved_rec.get("score", 0.0))
                default_abs = bool(saved_rec.get("is_absent", 0))

                col_name, col_score, col_absent = st.columns([3, 1, 1])
                with col_name:
                    st.markdown(f'<div class="student-card">📌 <b>{idx}. {st_item["name"]}</b> <small style="color:#64748B;">({sid})</small></div>', unsafe_allow_html=True)
                with col_score:
                    sc = st.number_input(f"الدرجة (100)", min_value=0.0, max_value=100.0, value=default_sc, step=1.0, key=f"sc_{sid}")
                with col_absent:
                    is_abs = st.checkbox("غائب ⚪", value=default_abs, key=f"abs_{sid}")
                
                final_score = 0.0 if is_abs else sc
                updated_data.append({
                    "student_id": sid,
                    "name": st_item["name"],
                    "phone": st_item.get("phone", ""),
                    "score": final_score,
                    "is_absent": 1 if is_abs else 0
                })
            
            save_btn = st.form_submit_button("💾 حفظ البيانات والتحديث بقاعدة البيانات الدائمة")
            
        if save_btn:
            if save_grades_to_db(term, week, updated_data):
                st.success("✅ تم حفظ وتحديث درجات الطلاب بنجاح وبشكل دائم في قاعدة البيانات السحابية Supabase!")
                st.rerun()

        st.markdown("### 📊 جدول نتائج الرصد المنسق بالتلوين الشرطي:")
        
        table_rows = []
        for item in updated_data:
            sc = item["score"]
            is_abs = item["is_absent"]
            if is_abs == 1:
                cat = "غائب ⚪"
                pct = "0% (غائب)"
            elif sc < 50:
                cat = "أقل من 50% (ضعيف) 🔴"
                pct = f"{sc}%"
            elif sc <= 75:
                cat = "50% - 75% (متوسط) 🔵"
                pct = f"{sc}%"
            else:
                cat = "76% - 100% (ممتاز) 🟢"
                pct = f"{sc}%"
                
            table_rows.append({
                "اسم الطالب": item["name"],
                "رقم الهوية": item["student_id"],
                "درجة الإتقان / 100": sc if is_abs == 0 else 0.0,
                "النسبة المئوية": pct,
                "الفئة / الحالة": cat
            })
        
        df_display = pd.DataFrame(table_rows)
        st.dataframe(df_display, use_container_width=True)

# =========================================================
# الصفحة الثانية: إدارة المدرسة وتقارير أولياء الأمور
# =========================================================
elif page == "🏫 إدارة المدرسة وتقارير أولياء الأمور":
    st.subheader("🏫 إدارة المدرسة وإرسال وتقارير أولياء الأمور")
    
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

                msg = generate_parent_message(s_item["name"], sc, is_abs == 1)

                row_dict = {
                    "id": sid,
                    "name": s_item["name"],
                    "grade": g_name,
                    "class": c_num,
                    "phone": p_num,
                    "score": sc if (sc is not None and is_abs == 0) else 0.0,
                    "is_absent": is_abs,
                    "message": msg
                }
                all_students_flat.append(row_dict)

                if is_abs == 1:
                    cat_gray.append(row_dict)
                elif sc is None or sc < 50:
                    cat_red.append(row_dict)
                elif sc <= 75:
                    cat_blue.append(row_dict)
                else:
                    cat_green.append(row_dict)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🔴 فئة أقل من 50%", f"{len(cat_red)} طالب")
    m2.metric("🔵 فئة 50% - 75%", f"{len(cat_blue)} طالب")
    m3.metric("🟢 فئة 76% - 100%", f"{len(cat_green)} طالب")
    m4.metric("⚪ فئة الغياب", f"{len(cat_gray)} طالب")

    st.markdown("---")

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

            st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)

            for idx_st, item in enumerate(cat_list):
                wa_manual_url = create_whatsapp_web_url(item['phone'], item['message'])
                score_str = f"{item['score']}%" if item['is_absent'] == 0 else "غائب ⚪"
                
                # بطاقة الطالب التفاعلية المباشرة بديل ممتاز وشفاف يحل تداخل st.expander نهائياً
                st.markdown(f'''
                <details style="
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    border-radius: 12px;
                    padding: 14px 18px;
                    margin-bottom: 12px;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.03);
                    direction: rtl;
                    text-align: right;
                    font-family: 'Cairo', sans-serif;
                ">
                    <summary style="
                        font-size: 16px;
                        font-weight: 800;
                        color: #005A2B;
                        cursor: pointer;
                        outline: none;
                        line-height: 2.2;
                        padding: 4px 0;
                    ">
                        👤 {item['name']} &nbsp;&nbsp;•&nbsp;&nbsp; {item['grade']} &nbsp;&nbsp;•&nbsp;&nbsp; فصل: {item['class']}
                    </summary>
                    <div style="margin-top: 14px; border-top: 1px solid #f1f5f9; padding-top: 14px;">
                        <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; font-size: 13px;">
                            <span style="background: #f1f5f9; color: #334155; padding: 5px 12px; border-radius: 6px; font-weight: 700; border: 1px solid #cbd5e1;">🆔 الهوية: {item['id']}</span>
                            <span style="background: #e0f2fe; color: #0369a1; padding: 5px 12px; border-radius: 6px; font-weight: 700; border: 1px solid #bae6fd;">📊 الدرجة: {score_str}</span>
                            <span style="background: #fef3c7; color: #92400e; padding: 5px 12px; border-radius: 6px; font-weight: 700; border: 1px solid #fde68a;">📱 الجوال: {item['phone']}</span>
                        </div>
                        <div style="background-color: #f8fafc; border-right: 4px solid #005A2B; padding: 14px 18px; border-radius: 8px; color: #0f172a; font-size: 14px; line-height: 1.8; margin-bottom: 14px; word-wrap: break-word;">
                            <b style="color: #005A2B;">💬 نص الرسالة الموجهة لولي الأمر:</b><br/>
                            {item['message']}
                        </div>
                    </div>
                </details>
                ''', unsafe_allow_html=True)
                
                btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
                
                with btn_col1:
                    if st.button("💬 إرسال واتساب تلقائي", key=f"wa_dir_{item['id']}_{idx_st}"):
                        with st.spinner("جاري الإرسال المباشر..."):
                            ok, resp = send_whatsapp_direct_api(item['phone'], item['message'], wa_instance, wa_token)
                            if ok:
                                st.success(f"✅ {resp}")
                            else:
                                st.error(f"❌ {resp}")
                    
                with btn_col2:
                    st.markdown(f'''
                    <a href="{wa_manual_url}" target="_blank" style="text-decoration:none;">
                        <div style="background-color:#25D366; color:white; padding:8px 12px; border-radius:8px; text-align:center; font-weight:700; font-size:13px; line-height:1.5; display:block; border: 1px solid #1da851;">
                            🌐 فتح بالواتساب
                        </div>
                    </a>
                    ''', unsafe_allow_html=True)

                with btn_col3:
                    if st.button("📱 إرسال SMS (Mora)", key=f"sms_dir_{item['id']}_{idx_st}"):
                        with st.spinner("جاري الإرسال..."):
                            status, msg_resp = send_mora_sms(
                                item['phone'], item['message'], username=mora_user, password=mora_pass, sender_name=mora_sender, otp_code=mora_otp
                            )
                            if status:
                                st.success(f"✅ {msg_resp}")
                            else:
                                st.error(f"❌ تعذر الإرسال: {msg_resp}")

    with tab1: show_category_tab(cat_red, "فئة أقل من 50%")
    with tab2: show_category_tab(cat_blue, "فئة 50% - 75%")
    with tab3: show_category_tab(cat_green, "فئة 76% - 100%")
    with tab4: show_category_tab(cat_gray, "فئة الغياب")

    st.markdown("---")
    st.markdown("### 📞 إدارة ورصد أرقام جوالات أولياء الأمور (تحديث وحفظ الدائم):")

    df_reports_all = pd.DataFrame(all_students_flat)
    if not df_reports_all.empty:
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            st_select = st.selectbox("اختر الطالب لتحديث رقم جوال ولي أمره:", df_reports_all["name"].tolist())

        selected_st_row = df_reports_all[df_reports_all["name"] == st_select].iloc[0]

        with col_p2:
            new_phone = st.text_input("رقم الجوال الجديد:", value=selected_st_row["phone"])
            if st.button("💾 تحديث وتثبيت رقم الجوال في قاعدة البيانات"):
                if update_student_phone_db(selected_st_row["id"], new_phone):
                    st.success(f"✅ تم تحديث رقم جوال الطالب {st_select} بنجاح في قاعدة البيانات السحابية!")
                    st.rerun()

# =========================================================
# الصفحة الثالثة: طباعة التقارير والتحليلات (جديدة)
# =========================================================
elif page == "🁻 طباعة التقارير والتحليلات":
    st.title("🁻 مركز التقارير المطبوعة وتحليل النواتج")
    st.markdown("اختر نوع التقرير المطلوب، وقم بتخصيص الخيارات لعرض التحليلات، التصدير إلى Excel وطباعة/تصدير PDF.")
    
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        rep_term = st.selectbox("اختر الفصل الدراسي للتقرير:", ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"], key="rep_term_select")
    with col_sel2:
        rep_week = st.selectbox("اختر الأسبوع:", [f"الأسبوع {i}" for i in range(1, 19)], key="rep_week_select")

    st.markdown("---")

    # جلب درجات الأسبوع المختار
    db_grades_list = fetch_all_grades_db(rep_term, rep_week)
    db_grades_map = {str(g['student_id']): g for g in db_grades_list}
    phone_db_map = fetch_student_phones_db()

    # تجميع كلي للبيانات
    master_records = []
    for g_name, g_data in STUDENTS_DB_GRADES.items():
        for c_num, s_list in g_data.items():
            for s_item in s_list:
                sid = str(s_item["id"])
                rec = db_grades_map.get(sid, {})
                sc = rec.get("score", None)
                is_abs = rec.get("is_absent", 0)
                phone = phone_db_map.get(sid, s_item.get("phone", ""))
                
                status_cat = "غير مرصود"
                if is_abs == 1:
                    status_cat = "غائب ⚪"
                elif sc is not None:
                    if sc < 50:
                        status_cat = "ضعيف (<50%) 🔴"
                    elif sc <= 75:
                        status_cat = "متوسط (50-75%) 🔵"
                    else:
                        status_cat = "متميز (>75%) 🟢"
                
                master_records.append({
                    "رقم الهوية": sid,
                    "اسم الطالب": s_item["name"],
                    "الصف الدراسي": g_name,
                    "الفصل / الشعبة": f"فصل {c_num}",
                    "الدرجة": sc if (sc is not None and is_abs == 0) else 0.0,
                    "الحالة": status_cat,
                    "غائب": "نعم" if is_abs == 1 else "لا",
                    "رقم الجوال": phone
                })
                
    df_master = pd.DataFrame(master_records)

    # اختيار نوع التقرير
    rep_type = st.radio(
        "📋 اختر نوع التقرير المطلوب:",
        ["📑 التقرير الشامل للمدرسة", "🏫 تقرير الصفوف", "🏛️ تقرير فصل محدد", "📊 تقرير تحليل النواتج والافتراق التحصيلي"],
        horizontal=True
    )

    # دالة مساعدة لتوليد ملف Excel
    def to_excel(df, sheet_name='التقرير'):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return output.getvalue()

    # دالة مساعدة لتوليد صفحة HTML قابلة للطباعة PDF
    def generate_html_report(title, subtitle, df_table, metrics_summary=None):
        table_html = df_table.to_html(classes="styled-table", index=False)
        metrics_html = ""
        if metrics_summary:
            metrics_html = '<div class="metrics-container">'
            for k, v in metrics_summary.items():
                metrics_html += f'<div class="metric-box"><div class="metric-val">{v}</div><div class="metric-lbl">{k}</div></div>'
            metrics_html += '</div>'

        html_content = f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        body {{
            font-family: 'Cairo', sans-serif;
            direction: rtl;
            text-align: right;
            padding: 30px;
            background-color: #fff;
            color: #1e293b;
        }}
        .header {{
            text-align: center;
            border-bottom: 3px double #005A2B;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }}
        .header h1 {{
            color: #005A2B;
            margin: 0 0 8px 0;
            font-size: 26px;
        }}
        .header h3 {{
            color: #64748b;
            margin: 0;
            font-size: 16px;
            font-weight: 600;
        }}
        .metrics-container {{
            display: flex;
            justify-content: space-around;
            margin-bottom: 25px;
            gap: 15px;
        }}
        .metric-box {{
            background: #f0fdf4;
            border: 1px solid #bbf7d0;
            border-radius: 8px;
            padding: 12px 20px;
            text-align: center;
            flex: 1;
        }}
        .metric-val {{
            font-size: 22px;
            font-weight: 800;
            color: #005A2B;
        }}
        .metric-lbl {{
            font-size: 13px;
            color: #475569;
            font-weight: 600;
        }}
        .styled-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            font-size: 14px;
        }}
        .styled-table th {{
            background-color: #005A2B;
            color: white;
            padding: 10px;
            border: 1px solid #005A2B;
            text-align: center;
        }}
        .styled-table td {{
            padding: 8px 12px;
            border: 1px solid #e2e8f0;
            text-align: center;
        }}
        .styled-table tr:nth-child(even) {{
            background-color: #f8fafc;
        }}
        .footer {{
            margin-top: 40px;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
            border-top: 1px solid #e2e8f0;
            padding-top: 10px;
        }}
        @media print {{
            .no-print {{ display: none; }}
            body {{ padding: 0; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏫 متوسطة الثغر النموذجية الأهلية</h1>
        <h3>{title} - {subtitle}</h3>
        <p style="font-size:12px; color:#64748b; margin-top:5px;">تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d')}</p>
    </div>
    {metrics_html}
    {table_html}
    
    <div style="display: flex; justify-content: space-between; margin-top: 40px; margin-bottom: 25px; text-align: center; gap: 15px;">
        <div style="flex: 1; padding: 12px; border-top: 2px solid #005A2B; background: #f8fafc; border-radius: 6px;">
            <div style="font-size: 13px; font-weight: 700; color: #005A2B;">وكيل شؤون الطلاب</div>
            <div style="font-size: 15px; font-weight: 800; margin-top: 6px; color: #1e293b;">صالح بن عبدالله الدعجاني</div>
        </div>
        <div style="flex: 1; padding: 12px; border-top: 2px solid #005A2B; background: #f8fafc; border-radius: 6px;">
            <div style="font-size: 13px; font-weight: 700; color: #005A2B;">وكيل الشؤون التعليمية</div>
            <div style="font-size: 15px; font-weight: 800; margin-top: 6px; color: #1e293b;">محمد مبروك السيد</div>
        </div>
        <div style="flex: 1; padding: 12px; border-top: 2px solid #005A2B; background: #f8fafc; border-radius: 6px;">
            <div style="font-size: 13px; font-weight: 700; color: #005A2B;">مدير المدرسة</div>
            <div style="font-size: 15px; font-weight: 800; margin-top: 6px; color: #1e293b;">إبراهيم بن موسى التميمي</div>
        </div>
    </div>
    
    <div class="footer">
       - تصميم وتطوير أ/ محمد سامي السعيد  &&  تم استخراج هذا التقرير آلياً من نظام إدارة درجات مدرسة الثغر النموذجية
    </div>
</body>
</html>"""
        return html_content

    # 1. التقرير الشامل للمدرسة
    if rep_type == "📑 التقرير الشامل للمدرسة":
        st.markdown("<div class='report-card'>", unsafe_allow_html=True)
        st.markdown("<div class='report-title'>📑 التقرير الشامل لجميع الصفوف والفصول</div>", unsafe_allow_html=True)
        st.caption(f"عرض نتائج كافة الطلاب لـ ({rep_term} - {rep_week})")
        
        tot_std = len(df_master)
        avg_score = df_master["الدرجة"].mean() if tot_std > 0 else 0
        tot_abs = (df_master["غائب"] == "نعم").sum()
        
        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        m_c1.metric("👥 إجمالي الطلاب", f"{tot_std} طالب")
        m_c2.metric("📈 متوسط درجات المدرسة", f"{avg_score:.1f}%")
        m_c3.metric("⚪ إجمالي الغائبين", f"{tot_abs} طالب")
        m_c4.metric("🏆 نسبة الحضور", f"{((tot_std - tot_abs)/tot_std*100):.1f}%" if tot_std > 0 else "0%")
        
        st.dataframe(df_master, use_container_width=True)

        # رسم بياني للمدرسة
        if _PLOTLY_AVAILABLE:
            fig_school = px.histogram(
                df_master, 
                x="الحالة", 
                title="📊 توزيع مستويات الطلاب على مستوى المدرسة",
                color="الحالة",
                color_discrete_map={
                    "متميز (>75%) 🟢": "#22c55e",
                    "متوسط (50-75%) 🔵": "#3b82f6",
                    "ضعيف (<50%) 🔴": "#ef4444",
                    "غائب ⚪": "#94a3b8"
                }
            )
            st.plotly_chart(fig_school, use_container_width=True)
        else:
            st.info("📊 توزيع المستويات (عادي):")
            st.bar_chart(df_master["الحالة"].value_counts())

        render_signatures_card()
        col_ex1, col_ex2 = st.columns(2)
        with col_ex1:
            excel_data = to_excel(df_master, sheet_name="التقرير الشامل")
            st.download_button("📥 تصدير التقرير الشامل إلى Excel", data=excel_data, file_name=f"Comprehensive_Report_{rep_week}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with col_ex2:
            html_rep = generate_html_report("التقرير الشامل للمدرسة", f"{rep_term} - {rep_week}", df_master, {
                "إجمالي الطلاب": f"{tot_std}",
                "متوسط المدرسة": f"{avg_score:.1f}%",
                "الطلاب الغائبون": f"{tot_abs}"
            })
            st.download_button("🖨️ طباعة / تصدير التقرير الشامل PDF", data=html_rep, file_name=f"Comprehensive_Report_{rep_week}.html", mime="text/html", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # 2. تقرير الصفوف
    elif rep_type == "🏫 تقرير الصفوف":
        st.markdown("<div class='report-card'>", unsafe_allow_html=True)
        col_hdr, col_drop = st.columns([2, 2])
        with col_hdr:
            st.markdown("<div class='report-title'>🏫 تقرير الصفوف الدراسية</div>", unsafe_allow_html=True)
        with col_drop:
            selected_grade = st.selectbox("اختر الصف الدراسي المراد عرض تقريره:", ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"], key="rep_grade_select")

        df_grade = df_master[df_master["الصف الدراسي"] == selected_grade]
        st.caption(f"تقرير نتائج {selected_grade} | {rep_term} - {rep_week}")

        g_tot = len(df_grade)
        g_avg = df_grade["الدرجة"].mean() if g_tot > 0 else 0
        g_abs = (df_grade["غائب"] == "نعم").sum()

        mg1, mg2, mg3 = st.columns(3)
        mg1.metric(f"👥 طلاب {selected_grade}", f"{g_tot} طالب")
        mg2.metric("📈 متوسط درجة الصف", f"{g_avg:.1f}%")
        mg3.metric("⚪ عدد الغائبين بالصف", f"{g_abs} طالب")

        st.dataframe(df_grade, use_container_width=True)

        # رسم بياني للصف
        if _PLOTLY_AVAILABLE:
            fig_grade = px.pie(
                df_grade, 
                names="الحالة", 
                title=f"🎯 الرسم البياني لتوزيع المستويات في {selected_grade}",
                hole=0.4,
                color="الحالة",
                color_discrete_map={
                    "متميز (>75%) 🟢": "#22c55e",
                    "متوسط (50-75%) 🔵": "#3b82f6",
                    "ضعيف (<50%) 🔴": "#ef4444",
                    "غائب ⚪": "#94a3b8"
                }
            )
            st.plotly_chart(fig_grade, use_container_width=True)
        else:
            st.info(f"📊 توزيع المستويات في {selected_grade}:")
            st.bar_chart(df_grade["الحالة"].value_counts())

        render_signatures_card()
        col_gx1, col_gx2 = st.columns(2)
        with col_gx1:
            st.download_button("📥 تصدير تقرير الصف إلى Excel", data=to_excel(df_grade, sheet_name=selected_grade), file_name=f"Report_{selected_grade}_{rep_week}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with col_gx2:
            html_g_rep = generate_html_report(f"تقرير {selected_grade}", f"{rep_term} - {rep_week}", df_grade, {
                "إجمالي طلاب الصف": f"{g_tot}",
                "متوسط درجات الصف": f"{g_avg:.1f}%",
                "عدد الغائبين": f"{g_abs}"
            })
            st.download_button("🖨️ طباعة / تصدير تقرير الصف PDF", data=html_g_rep, file_name=f"Report_{selected_grade}_{rep_week}.html", mime="text/html", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # 3. تقرير فصل محدد
    elif rep_type == "🏛️ تقرير فصل محدد":
        st.markdown("<div class='report-card'>", unsafe_allow_html=True)
        col_hdr2, col_d1, col_d2 = st.columns([2, 1.5, 1.5])
        with col_hdr2:
            st.markdown("<div class='report-title'>🏛️ تقرير فصل محدد</div>", unsafe_allow_html=True)
        with col_d1:
            cls_grade = st.selectbox("اختر الصف:", ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"], key="cls_g_select")
        with col_d2:
            available_classes_rep = list(STUDENTS_DB_GRADES.get(cls_grade, {}).keys()) or [1]
            cls_num = st.selectbox("اختر الفصل/الشعبة:", available_classes_rep, key="cls_n_select")

        df_class = df_master[(df_master["الصف الدراسي"] == cls_grade) & (df_master["الفصل / الشعبة"] == f"فصل {cls_num}")]
        st.caption(f"تقرير نتائج {cls_grade} - فصل ({cls_num}) | {rep_term} - {rep_week}")

        c_tot = len(df_class)
        c_avg = df_class["الدرجة"].mean() if c_tot > 0 else 0
        c_abs = (df_class["غائب"] == "نعم").sum()

        mc1, mc2, mc3 = st.columns(3)
        mc1.metric(f"👥 طلاب فصل ({cls_num})", f"{c_tot} طالب")
        mc2.metric("📈 متوسط الدرجة للفصل", f"{c_avg:.1f}%")
        mc3.metric("⚪ غياب الفصل", f"{c_abs} طالب")

        st.dataframe(df_class, use_container_width=True)

        if _PLOTLY_AVAILABLE:
            fig_cls = px.bar(
                df_class, 
                x="اسم الطالب", 
                y="الدرجة", 
                color="الحالة",
                title=f"📊 درجات طلاب {cls_grade} - فصل ({cls_num})",
                color_discrete_map={
                    "متميز (>75%) 🟢": "#22c55e",
                    "متوسط (50-75%) 🔵": "#3b82f6",
                    "ضعيف (<50%) 🔴": "#ef4444",
                    "غائب ⚪": "#94a3b8"
                }
            )
            st.plotly_chart(fig_cls, use_container_width=True)
        else:
            st.info(f"📊 درجات طلاب {cls_grade} - فصل ({cls_num}):")
            st.bar_chart(df_class.set_index("اسم الطالب")["الدرجة"])

        render_signatures_card()
        col_cx1, col_cx2 = st.columns(2)
        with col_cx1:
            st.download_button(f"📥 تصدير تقرير فصل ({cls_num}) إلى Excel", data=to_excel(df_class, sheet_name=f"فصل_{cls_num}"), file_name=f"Report_{cls_grade}_Class{cls_num}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with col_cx2:
            html_c_rep = generate_html_report(f"تقرير {cls_grade} - فصل ({cls_num})", f"{rep_term} - {rep_week}", df_class, {
                "عدد الطلاب": f"{c_tot}",
                "متوسط الفصل": f"{c_avg:.1f}%",
                "عدد الغائبين": f"{c_abs}"
            })
            st.download_button(f"🖨️ طباعة / تصدير تقرير فصل ({cls_num}) PDF", data=html_c_rep, file_name=f"Report_{cls_grade}_Class{cls_num}.html", mime="text/html", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # 4. تقرير تحليل النواتج
    elif rep_type == "📊 تقرير تحليل النواتج والافتراق التحصيلي":
        st.markdown("<div class='report-card'>", unsafe_allow_html=True)
        st.markdown("<div class='report-title'>📊 تقرير تحليل نواتج التعلم والافتراق التحصيلي</div>", unsafe_allow_html=True)
        st.caption(f"تحليل إحصائي شامل ومقارنة أداء الصفوف لـ ({rep_term} - {rep_week})")

        analysis_rows = []
        for g_name in ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"]:
            df_g = df_master[df_master["الصف الدراسي"] == g_name]
            g_tot = len(df_g)
            if g_tot == 0:
                continue
            
            weak_cnt = len(df_g[df_g["الحالة"] == "ضعيف (<50%) 🔴"])
            mid_cnt = len(df_g[df_g["الحالة"] == "متوسط (50-75%) 🔵"])
            exc_cnt = len(df_g[df_g["الحالة"] == "متميز (>75%) 🟢"])
            abs_cnt = len(df_g[df_g["غائب"] == "نعم"])
            avg_sc = df_g["الدرجة"].mean()

            analysis_rows.append({
                "الصف الدراسي": g_name,
                "إجمالي الطلاب": g_tot,
                "المتوسط العام": f"{avg_sc:.1f}%",
                "الطلاب الضعاف (<50%)": f"{weak_cnt} ({weak_cnt/g_tot*100:.1f}%)",
                "الطلاب المتوسطون (50-75%)": f"{mid_cnt} ({mid_cnt/g_tot*100:.1f}%)",
                "الطلاب المتميزون (>75%)": f"{exc_cnt} ({exc_cnt/g_tot*100:.1f}%)",
                "الغائبون": f"{abs_cnt} ({abs_cnt/g_tot*100:.1f}%)"
            })

        df_outcomes = pd.DataFrame(analysis_rows)
        st.subheader("📈 جدول المقارنة الإحصائية لنواتج التعلم بين الصفوف:")
        st.dataframe(df_outcomes, use_container_width=True)

        # رسم بياني لمقارنة نواتج التعلم
        chart_data = []
        for g_name in ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"]:
            df_g = df_master[df_master["الصف الدراسي"] == g_name]
            g_tot = len(df_g)
            if g_tot > 0:
                chart_data.append({"الصف": g_name, "الفئة": "ضعاف (<50%)", "العدد": len(df_g[df_g["الحالة"] == "ضعيف (<50%) 🔴"])})
                chart_data.append({"الصف": g_name, "الفئة": "متوسطون (50-75%)", "العدد": len(df_g[df_g["الحالة"] == "متوسط (50-75%) 🔵"])})
                chart_data.append({"الصف": g_name, "الفئة": "متميزون (>75%)", "العدد": len(df_g[df_g["الحالة"] == "متميز (>75%) 🟢"])})
                chart_data.append({"الصف": g_name, "الفئة": "غائبون", "العدد": len(df_g[df_g["غائب"] == "نعم"])})

        df_chart = pd.DataFrame(chart_data)
        if not df_chart.empty:
            if _PLOTLY_AVAILABLE:
                fig_outcomes = px.bar(
                    df_chart, 
                    x="الصف", 
                    y="العدد", 
                    color="الفئة", 
                    barmode="group",
                    title="📊 مقارنة توزيع الفئات التحصيلية بين المرحلة المتوسطة",
                    color_discrete_map={
                        "متميزون (>75%)": "#22c55e",
                        "متوسطون (50-75%)": "#3b82f6",
                        "ضعاف (<50%)": "#ef4444",
                        "غائبون": "#94a3b8"
                    }
                )
                st.plotly_chart(fig_outcomes, use_container_width=True)
            else:
                st.info("📊 مقارنة الفئات التحصيلية بين الصفوف:")
                pivot_df = df_chart.pivot(index="الصف", columns="الفئة", values="العدد").fillna(0)
                st.bar_chart(pivot_df)

        render_signatures_card()
        col_ox1, col_ox2 = st.columns(2)
        with col_ox1:
            st.download_button("📥 تصدير تقرير تحليل النواتج إلى Excel", data=to_excel(df_outcomes, sheet_name="تحليل النواتج"), file_name=f"Outcomes_Analysis_{rep_week}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        with col_ox2:
            html_o_rep = generate_html_report("تقرير تحليل نواتج التعلم", f"{rep_term} - {rep_week}", df_outcomes, {
                "الفصل الدراسي": rep_term,
                "الأسبوع المستهدف": rep_week,
                "عدد الصفوف المحللة": f"{len(df_outcomes)}"
            })
            st.download_button("🖨️ طباعة / تصدير تقرير تحليل النواتج PDF", data=html_o_rep, file_name=f"Outcomes_Analysis_{rep_week}.html", mime="text/html", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# الصفحة الرابعة: إدارة الطلاب (إضافة / حذف / نقل) (جديدة)
# =========================================================
elif page == "👥 إدارة الطلاب (إضافة / حذف / نقل)":
    st.title("👥 صفحة إدارة بيانات الطلاب")
    st.markdown("يمكنك من خلال هذه الصفحة **إضافة طالب جديد**، **حذف طالب**، أو **نقل طالب من فصل إلى آخر** بكل سهولة مع الحفظ المباشر.")
    
    tab_add, tab_del, tab_transfer = st.tabs([
        "➕ إضافة طالب جديد",
        "🗑️ حذف طالب",
        "🔄 نقل طالب بين الفصول"
    ])

    # 1. إضافة طالب جديد
    with tab_add:
        st.subheader("➕ إضافة طالب جديد إلى المدرسة")
        with st.form("add_student_form", clear_on_submit=True):
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                new_id = st.text_input("رقم الهوية / الرقم الأكاديمي (10 أرقام):", placeholder="مثال: 1122334455")
                new_name = st.text_input("اسم الطالب الرباعي:", placeholder="مثال: أحمد محمد علي الغامدي")
            with col_a2:
                new_grade = st.selectbox("الصف الدراسي:", ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"], key="add_g_select")
                new_class = st.selectbox("الفصل / الشعبة:", [1, 2, 3], key="add_c_select")
                new_phone = st.text_input("رقم جوال ولي الأمر:", placeholder="مثال: 966501234567")
            
            btn_add = st.form_submit_button("💾 حفظ وإضافة الطالب إلى القائمة")
            
            if btn_add:
                if not new_id or not new_name or not new_phone:
                    st.error("⚠️ يرجى ملء كافة البيانات المطلوبة (الهوية، الاسم، الجوال).")
                else:
                    new_id_clean = str(new_id).strip()
                    # إضافة إلى st.session_state
                    if new_grade not in st.session_state["students_db"]:
                        st.session_state["students_db"][new_grade] = {}
                    if new_class not in st.session_state["students_db"][new_grade]:
                        st.session_state["students_db"][new_grade][new_class] = []
                    
                    # التحقق من عدم التكرار
                    existing_ids = [str(st_item["id"]) for g in st.session_state["students_db"].values() for c in g.values() for st_item in c]
                    if new_id_clean in existing_ids:
                        st.warning("⚠️ رقم الهوية هذا موجود بالفعل لطالب آخر!")
                    else:
                        st.session_state["students_db"][new_grade][new_class].append({
                            "id": new_id_clean,
                            "name": new_name.strip(),
                            "grade": new_grade,
                            "class": new_class,
                            "phone": str(new_phone).strip()
                        })
                        # تحديث Supabase إذا كان متصلاً
                        update_student_phone_db(new_id_clean, new_phone.strip())
                        st.success(f"✅ تم إضافة الطالب **{new_name}** بنجاح إلى **{new_grade} - فصل ({new_class})**!")
                        st.rerun()

    # 2. حذف طالب
    with tab_del:
        st.subheader("🗑️ حذف طالب من قاعدة البيانات")
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            del_grade = st.selectbox("اختر الصف الدراسي للطالب:", ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"], key="del_g_select")
        with col_d2:
            avail_classes_del = list(st.session_state["students_db"].get(del_grade, {}).keys()) or [1]
            del_class = st.selectbox("اختر الفصل / الشعبة:", avail_classes_del, key="del_c_select")
            
        current_class_students = st.session_state["students_db"].get(del_grade, {}).get(del_class, [])
        if not current_class_students:
            st.info("لا يوجد طلاب مسجلون في هذا الفصل حالياً.")
        else:
            student_options = {f"{s['name']} (هوية: {s['id']})": s for s in current_class_students}
            selected_st_label = st.selectbox("اختر الطالب المراد حذفه:", list(student_options.keys()))
            selected_st_obj = student_options[selected_st_label]
            
            st.error(f"⚠️ **تنبيه:** سيتم حذف الطالب **{selected_st_obj['name']}** نهائياً من المدرسة وقاعدة البيانات.")
            if st.button("🗑️ تأكيد حذف الطالب نهائياً"):
                # حذف من Session State
                st.session_state["students_db"][del_grade][del_class] = [
                    s for s in st.session_state["students_db"][del_grade][del_class] if str(s["id"]) != str(selected_st_obj["id"])
                ]
                # حذف من Supabase إذا كان متصلاً
                delete_student_from_db(selected_st_obj["id"])
                st.success(f"✅ تم حذف الطالب {selected_st_obj['name']} بنجاح.")
                st.rerun()

    # 3. نقل طالب بين الفصول
    with tab_transfer:
        st.subheader("🔄 نقل طالب من فصل إلى فصل آخر")
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            src_grade = st.selectbox("من صف:", ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"], key="src_g_select")
            avail_src_classes = list(st.session_state["students_db"].get(src_grade, {}).keys()) or [1]
            src_class = st.selectbox("من فصل:", avail_src_classes, key="src_c_select")
            
            src_students = st.session_state["students_db"].get(src_grade, {}).get(src_class, [])
            if src_students:
                tr_student_map = {f"{s['name']} ({s['id']})": s for s in src_students}
                selected_tr_label = st.selectbox("اختر الطالب المراد نقله:", list(tr_student_map.keys()))
                selected_tr_obj = tr_student_map[selected_tr_label]
            else:
                selected_tr_obj = None
                st.info("لا يوجد طلاب في هذا الفصل لنقلهم.")
                
        with col_t2:
            target_grade = st.selectbox("إلى صف:", ["الأول المتوسط", "الثاني المتوسط", "الثالث المتوسط"], key="tgt_g_select")
            target_class = st.selectbox("إلى فصل:", [1, 2, 3], key="tgt_c_select")
            
        if selected_tr_obj and st.button("🔄 تأكيد نقل الطالب الآن"):
            # 1. إزالة من المكان الحالي
            st.session_state["students_db"][src_grade][src_class] = [
                s for s in st.session_state["students_db"][src_grade][src_class] if str(s["id"]) != str(selected_tr_obj["id"])
            ]
            # 2. إضافة إلى المكان الجديد
            if target_grade not in st.session_state["students_db"]:
                st.session_state["students_db"][target_grade] = {}
            if target_class not in st.session_state["students_db"][target_grade]:
                st.session_state["students_db"][target_grade][target_class] = []
                
            updated_st = copy.deepcopy(selected_tr_obj)
            updated_st["grade"] = target_grade
            updated_st["class"] = target_class
            
            st.session_state["students_db"][target_grade][target_class].append(updated_st)
            st.success(f"✅ تم نقل الطالب **{selected_tr_obj['name']}** بنجاح إلى **{target_grade} - فصل ({target_class})**!")
            st.rerun()
