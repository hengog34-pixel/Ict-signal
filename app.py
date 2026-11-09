# ICT Signal Tool v2 - Streamlit web app (with MA, RSI and a cleaner UI)
# Educational only. Not financial advice. No profit is guaranteed.

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from plotly.subplots import make_subplots

st.set_page_config(page_title="ICT Signal Tool", page_icon="📈", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1100px;}
.signal-card {border-radius: 16px; padding: 18px 20px; margin: 8px 0 14px 0; color: white;}
.signal-long {background: linear-gradient(135deg, #0f9d58, #0b6e3f);}
.signal-short {background: linear-gradient(135deg, #d93025, #9b1c14);}
.signal-wait {background: linear-gradient(135deg, #5f6b7a, #3c4450);}
.signal-title {font-size: 2rem; font-weight: 800; line-height: 1.1;}
.signal-sub {opacity: 0.92; font-size: 0.95rem; margin-top: 6px;}
</style>
""", unsafe_allow_html=True)

st.title("📈 ICT Signal Tool")
st.caption("Educational only. Not financial advice. Test on a demo account first.")


def fmt(x):
    return f"{x:,.2f}" if abs(x) >= 10 else f"{x:,.5f}"


# ---------- Inputs (top of page, easy on phones) ----------
c1, c2, c3 = st.columns([2, 1, 1])
symbol = c1.text_input("Symbol", "BTC-USD").strip().upper()
interval = c2.selectbox("Interval", ["15m", "1h", "1d"], index=1)
period = c3.selectbox("Period", ["5d", "30d", "60d", "6mo", "1y"], index=1)
st.caption("Examples: ETH-USD, EURUSD=X, GC=F (gold), AAPL, TSLA")

with st.expander("⚙️ Advanced settings"):
    a1, a2 = st.columns(2)
    swing_n = a1.slider("Swing strength (bars each side)", 2, 6, 3)
    fvg_lookback = a2.slider("FVG lookback (bars)", 10, 80, 30)
    sweep_lookback = a1.slider("Sweep lookback (bars)", 5, 30, 10)
    rr = a2.slider("Risk:Reward", 1.0, 4.0, 2.0, 0.5)
    rsi_len = a1.slider("RSI length", 5, 30, 14)
    show_ma = a2.checkbox("Show MA20 / MA50", True)
    show_rsi = a2.checkbox("Show RSI panel", True)
    candle_style = a1.selectbox("Candle style",
                                ["TradingView (maroon/black)", "Classic (green/red)"])
    bars_shown = a2.slider("Bars shown", 50, 500, 120, 10)
    dark_chart = a1.checkbox("Dark chart", False)
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()


@st.cache_data(ttl=300)
def load_data(symbol, interval, period):
    df = yf.download(symbol, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna().reset_index()
    if len(df) > 0:
        df = df.rename(columns={df.columns[0]: "Time"})
        if interval != "1d":
            df["Time"] = pd.to_datetime(df["Time"], utc=True)
    return df


def add_indicators(df, rsi_len):
    df = df.copy()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / rsi_len, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_len, adjust=False).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))
    return df


def analyze(df, n, fvg_lookback, sweep_lookback, rr):
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    last = len(df) - 1

    swing_highs, swing_lows = [], []
    for i in range(n, len(df) - n):
        if h[i] == h[i - n:i + n + 1].max():
            swing_highs.append((i, h[i]))
        if l[i] == l[i - n:i + n + 1].min():
            swing_lows.append((i, l[i]))
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    hh = swing_highs[-1][1] > swing_highs[-2][1]
    hl = swing_lows[-1][1] > swing_lows[-2][1]
    if hh and hl:
        bias = "BULLISH"
    elif (not hh) and (not hl):
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    bull_sweep = bear_sweep = False
    for j in range(max(0, len(df) - sweep_lookback), len(df)):
        for idx, price in swing_lows:
            if idx < j - n and l[j] < price and c[j] > price:
                bull_sweep = True
        for idx, price in swing_highs:
            if idx < j - n and h[j] > price and c[j] < price:
                bear_sweep = True

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


SESSIONS = [(0, 8, "ASIA"), (8, 13, "LONDON"), (13, 21, "NEW YORK")]  # UTC hours


def session_name(hour):
    for a, b, name in SESSIONS:
        if a <= hour < b:
            return name
    return "LATE"


def ict_extras(df, r, interval, rr):
    """Session levels, 6-point checklist, grade and final signal (times are UTC)."""
    if interval == "1d" or len(df) < 20:
        return None
    t = df["Time"]
    day = t.dt.date
    today = day.iloc[-1]
    today_df = df[day == today]

    levels = {"Open": today_df["Open"].iloc[0]}
    asia = today_df[today_df["Time"].dt.hour < 8]
    if len(asia):
        levels["Asia H"] = asia["High"].max()
        levels["Asia L"] = asia["Low"].min()
    prev_days = sorted(set(day) - {today})
    if prev_days:
        prev_df = df[day == prev_days[-1]]
        levels["PDH"] = prev_df["High"].max()
        levels["PDL"] = prev_df["Low"].min()

    # Did price sweep a session / previous-day level recently?
    recent = df.tail(10)
    bear_level = any(((recent["High"] > levels[k]) & (recent["Close"] < levels[k])).any()
                     for k in ("Asia H", "PDH") if k in levels)
    bull_level = any(((recent["Low"] < levels[k]) & (recent["Close"] > levels[k])).any()
                     for k in ("Asia L", "PDL") if k in levels)

    hour = t.iloc[-1].hour
    killzone = (7 <= hour < 10) or (12 <= hour < 15)
    ma_ok = bool(pd.notna(df["MA50"].iloc[-1]))
    ma_up = ma_ok and bool(df["MA20"].iloc[-1] > df["MA50"].iloc[-1])
    ma_down = ma_ok and bool(df["MA20"].iloc[-1] < df["MA50"].iloc[-1])

    bull_list = [("Structure bullish", r["bias"] == "BULLISH"),
                 ("Swing liquidity sweep (low)", r["bull_sweep"]),
                 ("Price inside bullish FVG", r["in_bull"]),
                 ("Killzone (London / New York)", killzone),
                 ("Asia low / PDL swept", bull_level),
                 ("MA20 above MA50", ma_up)]
    bear_list = [("Structure bearish", r["bias"] == "BEARISH"),
                 ("Swing liquidity sweep (high)", r["bear_sweep"]),
                 ("Price inside bearish FVG", r["in_bear"]),
                 ("Killzone (London / New York)", killzone),
                 ("Asia high / PDH swept", bear_level),
                 ("MA20 below MA50", ma_down)]
    nb = sum(1 for _, ok in bull_list if ok)
    ns = sum(1 for _, ok in bear_list if ok)
    lean = "BUY" if nb > ns else ("SELL" if ns > nb else None)
    checks = max(nb, ns)
    grade = "A+" if checks >= 5 else ("B" if checks == 4 else ("C" if checks == 3 else "D"))

    # Final signal: needs grade B or better and a valid stop
    entry = df["Close"].iloc[-1]
    signal, stop, target = "WAIT", None, None
    if lean == "BUY" and checks >= 4:
        stop = r["swing_lows"][-1][1] * 0.999
        if entry > stop:
            signal, target = "LONG", entry + rr * (entry - stop)
    elif lean == "SELL" and checks >= 4:
        stop = r["swing_highs"][-1][1] * 1.001
        if entry < stop:
            signal, target = "SHORT", entry - rr * (stop - entry)
    if signal == "WAIT":
        stop = None

    # Sideways or trending (last 40 bars)
    w = df.tail(40)
    rng = w["High"].max() - w["Low"].min()
    net = abs(w["Close"].iloc[-1] - w["Close"].iloc[0])
    if rng and net / rng < 0.35:
        state = "SIDEWAYS"
    else:
        state = "TRENDING UP" if w["Close"].iloc[-1] > w["Close"].iloc[0] else "TRENDING DOWN"

    name = session_name(hour)
    label = "ASIA BUILD" if name == "ASIA" else name + (" KILLZONE" if killzone else "")
    return dict(levels=levels, lean=lean, checks=checks, grade=grade,
                score=round(checks / 6 * 100), signal=signal, entry=entry,
                stop=stop, target=target, state=state, session_label=label,
                check_list=bear_list if lean == "SELL" else bull_list,
                lean_text={"BUY": "BUY", "SELL": "SELL"}.get(lean, "BUY (tie, no lean)"))


def make_chart(df, r, title, show_ma, show_rsi, candle_style, bars_shown, dark,
               levels=None):
    last = len(df) - 1
    rows = 2 if show_rsi else 1
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True,
                        row_heights=[0.72, 0.28] if show_rsi else [1.0],
                        vertical_spacing=0.04)

    if candle_style.startswith("TradingView"):
        up_color = "#8b1a1a"
        down_color = "#e5e5e5" if dark else "#111111"
    else:
        up_color, down_color = "#26a69a", "#ef5350"
    fg = "#e5e5e5" if dark else "#111111"
    grid = "#2a2f3a" if dark else "#e3e6ea"

    fig.add_trace(go.Candlestick(
        x=df["Time"], open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"], name="Price",
        increasing=dict(line=dict(color=up_color, width=1), fillcolor=up_color),
        decreasing=dict(line=dict(color=down_color, width=1), fillcolor=down_color)),
        row=1, col=1)

    # Dotted line + label at the last price (like TradingView)
    last_close = df["Close"].iloc[-1]
    fig.add_hline(y=last_close, line_dash="dot", line_color=fg, line_width=1,
                  annotation_text=fmt(last_close), annotation_position="top right",
                  row=1, col=1)

    if levels:
        level_colors = {"Open": fg, "Asia H": "#1e88e5", "Asia L": "#1e88e5",
                        "PDH": "#f9a825", "PDL": "#f9a825"}
        for lv_name, lv_price in levels.items():
            fig.add_hline(y=lv_price, line_dash="dot", line_width=1,
                          line_color=level_colors.get(lv_name, fg),
                          annotation_text=lv_name, annotation_position="top left",
                          row=1, col=1)

    if show_ma:
        fig.add_trace(go.Scatter(x=df["Time"], y=df["MA20"], name="MA20",
                                 line=dict(color="orange", width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Time"], y=df["MA50"], name="MA50",
                                 line=dict(color="#4da3ff", width=1.5)), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=[df["Time"][i] for i, _ in r["swing_highs"]],
        y=[p for _, p in r["swing_highs"]], mode="markers", name="Swing High",
        marker=dict(symbol="triangle-down", color="red", size=9)), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=[df["Time"][i] for i, _ in r["swing_lows"]],
        y=[p for _, p in r["swing_lows"]], mode="markers", name="Swing Low",
        marker=dict(symbol="triangle-up", color="#2ecc71", size=9)), row=1, col=1)

    for t, i, bottom, top in r["fvgs"]:
        fig.add_shape(
            type="rect", x0=df["Time"][i], x1=df["Time"][last],
            y0=bottom, y1=top, line_width=0, row=1, col=1,
            fillcolor="rgba(0,200,0,0.25)" if t == "bull" else "rgba(230,0,0,0.25)")

    if r["signal"] != "WAIT":
        for name, price, color in [("Entry", r["entry"], "gray"),
                                   ("Stop", r["stop"], "red"),
                                   ("Target", r["target"], "#2ecc71")]:
            fig.add_hline(y=price, line_dash="dash", line_color=color,
                          annotation_text=name, row=1, col=1)

    if show_rsi:
        fig.add_trace(go.Scatter(x=df["Time"], y=df["RSI"], name="RSI",
                                 line=dict(color="#b388ff", width=1.5)), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="#2ecc71", row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)

    # Zoom to the last N bars so candles are big and easy to read
    start = max(0, len(df) - bars_shown)
    vis = df.iloc[start:]
    ymin, ymax = vis["Low"].min(), vis["High"].max()
    pad = (ymax - ymin) * 0.08 or ymax * 0.001
    fig.update_yaxes(range=[ymin - pad, ymax + pad], row=1, col=1)
    if len(df) > 1:
        step = df["Time"].iloc[-1] - df["Time"].iloc[-2]
        fig.update_xaxes(range=[df["Time"].iloc[start],
                                df["Time"].iloc[-1] + step * 6])

    fig.update_xaxes(rangeslider_visible=False, showgrid=True,
                     gridcolor=grid, griddash="dot")
    fig.update_yaxes(side="right", showgrid=True, gridcolor=grid, griddash="dot")

    fig.update_layout(
        title=title, template="plotly_dark" if dark else "plotly_white",
        dragmode="pan",
        height=760 if show_rsi else 600,
        margin=dict(l=10, r=10, t=60, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    return fig


# ---------- Main page ----------
if not symbol:
    st.info("Enter a symbol above.")
    st.stop()

df = load_data(symbol, interval, period)
if df.empty:
    st.error("No data found. Check the symbol, or try a shorter period "
             "(15m data only works up to 60 days).")
    st.stop()

df = add_indicators(df, rsi_len)
result = analyze(df, swing_n, fvg_lookback, sweep_lookback, rr)
if result is None:
    st.warning("Not enough data to find swings. Try a longer period.")
    st.stop()

ext = ict_extras(df, result, interval, rr)
if ext:
    result.update(signal=ext["signal"], entry=ext["entry"],
                  stop=ext["stop"], target=ext["target"])

last_row = df.iloc[-1]
prev_close = df["Close"].iloc[-2] if len(df) > 1 else last_row["Close"]
change = (last_row["Close"] / prev_close - 1) * 100

# Status strip (session, state, lean, grade, checklist count)
if ext:
    lean_txt = {"BUY": "BUY leads", "SELL": "SELL leads"}.get(ext["lean"], "No lean")
    if ext["signal"] == "WAIT":
        note = "HELD · " + ext["state"].lower() + (" — no A+" if ext["grade"] != "A+" else "")
    else:
        note = "ACTIVE · " + ext["signal"] + " · grade " + ext["grade"]
    st.markdown(
        "<style>"
        ".zq-strip{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0;}"
        ".zq-chip{border:1px solid rgba(128,128,128,.45);border-radius:10px;padding:4px 10px;font-weight:700;font-size:.85rem;letter-spacing:.03em;}"
        ".zq-gold{background:#f5c542;color:#1b1b1b;border-color:#f5c542;}"
        ".zq-note{background:rgba(245,197,66,.15);border-left:4px solid #f5c542;padding:6px 10px;border-radius:6px;font-size:.9rem;margin-bottom:8px;}"
        "</style>"
        "<div class='zq-strip'>"
        "<span class='zq-chip zq-gold'>" + ext["session_label"] + "</span>"
        "<span class='zq-chip'>" + ext["state"] + "</span>"
        "<span class='zq-chip'>" + ext["signal"] + " | " + lean_txt + " · " + ext["grade"] + " · " + str(ext["score"]) + "</span>"
        "<span class='zq-chip'>" + str(ext["checks"]) + "/6</span>"
        "</div><div class='zq-note'>" + note + " · times in UTC</div>",
        unsafe_allow_html=True)

# Signal card
sig = result["signal"]
cls = {"LONG": "signal-long", "SHORT": "signal-short"}.get(sig, "signal-wait")
icon = {"LONG": "🟢", "SHORT": "🔴"}.get(sig, "⚪")
if sig == "WAIT":
    sub = "No clear setup right now. WAIT is a normal result."
else:
    sub = ("Entry " + fmt(result["entry"]) + " · Stop " + fmt(result["stop"])
           + " · Target " + fmt(result["target"]))
st.markdown(
    '<div class="signal-card ' + cls + '"><div class="signal-title">'
    + icon + " " + sig + '</div><div class="signal-sub">'
    + symbol + " · " + interval + " · " + sub + "</div></div>",
    unsafe_allow_html=True)

# Key numbers
rsi_val = last_row["RSI"]
if rsi_val > 70:
    rsi_note = "Overbought"
elif rsi_val < 30:
    rsi_note = "Oversold"
else:
    rsi_note = "Neutral"

if pd.notna(last_row["MA50"]):
    trend = "Uptrend" if last_row["MA20"] > last_row["MA50"] else "Downtrend"
else:
    trend = "Not enough data"

m1, m2, m3, m4 = st.columns(4)
m1.metric("Price", fmt(last_row["Close"]), f"{change:+.2f}%")
m2.metric("RSI", f"{rsi_val:.1f}", rsi_note, delta_color="off")
m3.metric("MA trend", trend)
m4.metric("Structure", result["bias"])

# Tabs
tab_chart, tab_detail, tab_help = st.tabs(["📊 Chart", "🔍 Signal details", "📘 Help"])

with tab_chart:
    fig = make_chart(df, result, symbol + " (" + interval + ")", show_ma, show_rsi,
                     candle_style, bars_shown, dark_chart,
                     ext["levels"] if ext else None)
    st.plotly_chart(fig, use_container_width=True,
                    config={"displaylogo": False, "scrollZoom": True})

with tab_detail:
    def mark(flag):
        return "✅" if flag else "❌"
    if ext:
        st.write("**ICT checklist:**", ext["checks"], "/ 6 for the", ext["lean_text"],
                 "side | Grade:", ext["grade"])
        for label, ok in ext["check_list"]:
            st.write(mark(ok), label)
        st.write("Levels:", {k: round(float(v), 2) for k, v in ext["levels"].items()})
        st.divider()
    st.write("**Score:**", result["score"], "(LONG at +2 or more, SHORT at -2 or less)")
    st.write("Market structure:", result["bias"])
    st.write(mark(result["bull_sweep"]), "Bullish liquidity sweep")
    st.write(mark(result["bear_sweep"]), "Bearish liquidity sweep")
    st.write(mark(result["in_bull"]), "Price inside bullish FVG")
    st.write(mark(result["in_bear"]), "Price inside bearish FVG")
    st.write("MA20:", fmt(last_row["MA20"]) if pd.notna(last_row["MA20"]) else "n/a",
             "| MA50:", fmt(last_row["MA50"]) if pd.notna(last_row["MA50"]) else "n/a")

with tab_help:
    st.markdown("""
- **Market structure**: higher highs and higher lows is bullish, lower highs and lower lows is bearish.
- **Liquidity sweep**: price wicks past an old swing high or low, then closes back inside.
- **FVG (Fair Value Gap)**: a gap between candle 1 and candle 3 that price often returns to.
- **MA20 / MA50**: moving averages. MA20 above MA50 usually means an uptrend.
- **RSI**: above 70 is overbought, below 30 is oversold.
- **Chart tip**: drag to move, pinch to zoom, tap the home icon to reset.

This tool is for learning only. Signals are not guaranteed and are not advice.
""")
