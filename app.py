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

# 한국 상장 ETF 대체 종목 (추천)
KR_ETF_DESC = {
    "IVV": "TIGER 미국S&P500 / ACE 미국S&P500",
    "VEA": "KODEX 선진국MSCI World (*미국포함)",
    "VWO": "ARIRANG 신흥국MSCI(합성 H)",
    "BND": "TIGER 미국종합채권액티브(H)",
    "USIG": "ACE 미국회사채액티브",
    "VGIT": "TIGER 미국채10년선물 / ACE 미국30년국채액티브(H)",
    "VGSH": "KODEX 미국달러단기채권액티브",
    "VTV": "TIGER 미국배당다우존스 (*가치/배당 대체)",
    "IAUM": "ACE KRX금현물 / TIGER 골드선물(H)",
    "QQQM": "TIGER 미국나스닥100 / ACE 미국나스닥100",
    "SGOV": "TIGER 미국달러SOFR금리액티브(합성)"
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

# 모바일 폰트(Pretendard) 및 모든 표를 100% 동일하게 만들기 위한 공통 CSS
st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

/* 기본 텍스트 요소에만 폰트를 적용하여 사이드바 아이콘 등이 깨지는 현상(글씨로 나타남) 방지 */
html, body, p, h1, h2, h3, h4, h5, h6, li, table, th, td, div[class*="stMarkdown"], div[class*="stText"] {
    font-family: 'Pretendard', 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif !important;
    color: #333333;
}

/* 🚀 사이드바 화살표 등 Streamlit 기본 아이콘 폰트 강제 복구 */
.material-symbols-rounded, .material-icons, span[class*="stIcon"], i {
    font-family: 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
}

/* 제목 크기가 너무 크지 않도록 최적화 */
h1 { font-size: 1.5rem !important; padding-bottom: 0.5rem !important; }
h2 { font-size: 1.3rem !important; padding-bottom: 0.4rem !important; }
h3 { font-size: 1.15rem !important; padding-bottom: 0.3rem !important; }
h4 { font-size: 1.05rem !important; padding-bottom: 0.2rem !important; }

/* 파란색 링크 텍스트 녹색으로 변경 */
a { color: #21c354 !important; }

/* 모든 표에 적용할 공통 디자인(모양 100% 통일) */
.unified-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
    font-size: 14px !important;
    border: 2px solid rgba(128, 128, 128, 0.6) !important;
}
.unified-table th, .unified-table td {
    border: 1px solid rgba(128, 128, 128, 0.3) !important;
    padding: 10px !important;
    text-align: center !important;
    vertical-align: middle !important;
}
.unified-table thead th, .unified-table th {
    background-color: rgba(128, 128, 128, 0.15) !important;
    color: #000000 !important;
    font-weight: bold !important;
}

/* 데이터 무결성 텍스트 폰트 통일용 클래스 */
.unified-text {
    font-size: 14px !important;
}

/* 스마트폰 등 좁은 화면 최적화 (글씨 크기 및 패딩 축소) */
@media (max-width: 768px) {
    .unified-table {
        font-size: 12px !important;
    }
    .unified-table th, .unified-table td {
        padding: 6px 3px !important;
    }
    .unified-text {
        font-size: 12px !important;
    }
}
</style>
""", unsafe_allow_html=True)

st.title("🏛️ 자산배분 전략 및 전술적 스위칭 시스템")
st.markdown("<br>", unsafe_allow_html=True) # 타이틀 하단에 한 줄 띄우기

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

# ---------------------------
# 데이터 유효성 알림
# ---------------------------
is_all_success = True
loaded_tickers = []

if prices is None or prices.empty:
    st.warning("🚨 가격 데이터를 불러오지 못했습니다. 네트워크 문제 또는 yfinance 응답 실패일 수 있습니다.")
    is_all_success = False
else:
    loaded_tickers = prices.columns.tolist() if isinstance(prices, pd.DataFrame) else [prices.name]
    missing_tickers = [t for t in TICKER_DESC.keys() if t not in loaded_tickers]
    
    if missing_tickers:
        st.warning(f"⚠️ 일부 가격 데이터를 불러오지 못했습니다. 누락된 종목: {', '.join(missing_tickers)}")
        is_all_success = False

if unrate_history.empty:
    st.warning("🚨 실업률 데이터를 불러오지 못했습니다. FRED 접근 실패일 수 있습니다.")
    is_all_success = False

if is_all_success:
    # 섹터 간 간격을 원래대로 줄여서 <br> 사용
    st.markdown(
        f"<div class='unified-text' style='color: #21c354; font-weight: 500; margin-bottom: 10px;'>"
        f"✅ <strong>필수 데이터가 모두 정상적으로 로드되었습니다.</strong><br>"
        f"- 📈 <strong>수집된 티커 목록 ({len(loaded_tickers)}개)</strong>: {', '.join(loaded_tickers)}<br>"
        f"- 📊 <strong>실업률 데이터</strong>: 정상 로드됨 (현재 {curr_unrate:.2f}%, 12MA {ma12_unrate:.2f}%)"
        f"</div>",
        unsafe_allow_html=True
    )

st_divider()

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

# ---------------------------
# 전술적 알림 센터 (공통 CSS .unified-table 적용)
# ---------------------------
st.markdown("### 🚨 전술적 알림 센터")

# 지침 메시지 로직 (단순 명료하게 "우량주 스위칭 적용" 또는 "포트폴리오 적용"으로 변경)
if np.isnan(mdd) or np.isnan(curr_p) or np.isnan(ma50):
    guide_msg = "데이터 부족"
else:
    if mdd <= -15:
        guide_msg = "<span style='color: #FF4B4B; font-weight: bold;'>우량주 스위칭 적용</span>"
    else:
        guide_msg = "<span style='color: #FF4B4B; font-weight: bold;'>포트폴리오 적용</span>"

# 스위칭 단계 판단 로직
if np.isnan(mdd):
    sw_status, sw_details, sw_desc = "데이터 부족", "-", "MDD를 계산할 수 없습니다."
else:
    sw_details = f"현재 MDD: {mdd:.2f}%"
    if mdd > -15:
        sw_status = "노이즈 구간"
        sw_desc = "하락폭이 작습니다. 3분할 전략 유지를 권장합니다."
    else:
        if -20 < mdd <= -15: ratio, level = "20%", "1단계"
        elif -25 < mdd <= -20: ratio, level = "40%", "2단계"
        elif -30 < mdd <= -25: ratio, level = "60%", "3단계"
        elif -35 < mdd <= -30: ratio, level = "80%", "4단계"
        else: ratio, level = "100%", "최종단계"
        sw_status = f"{level} 스위칭"
        sw_desc = f"방어 자산의 {ratio}를 개별 우량주로 전환할 것을 권장합니다."

# 복귀 신호 판단 로직
if np.isnan(curr_p) or np.isnan(ma50):
    rv_status, rv_details, rv_desc = "데이터 부족", "-", "50일선 또는 현재가를 계산할 수 없습니다."
else:
    if curr_p < ma50:
        rv_status = "추세 붕괴 (50일선 하회)"
        rv_details = f"현재가: ${curr_p:.2f} / 50일선: ${ma50:.2f}"
        rv_desc = "3분할 자산배분 전략으로 복귀를 권장합니다."
    elif curr_p >= ath * 0.97:
        rv_status = "수익 극대화 구간"
        rv_details = f"현재가: ${curr_p:.2f} / 전고점: ${ath:.2f}"
        rv_desc = "전고점 근처입니다. 트레일링 스탑을 고려해 보세요."
    else:
        rv_status = "정상 추세 유지"
        rv_details = f"현재가: ${curr_p:.2f} / 50일선: ${ma50:.2f}"
        rv_desc = "주가가 50일선 위에 있어 추세가 살아있습니다."

tactical_html = f"""
<table class="unified-table">
    <thead>
        <tr>
            <th colspan="2">📌 핵심 행동 지침</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td colspan="2">{guide_msg}</td>
        </tr>
        <tr>
            <th style="width: 50%;">📉 우량주 스위칭 단계</th>
            <th style="width: 50%;">🔄 포트폴리오 복귀 신호</th>
        </tr>
        <tr>
            <td style="vertical-align: top;">
                <strong>상태:</strong> {sw_status}<br>
                <strong>지표:</strong> {sw_details}<br>
                💡 {sw_desc}
            </td>
            <td style="vertical-align: top;">
                <strong>상태:</strong> {rv_status}<br>
                <strong>지표:</strong> {rv_details}<br>
                💡 {rv_desc}
            </td>
        </tr>
    </tbody>
</table>
"""
st.markdown(tactical_html, unsafe_allow_html=True)

# 화살표 아이콘 (SVG)
st.markdown("""
<div style="display: flex; justify-content: center; margin: 25px 0;">
    <svg xmlns="http://www.w3.org/2000/svg" height="40" viewBox="0 -960 960 960" width="40" fill="#21c354">
        <path d="M480-200 240-440l56-56 184 183 184-183 56 56-240 240Zm0-240L240-680l56-56 184 183 184-183 56 56-240 240Z"/>
    </svg>
</div>
""", unsafe_allow_html=True)

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

# LAA
spy_200ma = ivv.rolling(window=200).mean().iloc[-1] if not ivv.empty and enough_length(ivv, 200) else np.nan
laa_dynamic = 'VGSH' if (curr_unrate > ma12_unrate and (not np.isnan(curr_p) and curr_p < spy_200ma)) else 'QQQM'
laa_tickers = ['VTV', 'VGIT', 'IAUM', laa_dynamic]

laa_res = []
laa_sum = 0.0
for t in laa_tickers:
    price_t = safe_series(prices, t).iloc[-1] if not safe_series(prices, t).empty else np.nan
    sh, cs = calc_shares(budget_per_strat * 0.25, price_t, exchange_rate)
    laa_res.append({"종목": t, "수량": f"{sh}주", "금액": cs, "금액표시": f"{cs:,.0f}원"})
    laa_sum += cs

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
# 요약 출력 (공통 CSS .unified-table 적용)
# ---------------------------
st.subheader("📊 전략별 리밸런싱 결과 요약")

vaa_status = "방어" if vaa_is_crisis else "공격"
laa_status = "불황" if laa_dynamic == 'VGSH' else "정상"
dm_status = "채권" if dm_pick == 'BND' else "주식"
total_invest = vaa_c + laa_sum + dm_c

html_table = f"""
<table class="unified-table">
    <thead>
        <tr style="border-bottom: 2px solid rgba(128, 128, 128, 0.8);">
            <th>전략</th>
            <th>상태</th>
            <th>추천/종목</th>
            <th>수량</th>
            <th>투자금액</th>
        </tr>
    </thead>
    <tbody>
        <tr style="border-bottom: 2px solid rgba(128, 128, 128, 0.8);">
            <td>VAA (🛡️)</td>
            <td>{vaa_status}</td>
            <td>{vaa_pick or "N/A"}</td>
            <td>{vaa_s}주</td>
            <td>{vaa_c:,.0f}원</td>
        </tr>
        <tr>
            <td rowspan="5">LAA (🐢)</td>
            <td rowspan="5">{laa_status}</td>
            <td>{laa_res[0]["종목"]}</td>
            <td>{laa_res[0]["수량"]}</td>
            <td>{laa_res[0]["금액표시"]}</td>
        </tr>
        <tr>
            <td>{laa_res[1]["종목"]}</td>
            <td>{laa_res[1]["수량"]}</td>
            <td>{laa_res[1]["금액표시"]}</td>
        </tr>
        <tr>
            <td>{laa_res[2]["종목"]}</td>
            <td>{laa_res[2]["수량"]}</td>
            <td>{laa_res[2]["금액표시"]}</td>
        </tr>
        <tr>
            <td>{laa_res[3]["종목"]}</td>
            <td>{laa_res[3]["수량"]}</td>
            <td>{laa_res[3]["금액표시"]}</td>
        </tr>
        <tr style="border-bottom: 2px solid rgba(128, 128, 128, 0.8);">
            <td colspan="2"><strong>LAA 소계</strong></td>
            <td><strong>{laa_sum:,.0f}원</strong></td>
        </tr>
        <tr style="border-bottom: 2px solid rgba(128, 128, 128, 0.8);">
            <td>듀얼모멘텀 (🚀)</td>
            <td>{dm_status}</td>
            <td>{dm_pick or "N/A"}</td>
            <td>{dm_s}주</td>
            <td>{dm_c:,.0f}원</td>
        </tr>
        <tr>
            <td colspan="4"><strong>📌 전체 총 투자금액 합계</strong></td>
            <td><strong>{total_invest:,.0f}원</strong></td>
        </tr>
    </tbody>
</table>
"""
st.markdown(html_table, unsafe_allow_html=True)

if not np.isnan(curr_unrate):
    st.success(f"📊 **실업률 모니터링**: 현재 **{curr_unrate:.2f}%** (12개월 평균: **{ma12_unrate:.2f}%**)")
else:
    st.success("실업률 데이터 없음")

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
# 전략별 상세 브리핑을 표로 (Pandas HTML 렌더링)
# ---------------------------
st.subheader("📝 전략별 상세 브리핑 (요약 표)")
brief_rows = []

brief_rows.append({
    "전략": "VAA (🛡️)",
    "판단 근거": "공격군 중 일부 모멘텀이 음수이면 방어 전환" if vaa_is_crisis else "공격 모멘텀 우세",
    "영향": "방어 모드: 주식 노출 축소 → 채권/현금 확대; 공격 모드: 모멘텀 우수 자산 집중",
    "시장 상황": "변동성 확대 시 방어 자산 선호; 모멘텀 회복 시 공격 자산 재가동"
})
brief_rows.append({
    "전략": "LAA (🐢)",
    "판단 근거": "실업률 상승(현재 > 12M 평균) AND S&P(IVV) 200일선 하회 → 방어",
    "영향": "동시 악화 시 변동성 완화 목적의 초단기 국채 전환; 정상 시 분산 유지",
    "시장 상황": "경기 약화 신호(실업률 상승)와 가격 약세 동시 발생 시 방어적 포지셔닝 권장"
})
brief_rows.append({
    "전략": "듀얼모멘텀 (🚀)",
    "판단 근거": "12개월 상대수익률(IVV vs VEA) 비교 후 현금(SGOV) 대비 우위 판단",
    "영향": "주식 우위 시 주식 노출 유지; 우위 없으면 채권(BND)으로 방어",
    "시장 상황": "글로벌 주식 상대수익률이 현저히 낮아지면 안전자산 선호; 주식 우위 시 리스크 온"
})

brief_df = pd.DataFrame(brief_rows).replace({r"\n": " "}, regex=True)
brief_df.index = np.arange(1, len(brief_df) + 1)
brief_df.index.name = "No."

st.markdown(brief_df.reset_index().to_html(classes="unified-table", index=False, escape=False), unsafe_allow_html=True)

st_divider()

# ---------------------------
# 하단 탭: 히스토리, 주요 지표 차트(실업률 포함), 종목 정보
# ---------------------------
t1, t2, t3 = st.tabs(["📜 리밸런싱 히스토리", "📉 주요 지표 차트", "ℹ️ 종목 정보"])
with t1:
    if st.session_state['history']:
        hist_df = pd.DataFrame(st.session_state['history'])
        hist_df.index = np.arange(1, len(hist_df) + 1)
        hist_df.index.name = "No."
        st.markdown(hist_df.reset_index().to_html(classes="unified-table", index=False, escape=False), unsafe_allow_html=True)
    else:
        st.success("저장된 히스토리가 없습니다.")

with t2:
    st.subheader("실업률 (월별) 및 12개월 평균")
    if not unrate_history.empty:
        plot_df = unrate_history.copy()
        plot_df.index.name = "Month"
        display_unrate = plot_df.rename(columns={'UNRATE': '실업률(%)', 'MA12': '12개월 평균(%)'})
        
        formatted_unrate = display_unrate.copy()
        for col in formatted_unrate.columns:
            formatted_unrate[col] = formatted_unrate[col].apply(lambda x: f"{x:.2f}")
            
        st.markdown(formatted_unrate.reset_index().to_html(classes="unified-table", index=False, escape=False), unsafe_allow_html=True)
        st.line_chart(plot_df)
        st.caption("월별 실업률과 12개월 이동평균을 함께 표시합니다.")
    else:
        st.success("실업률 데이터가 없어 차트를 표시할 수 없습니다.")

with t3:
    rows = []
    for k, v in TICKER_DESC.items():
        s = safe_series(prices, k)
        price_str = f"${s.iloc[-1]:.2f}" if not s.empty else "N/A"
        kr_equivalent = KR_ETF_DESC.get(k, "대체 종목 없음")
        rows.append({
            "미국 티커": k, 
            "현재가 (미국)": price_str, 
            "설명": v, 
            "🇰🇷 대체가능 한국 상장 ETF": kr_equivalent
        })
        
    info_df = pd.DataFrame(rows)
    info_df.index = np.arange(1, len(info_df) + 1)
    info_df.index.name = "No."
    st.markdown(info_df.reset_index().to_html(classes="unified-table", index=False, escape=False), unsafe_allow_html=True)

st_divider()
st.markdown("**주의사항**: 이 도구는 교육용이며 투자 권유가 아닙니다. 데이터 부족, 네트워크 오류, yfinance/FRED 응답 실패 등으로 결과가 달라질 수 있습니다.")
