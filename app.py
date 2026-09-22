elif page == "🏫 إدارة المدرسة وتقارير أولياء الأمور":
    st.subheader("🏫 إدارة المدرسة وإرسال وتقارير أولياء الأمور")
    
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        weeks = [f"الأسبوع {i}" for i in range(1, 19)]
        selected_week = st.selectbox("اختر الأسبوع لعرض التقرير والرسائل:", weeks)
    with col_w2:
        selected_term = st.selectbox("اختر الفصل الدراسي:", ["الفصل الدراسي الأول", "الفصل الدراسي الثاني"])
        
    st.markdown("---")

    conn = get_db_connection()
    query = """
        SELECT s.id, s.name, s.grade, s.class, s.phone, g.score, g.is_absent
        FROM students s
        LEFT JOIN grades g ON s.id = g.student_id AND g.term = ? AND g.week = ?
        ORDER BY s.grade, s.class, s.name
    """
    df_reports = pd.read_sql_query(query, conn, params=(selected_term, selected_week))
    conn.close()

    cat_red, cat_blue, cat_green, cat_gray = [], [], [], []

    for idx, r in df_reports.iterrows():
        sc = r["score"]
        is_abs = r["is_absent"]
        msg = generate_parent_message(r["name"], sc, is_abs)
        
        row_dict = {
            "id": r["id"],
            "name": r["name"],
            "grade": r["grade"],
            "class": r["class"],
            "phone": r["phone"],
            "score": sc if (sc is not None and is_abs == 0) else 0.0,
            "is_absent": is_abs,
            "message": msg
        }
        
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

    st.markdown("##### 📱 قناتا الإرسال المتاحتان لولي الأمر (WhatsApp + Mora SMS):")
    col_info1, col_info2 = st.columns(2)
    with col_info1:
        st.success("💬 **واتساب (WhatsApp):** رابط مباشر يفتح تطبيق الواتساب مع النص المجهز مسبقاً بنقرة زر.")
    with col_info2:
        st.info("📱 **Mora SMS (مورا):** إرسال مباشر عبر البوابة المدرسية المعتمدة (mora-sa.com) مع دعم الإرسال الفردي والجماعي.")

    st.markdown("### 📋 تفاصيل الرسائل النصية الموجهة حسب الفئات:")

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
            
            # خيار الإرسال الجماعي Bulk SMS عبر Mora
            with st.expander(f"🚀 إرسال جماعي (Bulk SMS عبر Mora) لجميع طلاب {cat_name} ({len(cat_list)} طالب)"):
                st.write(f"سيتم إرسال الرسائل النصية القصيرة تلقائياً عبر منصة Mora إلى جميع أرقام أولياء أمور {cat_name}.")
                if st.button(f"⚡ إرسال SMS جماعي لجميع طلاب {cat_name}", key=f"bulk_sms_{cat_name}"):
                    with st.spinner("جاري الإرسال الجماعي عبر Mora SMS..."):
                        succ, fail, details = send_mora_bulk_sms(
                            cat_list, username=mora_user, password=mora_pass, sender_name=mora_sender, otp_code=mora_otp
                        )
                        st.success(f"✅ اكتملت عملية الإرسال! النجاح: {succ} | الفشل: {fail}")

            st.markdown("---")

            for item in cat_list:
                wa_link = create_whatsapp_url(item['phone'], item['message'])
                with st.expander(f"👤 {item['name']} ({item['grade']} - فصل {item['class']}) | جوال ولي الأمر: {item['phone']}"):
                    st.write(f"**رقم الهوية:** {item['id']}")
                    st.write(f"**النسبة المئوية / الدرجة:** {item['score']}%" if item['is_absent'] == 0 else "**الحالة:** غائب ⚪")
                    st.info(f"💬 **نص الرسالة الموجهة:**\n\n{item['message']}")
                    
                    btn_col1, btn_col2 = st.columns(2)
                    
                    with btn_col1:
                        st.markdown(f'''
                        <a href="{wa_link}" target="_blank" style="text-decoration:none;">
                            <div style="background-color:#25D366; color:white; padding:10px 14px; border-radius:6px; text-align:center; font-weight:bold; font-size:14px; margin-top:5px; display:block;">
                                💬 إرسال عبر الواتساب (WhatsApp)
                            </div>
                        </a>
                        ''', unsafe_allow_html=True)
                        
                    with btn_col2:
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
