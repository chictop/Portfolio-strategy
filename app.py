import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from pandas_datareader import data as pdr

# ---------------------------
# 설정
# ---------------------------
TICKER_DESC = {
    "IVV": "S&P 500 (초저비용)", "VEA": "선진국 주식 (초저비용)", "VWO": "신흥국 주식 (초저비용)",
    "BND": "미국 종합채권", "USIG": "투자등급 회사채", "VGIT": "중기 국채",
    "VGSH": "단기 국채", "VTV": "대형 가치주", "IAUM": "금 (초저비용)",
    "QQQM": "나스닥 100 (초저비용)", "SGOV": "초단기 국채(현금)"
}
HISTORY_FILE = "rebalancing_history.csv"

# ---------------------------
# 유틸리티
# ---------------------------
def st_divider():
    if hasattr(st, "divider"):
        st.divider()
    else:
        st.markdown("---")

def safe_series(prices, ticker):
    """티커 존재 및 NaN 제거 후 Series 반환. 없으면 빈 Series."""
    if prices is None or prices.empty:
        return pd.Series(dtype=float)
    if ticker not in prices.columns:
        return pd.Series(dtype=float)
    return prices[ticker].dropna()

def enough_length(series, required):
    return len(series) > required

def calc_shares(budget_krw, price_usd, ex_rate):
    """안전한 주수 계산. price_usd 유효성 검사."""
    try:
        if price_usd is None or np.isnan(price_usd) or price_usd <= 0:
            return 0, 0.0
        shares = int((budget_krw / ex_rate) // price_usd)
        return shares, shares * price_usd * ex_rate
    except Exception:
        return 0, 0.0

def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            return pd.read_csv(HISTORY_FILE).to_dict('records')
    except Exception:
        return []
    return []

def save_history(history_list):
    try:
        pd.DataFrame(history_list).to_csv(HISTORY_FILE, index=False, encoding='utf-8-sig')
        return True
    except Exception:
        return False

# ---------------------------
# 데이터 호출 (안전 처리)
# ---------------------------
@st.cache_data(ttl=3600)
def get_live_exchange_rate():
    try:
        ex_data = yf.download("KRW=X", period="1d", interval="1m", progress=False)
        if ex_data is None or ex_data.empty:
            return 1350.0
        return float(ex_data['Close'].iloc[-1])
    except Exception:
        return 1350.0

@st.cache_data(ttl=3600)
def download_prices(tickers, days_back=500):
    try:
        start = datetime.now() - timedelta(days=days_back)
        df = yf.download(tickers, start=start, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return pd.DataFrame()
        if 'Close' in df.columns:
            return df['Close']
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=86400)
def get_unrate_data():
    try:
        df = pdr.get_data_fred('UNRATE', start='2023-01-01').dropna()
        if df.empty:
            return pd.DataFrame(), 0.0, 0.0
        df.columns = ['UNRATE']
        df['MA12'] = df['UNRATE'].rolling(window=12, min_periods=1).mean()
        df = df.round(2)
        display_df = df.tail(12).copy()
        display_df.index = display_df.index.strftime('%Y-%m')
        return display_df, float(df['UNRATE'].iloc[-1]), float(df['MA12'].iloc[-1])
    except Exception:
        return pd.DataFrame(), 0.0, 0.0

# ---------------------------
# 전략 보조 함수
# ---------------------------
def get_vaa_score(prices, ticker):
    s = safe_series(prices, ticker)
    if not enough_length(s, 252):
        return np.nan
    try:
        return (12*((s.iloc[-1]/s.iloc[-22])-1)) + (4*((s.iloc[-1]/s.iloc[-66])-1)) + (2*((s.iloc[-1]/s.iloc[-132])-1)) + (1*((s.iloc[-1]/s.iloc[-252])-1))
    except Exception:
        return np.nan

def ret12(prices, ticker):
    s = safe_series(prices, ticker)
    if not enough_length(s, 252):
        return np.nan
    try:
        return (s.iloc[-1] / s.iloc[-252]) - 1
    except Exception:
        return np.nan

# ---------------------------
# 앱 UI 및 로직
# ---------------------------
st.set_page_config(page_title="퀀트 투자 전술 대시보드", layout="wide")
st.title("🏛️ 자산배분 전략 및 전술적 스위칭 시스템")

# 세션 히스토리 로드
if 'history' not in st.session_state:
    st.session_state['history'] = load_history()

# 데이터 로드
current_ex = get_live_exchange_rate()
prices = download_prices(list(TICKER_DESC.keys()))
unrate_history, curr_unrate, ma12_unrate = get_unrate_data()

# 사이드바
st.sidebar.header("⚙️ 투자 설정")
total_assets = st.sidebar.number_input("총 투자 자산 (원)", min_value=0, value=30000000, step=1000000)
exchange_rate = st.sidebar.number_input("현재 환율 (원/$)", value=current_ex, step=0.1)
budget_per_strat = total_assets / 3

# 데이터 유효성 알림
if prices is None or prices.empty:
    st.warning("가격 데이터를 불러오지 못했습니다. 네트워크 문제 또는 yfinance 응답 실패일 수 있습니다.")
else:
    st.success("가격 데이터를 불러왔습니다.")

if unrate_history.empty:
    st.warning("실업률 데이터를 불러오지 못했습니다. FRED 접근 실패일 수 있습니다.")

# IVV(=S&P) 기준 지표 (안전 체크)
ivv = safe_series(prices, 'IVV')
if ivv.empty:
    st.warning("IVV 가격 데이터가 부족하여 일부 지표를 계산할 수 없습니다.")
    ath = curr_p = mdd = ma50 = np.nan
else:
    ath = ivv.cummax().iloc[-1]
    curr_p = ivv.iloc[-1]
    mdd = (curr_p / ath - 1) * 100
    ma50 = ivv.rolling(window=50).mean().iloc[-1]

st.markdown("### 🚨 전술적 알림 센터 (Tactical Alert Center)")
with st.container():
    col_sw, col_rv = st.columns(2)
    with col_sw:
        st.markdown("**📉 우량주 스위칭 단계 (공격 신호)**")
        if np.isnan(mdd):
            st.info("MDD를 계산할 수 없습니다 (데이터 부족).")
        else:
            if mdd > -15:
                st.info(f"**상태: 노이즈 구간 (MDD {mdd:.2f}%)**\n하락폭이 작습니다. 3분할 전략 유지 권장.")
            else:
                if -20 < mdd <= -15:
                    ratio, level = "20%", "1단계"
                elif -25 < mdd <= -20:
                    ratio, level = "40%", "2단계"
                elif -30 < mdd <= -25:
                    ratio, level = "60%", "3단계"
                elif -35 < mdd <= -30:
                    ratio, level = "80%", "4단계"
                else:
                    ratio, level = "100%", "최종단계"
                st.warning(f"**상태: {level} 스위칭 (MDD {mdd:.2f}%)**\n방어 자산의 **{ratio}**를 개별 우량주로 전환 권장.")

    with col_rv:
        st.markdown("**🔄 포트폴리오 복귀 신호 (탈출 신호)**")
        if np.isnan(curr_p) or np.isnan(ma50):
            st.info("50일선 또는 현재가를 계산할 수 없습니다.")
        else:
            if curr_p < ma50:
                st.error(f"**상태: 추세 붕괴 (50일선 하회)**\n주가가 50일선(${ma50:.2f}) 아래입니다. 3분할 전략으로 복귀 권장.")
            elif curr_p >= ath * 0.97:
                st.success("**상태: 수익 극대화 구간**\n전고점 근처입니다. 트레일링 스탑 고려.")
            else:
                st.write(f"현재 주가(${curr_p:.2f})가 50일선(${ma50:.2f}) 위에 있어 추세가 살아있습니다.")

st_divider()

# ---------------------------
# 전략 계산
# ---------------------------
# VAA
vaa_atk = ['IVV', 'VEA', 'VWO', 'BND']
vaa_dfn = ['USIG', 'VGIT', 'VGSH']
vaa_scores = {}
for t in vaa_atk + vaa_dfn:
    sc = get_vaa_score(prices, t)
    vaa_scores[t] = np.nan if sc is None else sc

# VAA 위기 판단 (공격군 중 하나라도 음수면 위기)
vaa_is_crisis = any((not np.isnan(vaa_scores.get(t, np.nan))) and vaa_scores[t] <= 0 for t in vaa_atk)
# 유효한 후보만 고려
if vaa_is_crisis:
    candidates = [t for t in vaa_dfn if not np.isnan(vaa_scores.get(t, np.nan))]
else:
    candidates = [t for t in vaa_atk if not np.isnan(vaa_scores.get(t, np.nan))]

vaa_pick = max(candidates, key=lambda x: vaa_scores[x]) if candidates else None
if vaa_pick:
    price_vaa = safe_series(prices, vaa_pick).iloc[-1] if not safe_series(prices, vaa_pick).empty else np.nan
    vaa_s, vaa_c = calc_shares(budget_per_strat, price_vaa, exchange_rate)
else:
    vaa_s, vaa_c = 0, 0.0

# LAA: 먼저 LAA 상세(표와 합계)를 계산하여 summary에 반영
spy_200ma = ivv.rolling(window=200).mean().iloc[-1] if not ivv.empty and enough_length(ivv, 200) else np.nan
laa_dynamic = 'VGSH' if (curr_unrate > ma12_unrate and (not np.isnan(curr_p) and curr_p < spy_200ma)) else 'QQQM'
laa_tickers = ['VTV', 'VGIT', 'IAUM', laa_dynamic]

# LAA 상세 계산 (합계 포함)
laa_res = []
laa_sum = 0.0
for t in laa_tickers:
    price_t = safe_series(prices, t).iloc[-1] if not safe_series(prices, t).empty else np.nan
    sh, cs = calc_shares(budget_per_strat * 0.25, price_t, exchange_rate)
    laa_res.append({"종목": t, "수량": f"{sh}주", "금액": cs, "금액표시": f"{cs:,.0f}원"})
    laa_sum += cs
# laa_sum now represents the actual KRW used by LAA allocations

# DM
ivv_ret = ret12(prices, 'IVV')
vea_ret = ret12(prices, 'VEA')
sgov_ret = ret12(prices, 'SGOV')
if np.isnan(ivv_ret) and np.isnan(vea_ret):
    dm_pick = 'BND'
else:
    better = 'IVV' if (not np.isnan(ivv_ret) and (np.isnan(vea_ret) or ivv_ret > vea_ret)) else 'VEA'
    better_ret = ivv_ret if better == 'IVV' else vea_ret
    dm_pick = better if (not np.isnan(better_ret) and better_ret > sgov_ret) else 'BND'

price_dm = safe_series(prices, dm_pick).iloc[-1] if not safe_series(prices, dm_pick).empty else np.nan
dm_s, dm_c = calc_shares(budget_per_strat, price_dm, exchange_rate)

# ---------------------------
# 요약 출력 (LAA 투자금액은 laa_sum으로 반영)
# ---------------------------
st.subheader("📊 전략별 리밸런싱 결과 요약")
summary_df = pd.DataFrame([
    {"전략": "VAA (🛡️)", "상태": "방어" if vaa_is_crisis else "공격", "추천": vaa_pick or "N/A", "수량": f"{vaa_s}주", "투자금액": vaa_c},
    {"전략": "LAA (🐢)", "상태": "불황" if laa_dynamic == 'VGSH' else "정상", "추천": f"고정3+{laa_dynamic}", "수량": "하단참조", "투자금액": laa_sum},
    {"전략": "듀얼모멘텀 (🚀)", "상태": "채권" if dm_pick == 'BND' else "주식", "추천": dm_pick or "N/A", "수량": f"{dm_s}주", "투자금액": dm_c}
])

# 투자금액 포맷팅 및 합계 행 추가
summary_df_display = summary_df.copy()
summary_df_display["투자금액"] = summary_df_display["투자금액"].apply(lambda x: f"{x:,.0f}원")
total_invest = summary_df["투자금액"].sum()
# 합계 행
summary_df_display = pd.concat([summary_df_display, pd.DataFrame([{"전략": "📌 합계", "상태": "", "추천": "", "수량": "", "투자금액": f"{total_invest:,.0f}원"}])], ignore_index=True)

st.table(summary_df_display)

if st.button("📥 현재 결과 히스토리에 기록"):
    log = {"날짜": datetime.now().strftime("%Y-%m-%d %H:%M"), "VAA": vaa_pick or "", "LAA": laa_dynamic, "DM": dm_pick or "", "MDD": f"{mdd:.2f}%" if not np.isnan(mdd) else ""}
    st.session_state['history'].append(log)
    ok = save_history(st.session_state['history'])
    if ok:
        st.success("히스토리가 파일에 저장되었습니다.")
    else:
        st.error("히스토리 저장에 실패했습니다. 파일 권한을 확인하세요.")

st_divider()

# ---------------------------
# 전략별 상세 브리핑을 표로 (요청 반영: '시장 상황' 컬럼으로 변경)
# ---------------------------
st.subheader("📝 전략별 상세 브리핑 (요약 표)")
brief_rows = []

# VAA row
vaa_judge = "공격군 중 일부 모멘텀이 음수이면 방어 전환" if vaa_is_crisis else "공격 모멘텀 우세"
vaa_impact = "방어 모드: 주식 노출 축소 → 채권/현금 확대; 공격 모드: 모멘텀 우수 자산 집중"
vaa_market = "시장 상황: 변동성 확대 시 방어 자산 선호; 모멘텀 회복 시 공격 자산 재가동"
brief_rows.append({
    "전략": "VAA (🛡️)",
    "판단 근거": vaa_judge,
    "영향": vaa_impact,
    "시장 상황": vaa_market
})

# LAA row
laa_judge = "실업률 상승(현재 > 12M 평균) AND S&P(IVV) 200일선 하회 → 방어"
laa_impact = "동시 악화 시 변동성 완화 목적의 초단기 국채 전환; 정상 시 분산 유지"
laa_market = "시장 상황: 경기 약화 신호(실업률 상승)와 가격 약세 동시 발생 시 방어적 포지셔닝 권장"
brief_rows.append({
    "전략": "LAA (🐢)",
    "판단 근거": laa_judge,
    "영향": laa_impact,
    "시장 상황": laa_market
})

# DM row
dm_judge = "12개월 상대수익률(IVV vs VEA) 비교 후 현금(SGOV) 대비 우위 판단"
dm_impact = "주식 우위 시 주식 노출 유지; 우위 없으면 채권(BND)으로 방어"
dm_market = "시장 상황: 글로벌 주식 상대수익률이 현저히 낮아지면 안전자산 선호; 주식 우위 시 리스크 온"
brief_rows.append({
    "전략": "듀얼모멘텀 (🚀)",
    "판단 근거": dm_judge,
    "영향": dm_impact,
    "시장 상황": dm_market
})

brief_df = pd.DataFrame(brief_rows)
# 한 줄 셀 규칙: 각 셀 한 줄로 유지하기 위해 줄바꿈 제거
brief_df = brief_df.replace({r"\n": " "}, regex=True)
st.table(brief_df)

st_divider()

# ---------------------------
# LAA 상세 (오직 왼쪽에만 표시; 옆의 상세 브리핑은 삭제됨)
# ---------------------------
st.subheader("LAA 상세 및 실업률")
st.write(f"**LAA 전략 상세 (총액: {laa_sum:,.0f}원 — 실제 할당 합계)**")
laa_display = []
for r in laa_res:
    laa_display.append({"종목": r["종목"], "수량": r["수량"], "금액(원)": r["금액표시"]})
laa_display.append({"종목": "📂 합계", "수량": "-", "금액(원)": f"{laa_sum:,.0f}원"})
st.table(pd.DataFrame(laa_display))

if not np.isnan(curr_unrate):
    st.info(f"📊 **실업률**: 현재 **{curr_unrate:.2f}%** (12개월 평균: **{ma12_unrate:.2f}%**)")
else:
    st.info("실업률 데이터 없음")

st_divider()

# ---------------------------
# 하단 탭: 히스토리, 주요 지표 차트(실업률 포함), 종목 정보
# ---------------------------
t1, t2, t3 = st.tabs(["📜 리밸런싱 히스토리", "📉 주요 지표 차트", "ℹ️ 종목 정보"])
with t1:
    if st.session_state['history']:
        st.table(pd.DataFrame(st.session_state['history']))
    else:
        st.info("저장된 히스토리가 없습니다.")

with t2:
    # 실업률 및 12개월 평균 그래프 (월별) — IVV 차트 제거 요청 반영
    st.subheader("실업률 (월별) 및 12개월 평균")
    if not unrate_history.empty:
        plot_df = unrate_history.copy()
        plot_df.index.name = "Month"
        display_unrate = plot_df.rename(columns={'UNRATE': '실업률(%)', 'MA12': '12개월 평균(%)'})
        st.table(display_unrate)
        st.line_chart(plot_df)
        st.caption("월별 실업률과 12개월 이동평균을 함께 표시합니다.")
    else:
        st.info("실업률 데이터가 없어 차트를 표시할 수 없습니다.")

with t3:
    rows = []
    for k, v in TICKER_DESC.items():
        s = safe_series(prices, k)
        price_str = f"${s.iloc[-1]:.2f}" if not s.empty else "N/A"
        rows.append({"티커": k, "현재가": price_str, "설명": v})
    st.table(pd.DataFrame(rows))

st_divider()
st.markdown("**주의사항**: 이 도구는 교육용이며 투자 권유가 아닙니다. 데이터 부족, 네트워크 오류, yfinance/FRED 응답 실패 등으로 결과가 달라질 수 있습니다.")
