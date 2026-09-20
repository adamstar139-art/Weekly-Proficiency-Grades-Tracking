import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import io
import copy
import urllib.parse
import requests

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
        key = st.secrets.get("key") or st.secrets.get("SUPABASE_KEY") or st.secrets.get("anon_key")

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
# 3. قائمة الطلاب الأساسية
# =========================================================
STUDENTS_DB_GRADES = {
    "الأول المتوسط": {
        1: [
            {"id": "1167628468", "name": "ابراهيم بن محمد بن علي الوهيبي", "phone": "966504158122"},
            {"id": "2395664317", "name": "بلال عبدالرزاق عيسى العيسى", "phone": "966507448712"},
            {"id": "1170582165", "name": "حسام بن محمد بن علي ال رايان البارقي", "phone": "966504445699"},
            {"id": "1169004353", "name": "ريان عبدالله جابر الاسمري", "phone": "966554260960"},
            {"id": "2446713998", "name": "زيد زياد عبد اللطيف ابو قبع", "phone": "966590123455"},
            {"id": "2527104554", "name": "سامي سعد عباس حمد", "phone": "966591781701"},
            {"id": "1170111759", "name": "سعد ناصر سعد السيف", "phone": "966503219351"},
            {"id": "1195559479", "name": "عبدالعزيز عبدالله عبدالعزيز العمار", "phone": "966555838394"},
            {"id": "1153310501", "name": "عبدالله بن سليمان بن عبدالله الراجحي", "phone": "0551418881"},
            {"id": "1170836520", "name": "عبدالله سعد بن محمد العيشان", "phone": "966504217660"},
            {"id": "1171448515", "name": "علي احمد علي كريري", "phone": "966558885481"},
            {"id": "1170853053", "name": "علي سعد علي القحطاني", "phone": "966505466546"},
            {"id": "1172018036", "name": "عمر عبدالله سعد الجبرين", "phone": "966555249420"},
            {"id": "2552851368", "name": "مازن اسلام احمد ابراهيم موسى", "phone": "966550490495"},
            {"id": "013609321", "name": "محمد أحمد علي عقيل", "phone": "966546000184"},
            {"id": "2394606749", "name": "محمد اشرف مسعود ابوخاطر", "phone": "966501276888"},
            {"id": "1170042046", "name": "محمد بن فيصل بن مصلح الشمراني", "phone": "966555832145"},
            {"id": "1169174164", "name": "محمد نايف فراج الدعجاني", "phone": "966554444782"},
            {"id": "2380890976", "name": "وائل بولعيش", "phone": "966591534495"}
        ],
        2: [
            {"id": "1170348286", "name": "الوليد ابن خالد بن فهد العتيبي", "phone": "966558522229"},
            {"id": "1172433185", "name": "باسل محمد فرج الدوسري", "phone": "966537589781"},
            {"id": "1173391556", "name": "بسام بن عبدالكريم بن عبدالله الحرقان الدوسري", "phone": "966534467820"},
            {"id": "1169185053", "name": "تركي عبدالله مسفر الدوسري", "phone": "966505258369"},
            {"id": "1170108078", "name": "تميم فهد عبدالعزيز العزاز", "phone": "966554435692"}
        ]
    },
    "الثاني المتوسط": {
        1: [
            {"id": "1163760935", "name": "احمد سامي بن احمد العمران", "phone": "966551501503"},
            {"id": "1153756612", "name": "الوليد عبدالله بن ابراهيم المبدل", "phone": "966505241627"},
            {"id": "1164269209", "name": "ذياب بن محمد بن ذياب القحطاني", "phone": "966561169999"}
        ]
    },
    "الثالث المتوسط": {
        1: [
            {"id": "1158966166", "name": "أاصيل ناصر بن محمد مذكور", "phone": "966552149044"},
            {"id": "1162308223", "name": "خالد محمد مسدف معافا", "phone": "966552680201"}
        ]
    }
}

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
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
html, body, [class*="css"], div, span, button, input, select {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl;
    text-align: right;
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

# بنر اليوم الوطني وتحديث الهوية
st.markdown("""
<div class="national-day-banner">
    <div class="national-day-title">🇸🇦 نحلم ونحقق - اليوم الوطني السعودي 🌴⚔️</div>
    <div class="national-day-sub">مدرسة متوسطة الثغر النموذجية الأهلية - نظام رصد درجات الإتقان الأسبوعية</div>
</div>
""", unsafe_allow_html=True)

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
    mora_user = st.text_input("اسم المستخدم / الرقم:", value="966560229124", key="mora_u")
    mora_pass = st.text_input("كلمة المرور:", value="THA@0508634881", type="password", key="mora_p")
    mora_sender = st.text_input("اسم المرسل المعتمد:", value="S", key="mora_s")
    mora_otp = st.text_input("كود التحقق / OTP (إذا طلب):", value="", key="mora_otp_input")

st.sidebar.markdown("---")
page = st.sidebar.radio("اختر الصفحة:", ["📝 صفحة الرصد", "🏫 إدارة المدرسة وتقارير أولياء الأمور"])

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
        class_num = st.selectbox("الفصل / الشعبة:", [1, 2, 3])
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

                col_name, col_score, col_absent = st.columns([3, 2, 1])
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

            st.markdown("---")

            for item in cat_list:
                wa_manual_url = create_whatsapp_web_url(item['phone'], item['message'])
                with st.expander(f"👤 {item['name']} ({item['grade']} - فصل {item['class']}) | جوال ولي الأمر: {item['phone']}"):
                    st.write(f"**رقم الهوية:** {item['id']}")
                    st.write(f"**النسبة المئوية / الدرجة:** {item['score']}%" if item['is_absent'] == 0 else "**الحالة:** غائب ⚪")
                    st.info(f"""💬 **نص الرسالة الموجهة:**

{item['message']}""")
                    
                    btn_col1, btn_col2, btn_col3 = st.columns(3)
                    
                    with btn_col1:
                        if st.button(f"💬 إرسال واتساب تلقائي (مباشر)", key=f"wa_direct_{item['id']}"):
                            with st.spinner("جاري الإرسال المباشر..."):
                                ok, resp = send_whatsapp_direct_api(item['phone'], item['message'], wa_instance, wa_token)
                                if ok:
                                    st.success(f"✅ {resp}")
                                else:
                                    st.error(f"❌ {resp}")
                        
                    with btn_col2:
                        st.markdown(f'''
                        <a href="{wa_manual_url}" target="_blank" style="text-decoration:none;">
                            <div style="background-color:#25D366; color:white; padding:8px 12px; border-radius:6px; text-align:center; font-weight:bold; font-size:13px; margin-top:2px; display:block;">
                                🌐 فتح في تطبيق الواتساب
                            </div>
                        </a>
                        ''', unsafe_allow_html=True)

                    with btn_col3:
                        if st.button(f"📱 إرسال SMS (Mora)", key=f"single_sms_{item['id']}"):
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
