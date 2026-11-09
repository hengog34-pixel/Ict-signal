# ICT Signal Tool - Streamlit web app
# Educational only. Not financial advice. No profit is guaranteed.

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="ICT Signal Tool", layout="wide")
st.title("ICT Signal Tool")
st.caption("Educational only. Not financial advice. Test on a demo account first.")

# ---------- Sidebar inputs ----------
with st.sidebar:
    st.header("Settings")
    symbol = st.text_input("Symbol", "BTC-USD").strip().upper()
    interval = st.selectbox("Interval", ["15m", "1h", "1d"], index=1)
    period = st.selectbox("Period", ["5d", "30d", "60d", "6mo", "1y"], index=1)
    swing_n = st.slider("Swing strength (bars each side)", 2, 6, 3)
    fvg_lookback = st.slider("FVG lookback (bars)", 10, 80, 30)
    sweep_lookback = st.slider("Sweep lookback (bars)", 5, 30, 10)
    rr = st.slider("Risk:Reward", 1.0, 4.0, 2.0, 0.5)
    st.caption("Examples: ETH-USD, EURUSD=X, GC=F (gold), AAPL, TSLA")


@st.cache_data(ttl=300)
def load_data(symbol, interval, period):
    df = yf.download(symbol, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna().reset_index()
    if len(df) > 0:
        df = df.rename(columns={df.columns[0]: "Time"})
    return df


def analyze(df, n, fvg_lookback, sweep_lookback, rr):
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    last = len(df) - 1

    # Swing highs / lows
    swing_highs, swing_lows = [], []
    for i in range(n, len(df) - n):
        if h[i] == h[i - n:i + n + 1].max():
            swing_highs.append((i, h[i]))
        if l[i] == l[i - n:i + n + 1].min():
            swing_lows.append((i, l[i]))
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    # Market structure
    hh = swing_highs[-1][1] > swing_highs[-2][1]
    hl = swing_lows[-1][1] > swing_lows[-2][1]
    if hh and hl:
        bias = "BULLISH"
    elif (not hh) and (not hl):
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # Liquidity sweeps
    bull_sweep = bear_sweep = False
    for j in range(max(0, len(df) - sweep_lookback), len(df)):
        for idx, price in swing_lows:
            if idx < j - n and l[j] < price and c[j] > price:
                bull_sweep = True
        for idx, price in swing_highs:
            if idx < j - n and h[j] > price and c[j] < price:
                bear_sweep = True

    # Fair Value Gaps
    fvgs = []
    start = max(2, len(df) - fvg_lookback)
    for i in range(start, len(df)):
        if l[i] > h[i - 2]:
            bottom, top = h[i - 2], l[i]
            if i == last or l[i + 1:].min() > bottom:
                fvgs.append(("bull", i - 2, bottom, top))
        if h[i] < l[i - 2]:
            bottom, top = h[i], l[i - 2]
            if i == last or h[i + 1:].max() < top:
                fvgs.append(("bear", i - 2, bottom, top))

    in_bull = any(t == "bull" and l[last] <= top and c[last] >= bottom
                  for t, _, bottom, top in fvgs)
    in_bear = any(t == "bear" and h[last] >= bottom and c[last] <= top
                  for t, _, bottom, top in fvgs)

    # Score and signal
    score = 0
    score += 1 if bias == "BULLISH" else (-1 if bias == "BEARISH" else 0)
    score += 1 if bull_sweep else 0
    score -= 1 if bear_sweep else 0
    score += 1 if in_bull else 0
    score -= 1 if in_bear else 0

    signal, entry, stop, target = "WAIT", c[last], None, None
    if score >= 2:
        stop = swing_lows[-1][1] * 0.999
        if entry > stop:
            signal = "LONG"
            target = entry + rr * (entry - stop)
    elif score <= -2:
        stop = swing_highs[-1][1] * 1.001
        if entry < stop:
            signal = "SHORT"
            target = entry - rr * (stop - entry)

    return dict(bias=bias, bull_sweep=bull_sweep, bear_sweep=bear_sweep,
                in_bull=in_bull, in_bear=in_bear, score=score, signal=signal,
                entry=entry, stop=stop, target=target, fvgs=fvgs,
                swing_highs=swing_highs, swing_lows=swing_lows)


def make_chart(df, r, title):
    last = len(df) - 1
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["Time"], open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="Price"))
    fig.add_trace(go.Scatter(
        x=[df["Time"][i] for i, _ in r["swing_highs"]],
        y=[p for _, p in r["swing_highs"]], mode="markers", name="Swing High",
        marker=dict(symbol="triangle-down", color="red", size=9)))
    fig.add_trace(go.Scatter(
        x=[df["Time"][i] for i, _ in r["swing_lows"]],
        y=[p for _, p in r["swing_lows"]], mode="markers", name="Swing Low",
        marker=dict(symbol="triangle-up", color="green", size=9)))
    for t, i, bottom, top in r["fvgs"]:
        fig.add_shape(
            type="rect", x0=df["Time"][i], x1=df["Time"][last],
            y0=bottom, y1=top, line_width=0,
            fillcolor="rgba(0,180,0,0.25)" if t == "bull" else "rgba(220,0,0,0.25)")
    if r["signal"] != "WAIT":
        for name, price, color in [("Entry", r["entry"], "gray"),
                                   ("Stop", r["stop"], "red"),
                                   ("Target", r["target"], "green")]:
            fig.add_hline(y=price, line_dash="dash", line_color=color,
                          annotation_text=name)
    fig.update_layout(title=title, xaxis_rangeslider_visible=False,
                      height=600, margin=dict(l=10, r=10, t=50, b=10))
    return fig


# ---------- Main page ----------
if not symbol:
    st.info("Enter a symbol in the sidebar.")
    st.stop()

df = load_data(symbol, interval, period)
if df.empty:
    st.error("No data found. Check the symbol, or try a shorter period "
             "(15m data only works up to 60 days).")
    st.stop()

result = analyze(df, swing_n, fvg_lookback, sweep_lookback, rr)
if result is None:
    st.warning("Not enough data to find swings. Try a longer period.")
    st.stop()

# Signal summary
c1, c2, c3 = st.columns(3)
c1.metric("Signal", result["signal"])
c2.metric("Market structure", result["bias"])
c3.metric("Score", result["score"])

if result["signal"] != "WAIT":
    d1, d2, d3 = st.columns(3)
    d1.metric("Entry", round(result["entry"], 2))
    d2.metric("Stop loss", round(result["stop"], 2))
    d3.metric("Take profit", round(result["target"], 2))
else:
    st.info("No clear setup right now. WAIT is a normal result.")

with st.expander("Why this signal?"):
    st.write("Bullish sweep:", result["bull_sweep"],
             "| Bearish sweep:", result["bear_sweep"])
    st.write("Price in bullish FVG:", result["in_bull"],
             "| in bearish FVG:", result["in_bear"])

fig = make_chart(df, result, symbol + " (" + interval + ") - " + result["signal"])
st.plotly_chart(fig, use_container_width=True)
