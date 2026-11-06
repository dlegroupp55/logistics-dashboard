import streamlit as st
import pandas as pd
import plotly.express as px

# Настройка страницы в стиле скриншота
st.set_page_config(page_title="Монитор импортных поставок", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    h1, h2, h3 { color: #1E293B; font-family: 'Segoe UI', sans-serif; }
    .stMetric { background-color: #F8FAFC; padding: 1.5rem; border-radius: 0.5rem; border: 1px solid #E2E8F0; }
    </style>
""", unsafe_allow_html=True)

st.title("📂 Монитор импортных поставок")
st.caption("Система аналитики логистических партий импорта")

# Компонент загрузки файла
uploaded_file = st.file_uploader("Перетащите сюда файл Excel (.xlsx) или выгрузку CSV / TXT", type=["xlsx", "csv", "txt"])

if uploaded_file is not None:
    try:
        # Чтение файла (поддерживает и Excel, и CSV с автоопределением)
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file)
        else:
            df = pd.read_csv(uploaded_file, sep=None, engine='python')
        
        # Очистка названий колонок от лишних пробелов
        df.columns = df.columns.str.strip()
        
        # Преобразование дат
        date_cols = ['Фактическая дата прибытия на склад', 'Дата забора груза у отправителя', 'Факт Дата готовности заказа у отправимтеля', 'Фактическая дата отправления груза', 'Дата прибытия на таможню']
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Обработка пустых статусов
        if 'Статус' in df.columns:
            df['Статус'] = df['Статус'].fillna('В производстве')
            # Если статус передан строкой, но пустой в ячейке, тоже заполняем
            df['Статус'] = df['Статус'].replace(r'^\s*$', 'В производстве', regex=True)
        else:
            df['Статус'] = 'В производстве'
            
        # Расчет Lead Time по формуле: Фактическая дата прибытия - Дата забора
        if 'Фактическая дата прибытия на склад' in df.columns and 'Дата забора груза у отправителя' in df.columns:
            df['Lead Time (вычисленный)'] = (df['Фактическая дата прибытия на склад'] - df['Дата забора груза у отправителя']).dt.days
        else:
            df['Lead Time (вычисленный)'] = None

        # --- БЛОК ФИЛЬТРОВ ---
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            carriers = ['-- Все перевозчики --'] + sorted(df['Перевозчик'].dropna().unique().tolist())
            selected_carrier = st.selectbox("Перевозчик", carriers)
            
        with col_f2:
            countries = ['-- Все страны --'] + sorted(df['Страна отправления'].dropna().unique().tolist())
            selected_country = st.selectbox("Страна отправления", countries)
            
        with col_f3:
            statuses = ['-- Все статусы --'] + sorted(df['Статус'].dropna().unique().tolist())
            selected_status = st.selectbox("Текущий статус", statuses)
            
        # Фильтрация датафрейма
        filtered_df = df.copy()
        if selected_carrier != '-- Все перевозчики --':
            filtered_df = filtered_df[filtered_df['Перевозчик'] == selected_carrier]
        if selected_country != '-- Все страны --':
            filtered_df = filtered_df[filtered_df['Страна отправления'] == selected_country]
        if selected_status != '-- Все statuses --':
            filtered_df = filtered_df[filtered_df['Статус'] == selected_status]

        # --- БЛОК КАРТОЧЕК (KPI) ---
        st.write("---")
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        
        with kpi1:
            st.metric("Всего заказов в работе", len(filtered_df))
            
        with kpi2:
            total_sum = filtered_df['Сумма инвойса'].sum() if 'Сумма инвойса' in filtered_df.columns else 0
            st.metric("Общая сумма инвойсов (FCA)", f"${total_sum:,.2f}")
            
        with kpi3:
            # Расчет задержек (если Плановая дата < Текущей, а Фактической еще нет)
            delays = 0
            if 'Плановая Дата прибытия на склад' in filtered_df.columns:
                plan_date = pd.to_datetime(filtered_df['Плановая Дата прибытия на склад'], errors='coerce')
                delays = ((plan_date < pd.Timestamp.now()) & (filtered_df['Фактическая дата прибытия на склад'].isna())).sum()
            st.metric("Критические задержки", delays, delta_color="inverse")
            
        with kpi4:
            avg_lead_time = filtered_df['Lead Time (вычисленный)'].mean()
            st.metric("Средний Lead Time", f"{avg_lead_time:.1f} дн." if not pd.isna(avg_lead_time) else "0 дн.")

        # --- БЛОК ГРАФИКОВ ---
        st.write("---")
        g1, g2 = st.columns(2)
        
        with g1:
            st.subheader("📊 Воронка логистических этапов")
            funnel_data = filtered_df['Статус'].value_counts().reset_index()
            funnel_data.columns = ['Этап', 'Количество партий']
            
            # Сортировка по логическому порядку этапов
            stage_order = ['В производстве', 'В пути', 'На таможне', 'Прибыл на склад']
            funnel_data['Этап'] = pd.Categorical(funnel_data['Этап'], categories=stage_order, ordered=True)
            funnel_data = funnel_data.sort_values('Этап')
            
            fig_funnel = px.bar(funnel_data, x='Количество партий', y='Этап', orientation='h',
                                color='Этап', color_discrete_sequence=px.colors.qualitative.Safe)
            fig_funnel.update_layout(showlegend=False, height=300, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig_funnel, use_container_width=True)
            
        with g2:
            st.subheader("⏱ Рейтинг перевозчиков: Средний срок доставки (дней)")
            if 'Lead Time (вычисленный)' in filtered_df.columns and filtered_df['Lead Time (вычисленный)'].notna().any():
                carrier_data = filtered_df.groupby('Перевозчик')['Lead Time (вычисленный)'].mean().reset_index()
                carrier_data = carrier_data.sort_values(by='Lead Time (вычисленный)', ascending=False)
                
                fig_carrier = px.bar(carrier_data, x='Lead Time (вычисленный)', y='Перевозчик', orientation='h',
                                     labels={'Lead Time (вычисленный)': 'Дни'}, color_discrete_sequence=['#F59E0B'])
                fig_carrier.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig_carrier, use_container_width=True)
            else:
                st.info("Нет завершенных поставок для расчета сроков перевозчиков.")

        # --- РЕЕСТР ПАРТИЙ ---
        st.write("---")
        st.subheader("📋 Реестр логистических партий импорта")
        
        # Выбираем ключевые колонки для красивого отображения в таблице
        display_cols = ['Статус', 'Номер заказа поставщику в 1С', 'Поставщик', 'Страна отправления', 'Сумма инвойса', 'Перевозчик', 'Дата забора груза у отправителя', 'Фактическая дата прибытия на склад', 'Lead Time (вычисленный)']
        available_cols = [c for c in display_cols if c in filtered_df.columns]
        
        st.dataframe(filtered_df[available_cols].style.format(subset=['Сумма инвойса'], formatter="${:,.2f}"), use_container_width=True)

    except Exception as e:
        st.error(f"Ошибка при разборе файла. Убедитесь, что структура колонок совпадает с шаблоном. Техническая ошибка: {e}")
else:
    st.info("Ожидание загрузки файла данных для формирования дашборда.")
