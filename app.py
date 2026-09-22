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
