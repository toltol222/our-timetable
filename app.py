# app.py
# =========================================================
# [중요] requirements.txt 예시
# streamlit>=1.28
# st-gsheets-connection
# pandas
#
# [중요] Google Sheet 안에 아래 워크시트(tab)를 미리 만들어 주세요.
# 1) PlannerData
# 2) PlannerConfig
#
# [중요] Streamlit Secrets 형식 예시
# (로컬: .streamlit/secrets.toml / 배포: Streamlit Cloud > App settings > Secrets)
#
# [connections.gsheets]
# spreadsheet = "https://docs.google.com/spreadsheets/d/여기에_스프레드시트_ID_or_URL/edit#gid=0"
# type = "service_account"
# project_id = "xxx"
# private_key_id = "xxx"
# private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
# client_email = "xxx@xxx.iam.gserviceaccount.com"
# client_id = "xxx"
# auth_uri = "https://accounts.google.com/o/oauth2/auth"
# token_uri = "https://oauth2.googleapis.com/token"
# auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
# client_x509_cert_url = "xxx"
#
# [설정 팁]
# - Google Cloud에서 서비스 계정을 만들고
# - 그 서비스 계정 이메일을 구글 시트에 공유해야 합니다.
# - 이 앱은 읽기+쓰기(update)가 필요하므로 Editor 권한으로 공유하는 것을 권장합니다.
# =========================================================

import re
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# -------------------------------------------------
# 기본 설정
# -------------------------------------------------
st.set_page_config(
    page_title="나만의 하이테크 진도표",
    page_icon="📚",
    layout="wide",
)

DAYS = ["월", "화", "수", "목", "금"]
PERIODS = ["1교시", "2교시", "3교시", "4교시", "5교시", "6교시", "7교시"]
ROW_ORDER = PERIODS + ["종례"]

PLANNING_YEAR = 2026

DATA_WORKSHEET = "PlannerData"
CONFIG_WORKSHEET = "PlannerConfig"

# 사용자 식별 열 추가
DATA_COLS = ["ID", "수업날짜", "기록일시", "요일", "구분", "교시", "반", "유형", "내용", "목표"]
CONFIG_COLS = ["ID", "요일", "교시", "학급"]


# -------------------------------------------------
# Google Sheets 연결
# -------------------------------------------------
@st.cache_resource
def get_gsheets_conn():
    return st.connection("gsheets", type=GSheetsConnection)


def normalize_df_columns(df: pd.DataFrame, expected_cols: list[str]) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=expected_cols)

    temp = df.copy()
    for col in expected_cols:
        if col not in temp.columns:
            temp[col] = ""
    temp = temp[expected_cols].copy()
    return temp.fillna("")


def read_sheet_df(worksheet_name: str, expected_cols: list[str]) -> pd.DataFrame:
    conn = get_gsheets_conn()
    try:
        df = conn.read(worksheet=worksheet_name, ttl=0)
    except Exception:
        return pd.DataFrame(columns=expected_cols)

    return normalize_df_columns(df, expected_cols)


def write_sheet_df(worksheet_name: str, df: pd.DataFrame, expected_cols: list[str]) -> None:
    conn = get_gsheets_conn()
    safe_df = normalize_df_columns(df, expected_cols)
    conn.update(worksheet=worksheet_name, data=safe_df)
    st.cache_data.clear()


# -------------------------------------------------
# 사용자 / 식별 유틸
# -------------------------------------------------
def sanitize_user_name(name: str) -> str:
    name = str(name).strip()
    if not name:
        return ""
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", "_", name)
    return name


# -------------------------------------------------
# 키 생성 함수
# -------------------------------------------------
def make_date_key(day: str, user_id: str) -> str:
    return f"lesson_date_{user_id}_{day}"


def make_goal_key(day: str, user_id: str) -> str:
    return f"goal_{user_id}_{day}"


def make_input_key(day: str, row_name: str, user_id: str) -> str:
    return f"content_{user_id}_{day}_{row_name}"


def make_config_key(day: str, period: str, user_id: str) -> str:
    return f"config_{user_id}_{day}_{period}"


# -------------------------------------------------
# 날짜 / 주차 유틸
# -------------------------------------------------
def to_date_safe(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return date.today()


def get_today_day_label() -> str:
    idx = datetime.now().weekday()  # 월=0 ... 일=6
    if 0 <= idx <= 4:
        return DAYS[idx]
    return "월"


def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def get_friday(d: date) -> date:
    return get_monday(d) + timedelta(days=4)


def get_week_of_month(d: date) -> int:
    first_day = d.replace(day=1)
    first_monday_offset = (7 - first_day.weekday()) % 7
    first_monday = first_day + timedelta(days=first_monday_offset)

    monday = get_monday(d)
    if monday < first_monday:
        return 1
    return ((monday - first_monday).days // 7) + 2


def format_week_label(week_start: date) -> str:
    week_end = week_start + timedelta(days=4)
    month_week = get_week_of_month(week_start)
    return f"{week_start.year}년 {week_start.month}월 {month_week}주차 ({week_start:%m.%d}~{week_end:%m.%d})"


def generate_year_week_starts(year: int) -> list[date]:
    start = date(year, 1, 1)
    end = date(year, 12, 31)

    current = get_monday(start)
    weeks = []
    while current <= end:
        weeks.append(current)
        current += timedelta(days=7)
    return weeks


# -------------------------------------------------
# 데이터프레임 생성
# -------------------------------------------------
def create_empty_data_df() -> pd.DataFrame:
    return pd.DataFrame(columns=DATA_COLS)


def create_empty_config_df() -> pd.DataFrame:
    rows = []
    for day in DAYS:
        for period in PERIODS:
            rows.append({"ID": "", "요일": day, "교시": period, "학급": ""})
    return pd.DataFrame(rows, columns=CONFIG_COLS)


# -------------------------------------------------
# Google Sheets 기반 데이터 처리
# -------------------------------------------------
def load_user_data(user_name: str) -> pd.DataFrame:
    teacher_id = str(user_name).strip()
    all_df = read_sheet_df(DATA_WORKSHEET, DATA_COLS)
    if all_df.empty:
        return create_empty_data_df()

    temp = all_df[all_df["ID"].astype(str).str.strip() == teacher_id].copy()
    return normalize_df_columns(temp, DATA_COLS)


def load_user_config(user_name: str) -> pd.DataFrame:
    teacher_id = str(user_name).strip()
    all_df = read_sheet_df(CONFIG_WORKSHEET, CONFIG_COLS)
    if all_df.empty:
        return create_empty_config_df()

    temp = all_df[all_df["ID"].astype(str).str.strip() == teacher_id].copy()
    temp = normalize_df_columns(temp, CONFIG_COLS)

    # 사용자의 설정이 한 줄도 없으면 기본 골격 반환
    if temp.empty:
        temp = create_empty_config_df().copy()
        temp["ID"] = teacher_id
        return temp

    # 누락 교시/요일 보정
    base = create_empty_config_df().copy()
    base["ID"] = teacher_id

    merged = base.merge(
        temp,
        on=["ID", "요일", "교시"],
        how="left",
        suffixes=("_base", ""),
    )

    if "학급" not in merged.columns:
        merged["학급"] = ""
    merged["학급"] = merged["학급"].fillna("")

    return merged[CONFIG_COLS].copy().fillna("")


def save_user_config(user_name: str, config_df: pd.DataFrame) -> None:
    teacher_id = str(user_name).strip()
    all_df = read_sheet_df(CONFIG_WORKSHEET, CONFIG_COLS)

    if all_df.empty:
        all_df = create_empty_config_df()

    # 해당 사용자 기존 설정 제거 후 새 설정 반영
    remain = all_df[all_df["ID"].astype(str).str.strip() != teacher_id].copy()

    new_df = normalize_df_columns(config_df.copy(), CONFIG_COLS)
    new_df["ID"] = teacher_id

    updated = pd.concat([remain, new_df], ignore_index=True)
    updated = normalize_df_columns(updated, CONFIG_COLS)
    write_sheet_df(CONFIG_WORKSHEET, updated, CONFIG_COLS)


def append_rows_to_gsheet(user_name: str, new_df: pd.DataFrame) -> None:
    teacher_id = str(user_name).strip()
    all_df = read_sheet_df(DATA_WORKSHEET, DATA_COLS)

    if all_df.empty:
        all_df = create_empty_data_df()

    add_df = normalize_df_columns(new_df.copy(), DATA_COLS)
    add_df["ID"] = teacher_id

    updated = pd.concat([all_df, add_df], ignore_index=True)
    updated = normalize_df_columns(updated, DATA_COLS)
    write_sheet_df(DATA_WORKSHEET, updated, DATA_COLS)


def delete_rows_from_gsheet(user_name: str, day: str, row_name: str, lesson_date_str: str) -> None:
    teacher_id = str(user_name).strip()
    all_df = read_sheet_df(DATA_WORKSHEET, DATA_COLS)

    if all_df.empty:
        return

    mask = (
        (all_df["ID"].astype(str).str.strip() == teacher_id)
        & (all_df["수업날짜"].astype(str).str.strip() == lesson_date_str)
        & (all_df["요일"].astype(str).str.strip() == day)
        & (all_df["교시"].astype(str).str.strip() == row_name)
    )

    updated = all_df.loc[~mask].copy()
    updated = normalize_df_columns(updated, DATA_COLS)
    write_sheet_df(DATA_WORKSHEET, updated, DATA_COLS)


def prepare_log_df(df: pd.DataFrame) -> pd.DataFrame:
    temp = df.copy()
    if temp.empty:
        temp["수업날짜_dt"] = pd.Series(dtype="datetime64[ns]")
        temp["기록일시_dt"] = pd.Series(dtype="datetime64[ns]")
        temp["주차시작"] = pd.Series(dtype="object")
        return temp

    temp["수업날짜_dt"] = pd.to_datetime(temp["수업날짜"], errors="coerce")
    temp["기록일시_dt"] = pd.to_datetime(temp["기록일시"], errors="coerce")
    temp["주차시작"] = temp["수업날짜_dt"].dt.date.apply(
        lambda x: get_monday(x) if pd.notna(x) else pd.NaT
    )
    return temp


# -------------------------------------------------
# 시간표 설정 처리
# -------------------------------------------------
def build_class_map(config_df: pd.DataFrame) -> dict:
    class_map = {}
    if config_df.empty:
        return class_map

    for _, row in config_df.iterrows():
        day = str(row["요일"]).strip()
        period = str(row["교시"]).strip()
        class_name = str(row["학급"]).strip()
        if day in DAYS and period in PERIODS:
            class_map[(day, period)] = class_name
    return class_map


def has_any_timetable(config_df: pd.DataFrame) -> bool:
    if config_df.empty:
        return False
    return config_df["학급"].fillna("").astype(str).str.strip().ne("").any()


# -------------------------------------------------
# 데이터 가공
# -------------------------------------------------
def get_available_week_starts(df: pd.DataFrame, planning_year: int) -> list[date]:
    year_weeks = generate_year_week_starts(planning_year)
    data_weeks = []

    if not df.empty and "주차시작" in df.columns:
        for v in df["주차시작"].dropna().tolist():
            if isinstance(v, date):
                data_weeks.append(v)

    all_weeks = sorted(set(year_weeks + data_weeks), reverse=True)
    return all_weeks


def filter_df_by_week(df: pd.DataFrame, week_start: date) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    week_end = get_friday(week_start)
    mask = (
        df["수업날짜_dt"].notna()
        & (df["수업날짜_dt"].dt.date >= week_start)
        & (df["수업날짜_dt"].dt.date <= week_end)
    )
    return df.loc[mask].copy()


def get_all_records_df(all_df: pd.DataFrame) -> pd.DataFrame:
    if all_df.empty:
        return pd.DataFrame(columns=["수업날짜", "요일", "구분", "교시", "학급", "유형", "목표", "내용"])

    temp = all_df.sort_values(
        by=["수업날짜_dt", "기록일시_dt"],
        ascending=[False, False]
    ).copy()

    display_df = temp[["수업날짜", "요일", "구분", "교시", "반", "유형", "목표", "내용"]].rename(
        columns={"반": "학급"}
    )
    return display_df.reset_index(drop=True)


def build_goal_summary(week_df: pd.DataFrame) -> dict:
    summary = {day: "" for day in DAYS}
    if week_df.empty:
        return summary

    temp = week_df[week_df["목표"].fillna("").astype(str).str.strip() != ""].copy()
    if temp.empty:
        return summary

    temp = temp.sort_values(
        by=["수업날짜_dt", "기록일시_dt"],
        ascending=[False, False]
    )
    latest = temp.groupby("요일", as_index=False).first()

    for _, row in latest.iterrows():
        day = str(row["요일"]).strip()
        goal = str(row["목표"]).strip()
        if day in DAYS:
            summary[day] = goal
    return summary


def build_timetable_cells(week_df: pd.DataFrame, class_map: dict) -> dict:
    cells = {}
    for day in DAYS:
        for row_name in ROW_ORDER:
            default_class = class_map.get((day, row_name), "") if row_name in PERIODS else ""
            status = "class" if default_class else ("homeroom" if row_name == "종례" else "empty")
            cells[(day, row_name)] = {
                "status": status,
                "class_name": default_class,
                "content": "",
            }

    if week_df.empty:
        return cells

    temp = week_df.sort_values(
        by=["수업날짜_dt", "기록일시_dt"],
        ascending=[False, False]
    ).copy()

    latest = temp.groupby(["요일", "교시"], as_index=False).first()

    for _, row in latest.iterrows():
        day = str(row["요일"]).strip()
        row_name = str(row["교시"]).strip()
        content = str(row["내용"]).strip()
        entry_type = str(row["유형"]).strip()
        class_name = str(row["반"]).strip()

        if day not in DAYS or row_name not in ROW_ORDER:
            continue

        if row_name == "종례":
            cells[(day, row_name)] = {
                "status": "homeroom",
                "class_name": "",
                "content": content,
            }
            continue

        if entry_type == "수업":
            cells[(day, row_name)] = {
                "status": "class",
                "class_name": class_name,
                "content": content,
            }
        elif entry_type == "할일":
            cells[(day, row_name)] = {
                "status": "todo",
                "class_name": "",
                "content": content,
            }
        else:
            cells[(day, row_name)] = {
                "status": "class" if class_name else "todo",
                "class_name": class_name,
                "content": content,
            }

    return cells


# -------------------------------------------------
# 렌더링
# -------------------------------------------------
def render_goal_summary_html(goal_summary: dict) -> str:
    html = """
    <style>
    .goal-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        margin-bottom: 1.2rem;
        background: #FFFFFF;
    }
    .goal-table th, .goal-table td {
        border: 1px solid #D8E6F5;
        padding: 10px 12px;
        text-align: center;
        vertical-align: middle;
    }
    .goal-table th {
        background: #EEF6FF;
        color: #123A63;
        font-weight: 700;
    }
    .goal-title-cell {
        width: 120px;
        background: #123A63;
        color: #FFFFFF;
        font-weight: 700;
    }
    .goal-cell {
        background: #FFFFFF;
        color: #123A63;
        font-size: 0.95rem;
        line-height: 1.45;
        min-height: 52px;
    }
    </style>
    <table class="goal-table">
        <tr>
            <th class="goal-title-cell">주요 목표</th>
    """
    for day in DAYS:
        html += f"<th>{day}</th>"
    html += "</tr><tr><td class='goal-title-cell'>내용</td>"
    for day in DAYS:
        value = str(goal_summary.get(day, "")).strip()
        html += f"<td class='goal-cell'>{value}</td>"
    html += "</tr></table>"
    return html


def render_timetable_html(cells: dict) -> str:
    html = """
    <style>
    .planner-wrap {
        margin-top: 0.5rem;
        margin-bottom: 1.2rem;
    }
    .planner-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        border: 1px solid #D8E6F5;
        background: #FFFFFF;
    }
    .planner-table th, .planner-table td {
        border: 1px solid #D8E6F5;
        text-align: center;
        vertical-align: middle;
        padding: 0;
    }
    .planner-table thead th {
        background: #123A63;
        color: #FFFFFF;
        height: 54px;
        font-size: 1.02rem;
        font-weight: 700;
    }
    .planner-table .left-top {
        width: 90px;
        background: #123A63;
        color: #FFFFFF;
    }
    .planner-table .row-head {
        width: 90px;
        background: #EEF6FF;
        color: #123A63;
        font-size: 1.2rem;
        font-weight: 700;
        height: 92px;
    }
    .planner-table .row-head.homeroom {
        font-size: 1rem;
    }
    .planner-cell {
        height: 92px;
        padding: 8px 10px;
        line-height: 1.28;
        word-break: keep-all;
        white-space: normal;
    }
    .planner-cell.class-cell {
        background: #EEF6FF;
    }
    .planner-cell.todo-cell {
        background: #FFFFFF;
    }
    .planner-cell.homeroom-cell {
        background: #FFFFFF;
    }
    .planner-cell.empty-cell {
        background: #FAFCFF;
    }
    .class-name {
        color: #123A63;
        font-size: 1.1rem;
        font-weight: 700;
    }
    .class-content {
        margin-top: 4px;
        color: #123A63;
        font-size: 0.9rem;
    }
    .todo-content {
        color: #123A63;
        font-size: 0.9rem;
        font-weight: 500;
    }
    .todo-prefix {
        font-weight: 700;
    }
    .homeroom-content {
        color: #123A63;
        font-size: 0.9rem;
    }
    .placeholder-class {
        color: #123A63;
        font-size: 1.05rem;
        font-weight: 600;
    }
    </style>
    <div class="planner-wrap">
    <table class="planner-table">
        <thead>
            <tr>
                <th class="left-top"></th>
                <th>월</th>
                <th>화</th>
                <th>수</th>
                <th>목</th>
                <th>금</th>
            </tr>
        </thead>
        <tbody>
    """

    row_label_map = {
        "1교시": "1",
        "2교시": "2",
        "3교시": "3",
        "4교시": "4",
        "5교시": "5",
        "6교시": "6",
        "7교시": "7",
        "종례": "종례",
    }

    for row_name in ROW_ORDER:
        left_class = "row-head homeroom" if row_name == "종례" else "row-head"
        html += f"<tr><td class='{left_class}'>{row_label_map[row_name]}</td>"

        for day in DAYS:
            cell = cells[(day, row_name)]
            status = cell["status"]
            class_name = str(cell["class_name"]).strip()
            content = str(cell["content"]).strip()

            if status == "class":
                inner = f"<div class='class-name'>{class_name}</div>"
                if content:
                    inner += f"<div class='class-content'>{content}</div>"
                css_class = "planner-cell class-cell"
            elif status == "todo":
                inner = f"<div class='todo-content'><span class='todo-prefix'>할 일</span><br>{content}</div>" if content else ""
                css_class = "planner-cell todo-cell"
            elif status == "homeroom":
                inner = f"<div class='homeroom-content'>{content}</div>" if content else ""
                css_class = "planner-cell homeroom-cell"
            else:
                inner = f"<div class='placeholder-class'>{class_name}</div>" if class_name else ""
                css_class = "planner-cell empty-cell"

            html += f"<td class='{css_class}'>{inner}</td>"

        html += "</tr>"

    html += "</tbody></table></div>"
    return html


# -------------------------------------------------
# 개별 칸 초기화: Google Sheets 연동 삭제
# -------------------------------------------------
def delete_saved_cell(day: str, row_name: str, safe_user: str, teacher_name: str) -> None:
    date_key = make_date_key(day, safe_user)
    selected_lesson_date = to_date_safe(st.session_state.get(date_key, date.today()))
    lesson_date_str = selected_lesson_date.strftime("%Y-%m-%d")

    # Google Sheets에서 삭제
    delete_rows_from_gsheet(teacher_name, day, row_name, lesson_date_str)

    # 현재 입력창 즉시 비움
    st.session_state[make_input_key(day, row_name, safe_user)] = ""

    st.session_state["save_message"] = f"{day} {row_name} 기록이 초기화되었습니다."
    st.session_state["save_message_type"] = "success"
    st.rerun()


# -------------------------------------------------
# 저장 콜백
# -------------------------------------------------
def save_day_planner(day: str, teacher_name: str, class_map: dict, safe_user: str) -> None:
    selected_week_key = f"selected_week_start_{safe_user}"
    day_selector_key = f"day_selector_{safe_user}"

    date_key = make_date_key(day, safe_user)
    goal_key = make_goal_key(day, safe_user)

    selected_lesson_date = to_date_safe(st.session_state.get(date_key, date.today()))
    goal_text = str(st.session_state.get(goal_key, "")).strip()

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    lesson_date_str = selected_lesson_date.strftime("%Y-%m-%d")

    rows_to_add = []
    used_keys = [goal_key]

    for row_name in ROW_ORDER:
        input_key = make_input_key(day, row_name, safe_user)
        used_keys.append(input_key)
        content_text = str(st.session_state.get(input_key, "")).strip()

        if not content_text:
            continue

        if row_name == "종례":
            rows_to_add.append(
                {
                    "ID": teacher_name,
                    "수업날짜": lesson_date_str,
                    "기록일시": current_time,
                    "요일": day,
                    "구분": "종례",
                    "교시": "종례",
                    "반": "",
                    "유형": "종례",
                    "내용": content_text,
                    "목표": goal_text,
                }
            )
        else:
            class_name = class_map.get((day, row_name), "")
            entry_type = "수업" if class_name else "할일"

            rows_to_add.append(
                {
                    "ID": teacher_name,
                    "수업날짜": lesson_date_str,
                    "기록일시": current_time,
                    "요일": day,
                    "구분": "교시",
                    "교시": row_name,
                    "반": class_name,
                    "유형": entry_type,
                    "내용": content_text,
                    "목표": goal_text,
                }
            )

    if not rows_to_add and goal_text:
        rows_to_add.append(
            {
                "ID": teacher_name,
                "수업날짜": lesson_date_str,
                "기록일시": current_time,
                "요일": day,
                "구분": "목표",
                "교시": "목표",
                "반": "",
                "유형": "목표",
                "내용": "",
                "목표": goal_text,
            }
        )

    if not rows_to_add:
        st.session_state["save_message"] = f"{day}요일은 저장할 내용이 없습니다."
        st.session_state["save_message_type"] = "warning"
        st.session_state[day_selector_key] = day
        st.rerun()

    new_df = pd.DataFrame(rows_to_add, columns=DATA_COLS)
    append_rows_to_gsheet(teacher_name, new_df)

    st.session_state[selected_week_key] = get_monday(selected_lesson_date)
    st.session_state[day_selector_key] = day

    for key in used_keys:
        if key in st.session_state:
            del st.session_state[key]

    st.session_state["save_message"] = (
        f"{day}요일 내용 {len(rows_to_add)}건이 저장되었습니다. "
        f"(수업날짜: {lesson_date_str})"
    )
    st.session_state["save_message_type"] = "success"
    st.rerun()


# -------------------------------------------------
# 디자인
# -------------------------------------------------
st.markdown(
    """
    <style>
    :root {
        --bg-white: #FFFFFF;
        --navy: #123A63;
        --soft-blue: #EEF6FF;
    }

    .stApp {
        background: var(--bg-white);
    }

    .main-title {
        font-size: 2rem;
        font-weight: 800;
        color: var(--navy);
        margin-bottom: 0.2rem;
        text-align: center;
    }

    .sub-text {
        color: var(--navy);
        opacity: 0.8;
        margin-bottom: 1rem;
        text-align: center;
    }

    .section-card {
        background: var(--bg-white);
        border: 1px solid var(--soft-blue);
        border-radius: 16px;
        padding: 1rem 1rem 0.8rem 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 2px 8px rgba(18,58,99,0.04);
    }

    .table-header {
        color: var(--navy);
        font-weight: 700;
        padding-bottom: 0.35rem;
    }

    .free-label {
        color: var(--navy);
        opacity: 0.7;
        font-weight: 600;
    }

    .welcome-box {
        max-width: 720px;
        margin: 60px auto 0 auto;
        padding: 2rem 1.5rem;
        border: 1px solid #D8E6F5;
        border-radius: 18px;
        background: #FFFFFF;
        text-align: center;
        box-shadow: 0 2px 8px rgba(18,58,99,0.04);
    }

    .center-help {
        text-align: center;
        color: #123A63;
        font-weight: 700;
        margin-bottom: 0.6rem;
    }

    div[data-testid="stDateInput"] label,
    div[data-testid="stTextInput"] label,
    div[data-testid="stTextArea"] label,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stRadio"] label {
        color: var(--navy) !important;
        font-weight: 700 !important;
    }

    div[data-testid="stTextInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stTextArea"] textarea {
        border-radius: 10px !important;
        border: 1px solid var(--soft-blue) !important;
        background: #FFFFFF !important;
    }

    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stDateInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus {
        border: 1px solid var(--navy) !important;
        box-shadow: 0 0 0 1px var(--navy) !important;
    }

    .stButton > button {
        width: 100%;
        background: var(--navy) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        padding: 0.75rem 1rem !important;
    }

    .stButton > button:hover {
        background: var(--navy) !important;
        opacity: 0.92;
    }

    div[data-testid="stDataFrame"] {
        border: 1px solid var(--soft-blue);
        border-radius: 12px;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# 공통 세션 상태
# -------------------------------------------------
if "save_message" not in st.session_state:
    st.session_state["save_message"] = ""

if "save_message_type" not in st.session_state:
    st.session_state["save_message_type"] = "success"

if "confirmed_teacher_name" not in st.session_state:
    st.session_state["confirmed_teacher_name"] = ""

# -------------------------------------------------
# 초기 이름 입력 화면
# -------------------------------------------------
confirmed_name = st.session_state["confirmed_teacher_name"]

if not confirmed_name:
    st.markdown('<div class="main-title">📚 나만의 하이테크 진도표</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-text">환영합니다! 성함을 입력하고 나만의 진도표를 시작하세요.</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="welcome-box">
            <div class="center-help">성함을 입력하고 Enter를 눌러주세요</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1.2, 2.4, 1.2])
    with c2:
        typed_name = st.text_input(
            "성함 입력",
            placeholder="예: 김가혜",
            key="teacher_name_input_main",
            label_visibility="collapsed",
        )

    if typed_name and str(typed_name).strip():
        st.session_state["confirmed_teacher_name"] = str(typed_name).strip()
        st.rerun()

    st.stop()

teacher_name = st.session_state["confirmed_teacher_name"]
safe_user = sanitize_user_name(teacher_name)

# -------------------------------------------------
# 사용자별 세션 상태 초기화
# -------------------------------------------------
selected_week_key = f"selected_week_start_{safe_user}"
day_selector_key = f"day_selector_{safe_user}"
show_config_editor_key = f"show_config_editor_{safe_user}"

if selected_week_key not in st.session_state:
    st.session_state[selected_week_key] = get_monday(date.today())

if day_selector_key not in st.session_state:
    st.session_state[day_selector_key] = get_today_day_label()

if show_config_editor_key not in st.session_state:
    st.session_state[show_config_editor_key] = False

# -------------------------------------------------
# 데이터/설정 불러오기
# -------------------------------------------------
raw_df = load_user_data(teacher_name)
prepared_df = prepare_log_df(raw_df)
config_df = load_user_config(teacher_name)
class_map = build_class_map(config_df)
timetable_exists = has_any_timetable(config_df)

# -------------------------------------------------
# 제목
# -------------------------------------------------
st.markdown('<div class="main-title">📚 나만의 하이테크 진도표</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="sub-text"><b>{teacher_name}</b> 선생님의 개인 공간입니다. 시간표와 진도, 공강 할 일을 독립적으로 관리할 수 있습니다.</div>',
    unsafe_allow_html=True,
)

if st.session_state["save_message"]:
    if st.session_state["save_message_type"] == "success":
        st.success(st.session_state["save_message"])
    else:
        st.warning(st.session_state["save_message"])
    st.session_state["save_message"] = ""
    st.session_state["save_message_type"] = "success"

# -------------------------------------------------
# 상단 사용자 제어
# -------------------------------------------------
top_a, top_b = st.columns([6, 1.4])
with top_b:
    if st.button("사용자 변경", key=f"change_user_{safe_user}"):
        st.session_state["confirmed_teacher_name"] = ""
        st.rerun()

tool_a, tool_b = st.columns([5, 1.5])
with tool_b:
    if st.button("시간표 설정하기 / 수정", use_container_width=True, key=f"config_toggle_{safe_user}"):
        st.session_state[show_config_editor_key] = not st.session_state[show_config_editor_key]

# -------------------------------------------------
# 시간표 설정창
# -------------------------------------------------
if not timetable_exists:
    st.info("시간표가 없습니다. 먼저 시간표를 설정해주세요.")
    if st.button("시간표 설정하기", key=f"setup_btn_main_{safe_user}"):
        st.session_state[show_config_editor_key] = True

if st.session_state[show_config_editor_key]:
    st.markdown("## 시간표 설정")
    st.markdown('<div class="section-card">', unsafe_allow_html=True)

    header_cols = st.columns([0.9] + [1.3] * len(DAYS))
    header_cols[0].markdown('<div class="table-header">교시</div>', unsafe_allow_html=True)
    for i, day in enumerate(DAYS, start=1):
        header_cols[i].markdown(f'<div class="table-header">{day}</div>', unsafe_allow_html=True)

    st.markdown("---")

    for period in PERIODS:
        row_cols = st.columns([0.9] + [1.3] * len(DAYS))
        row_cols[0].write(period.replace("교시", ""))

        for i, day in enumerate(DAYS, start=1):
            existing_value = ""
            matched = config_df[(config_df["요일"] == day) & (config_df["교시"] == period)]
            if not matched.empty:
                existing_value = str(matched.iloc[0]["학급"]).strip()

            key = make_config_key(day, period, safe_user)
            if key not in st.session_state:
                st.session_state[key] = existing_value

            row_cols[i].text_input(
                label=f"{day}_{period}",
                key=key,
                label_visibility="collapsed",
                placeholder="예: 2-10",
            )

    if st.button("시간표 저장하기", key=f"save_config_{safe_user}"):
        rows = []
        for day in DAYS:
            for period in PERIODS:
                rows.append(
                    {
                        "ID": teacher_name,
                        "요일": day,
                        "교시": period,
                        "학급": str(st.session_state.get(make_config_key(day, period, safe_user), "")).strip(),
                    }
                )

        new_config_df = pd.DataFrame(rows, columns=CONFIG_COLS)
        save_user_config(teacher_name, new_config_df)
        st.session_state["save_message"] = "시간표가 저장되었습니다."
        st.session_state["save_message_type"] = "success"
        st.session_state[show_config_editor_key] = False
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# 다시 로드
config_df = load_user_config(teacher_name)
class_map = build_class_map(config_df)
timetable_exists = has_any_timetable(config_df)

if not timetable_exists:
    st.stop()

# -------------------------------------------------
# 상단: 주차 선택 (2026년 전체)
# -------------------------------------------------
available_week_starts = get_available_week_starts(prepared_df, PLANNING_YEAR)
if st.session_state[selected_week_key] not in available_week_starts:
    available_week_starts = [st.session_state[selected_week_key]] + available_week_starts
    available_week_starts = sorted(set(available_week_starts), reverse=True)

week_label_map = {wk: format_week_label(wk) for wk in available_week_starts}

st.markdown("### 조회 주차 선택")
selected_week_start = st.selectbox(
    "조회할 주차를 선택하세요",
    options=available_week_starts,
    index=available_week_starts.index(st.session_state[selected_week_key]),
    format_func=lambda x: week_label_map[x],
    key=f"week_select_{safe_user}",
)

st.session_state[selected_week_key] = selected_week_start
selected_week_df = filter_df_by_week(prepared_df, selected_week_start)

# -------------------------------------------------
# 요일 선택
# -------------------------------------------------
st.markdown("### 요일 선택")
selected_day = st.radio(
    "요일 선택",
    options=DAYS,
    horizontal=True,
    index=DAYS.index(st.session_state[day_selector_key]),
    key=f"day_radio_{safe_user}",
    label_visibility="collapsed",
)
st.session_state[day_selector_key] = selected_day

# -------------------------------------------------
# 입력 화면
# -------------------------------------------------
st.markdown(f"## {selected_day}요일 입력")
st.markdown('<div class="section-card">', unsafe_allow_html=True)

date_key = make_date_key(selected_day, safe_user)
goal_key = make_goal_key(selected_day, safe_user)

if date_key not in st.session_state:
    weekday_idx = DAYS.index(selected_day)
    st.session_state[date_key] = selected_week_start + timedelta(days=weekday_idx)

if goal_key not in st.session_state:
    st.session_state[goal_key] = ""

top1, top2 = st.columns([1.2, 2.8])
with top1:
    st.date_input(
        "수업 날짜 선택",
        key=date_key,
        value=st.session_state[date_key],
    )
with top2:
    st.text_input(
        "오늘의 주요 목표",
        key=goal_key,
        placeholder="예: 개념 이해 완료, 채점 마무리, 학부모 연락 정리",
    )

st.markdown("")

header_cols = st.columns([0.9, 1.4, 4.2, 0.9])
header_cols[0].markdown('<div class="table-header">교시</div>', unsafe_allow_html=True)
header_cols[1].markdown('<div class="table-header">학급/구분</div>', unsafe_allow_html=True)
header_cols[2].markdown('<div class="table-header">진도 또는 할 일</div>', unsafe_allow_html=True)
header_cols[3].markdown('<div class="table-header">초기화</div>', unsafe_allow_html=True)
st.markdown("---")

for period in PERIODS:
    class_name = class_map.get((selected_day, period), "")
    input_key = make_input_key(selected_day, period, safe_user)

    if input_key not in st.session_state:
        st.session_state[input_key] = ""

    cols = st.columns([0.9, 1.4, 4.2, 0.9])
    cols[0].write(period.replace("교시", ""))

    if class_name:
        cols[1].write(class_name)
        placeholder = "예: 프랑스 혁명 서론"
    else:
        cols[1].markdown('<span class="free-label">공강</span>', unsafe_allow_html=True)
        placeholder = "예: 생활기록부 정리, 평가 채점, 학부모 연락"

    cols[2].text_input(
        label=f"{selected_day} {period}",
        key=input_key,
        label_visibility="collapsed",
        placeholder=placeholder,
    )

    cols[3].button(
        "초기화",
        key=f"clear_{safe_user}_{selected_day}_{period}",
        on_click=delete_saved_cell,
        args=(selected_day, period, safe_user, teacher_name),
    )

homeroom_key = make_input_key(selected_day, "종례", safe_user)
if homeroom_key not in st.session_state:
    st.session_state[homeroom_key] = ""

st.markdown("#### 종례 사항")
home_cols = st.columns([6, 1])
home_cols[0].text_area(
    "종례 사항",
    key=homeroom_key,
    label_visibility="collapsed",
    height=110,
    placeholder="예: 숙제 안내, 준비물 공지, 생활지도, 전달사항",
)
home_cols[1].button(
    "초기화",
    key=f"clear_{safe_user}_{selected_day}_종례",
    on_click=delete_saved_cell,
    args=(selected_day, "종례", safe_user, teacher_name),
)

st.button(
    f"{selected_day}요일 저장하기",
    key=f"save_button_{safe_user}_{selected_day}",
    on_click=save_day_planner,
    args=(selected_day, teacher_name, class_map, safe_user),
)

st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------
# 주간 대시보드
# -------------------------------------------------
st.markdown("---")
st.markdown("## 주간 시간표 플래너")
st.caption(f"현재 조회 주차: {format_week_label(selected_week_start)}")

goal_summary = build_goal_summary(selected_week_df)
st.markdown(render_goal_summary_html(goal_summary), unsafe_allow_html=True)

cells = build_timetable_cells(selected_week_df, class_map)
st.markdown(render_timetable_html(cells), unsafe_allow_html=True)

# -------------------------------------------------
# 전체 기록
# -------------------------------------------------
st.markdown("---")
st.markdown("## 전체 기록")

all_records_df = get_all_records_df(prepared_df)

if all_records_df.empty:
    st.info("저장된 기록이 없습니다.")
else:
    st.dataframe(
        all_records_df,
        use_container_width=True,
        hide_index=True,
    )

# -------------------------------------------------
# CSV 다운로드
# -------------------------------------------------
csv_data = raw_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    label="내 데이터 CSV 다운로드",
    data=csv_data,
    file_name=f"data_{safe_user}.csv",
    mime="text/csv",
    use_container_width=True,
)

st.caption(f"Google Sheets 데이터 워크시트: {DATA_WORKSHEET}")
st.caption(f"Google Sheets 시간표 워크시트: {CONFIG_WORKSHEET}")
