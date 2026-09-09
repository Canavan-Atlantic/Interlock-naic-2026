"""Local visual language for the INTERLOCK Streamlit application."""

import streamlit as st


BRAND_CSS = """
<style>
:root {
  --interlock-navy: #062c3d;
  --interlock-navy-2: #07354a;
  --interlock-teal: #167a74;
  --interlock-turquoise: #00a89d;
  --interlock-ink: #173845;
  --interlock-muted: #5c7380;
  --interlock-pale: #eef7f8;
  --interlock-blue: #eaf3f7;
  --interlock-line: #d7e6e9;
  --interlock-amber: #b7791f;
  --interlock-red: #a63d40;
}

/* The app uses native Streamlit containers for structure and this small CSS
   layer only supplies brand colour, hierarchy, and responsive treatment. */
.stApp {
  background: #fbfdfd;
  color: var(--interlock-ink);
  font-family: "Montserrat", "Aptos", "Segoe UI", sans-serif;
}

[data-testid="stHeader"] { background: rgba(251, 253, 253, 0.94); }
[data-testid="stToolbar"] { visibility: hidden; }

.interlock-topbar {
  border-bottom: 1px solid var(--interlock-line);
  padding: 0.35rem 0 0.7rem;
  margin-bottom: 1.4rem;
}
.interlock-brand-wordmark {
  color: var(--interlock-navy);
  font-size: 1.35rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  line-height: 1;
}
.interlock-brand-caption {
  color: var(--interlock-teal);
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  margin-top: 0.3rem;
  text-transform: uppercase;
}
.interlock-nav-note {
  color: var(--interlock-muted);
  font-size: 0.74rem;
  text-align: right;
}

.interlock-hero {
  background:
    linear-gradient(110deg, rgba(6, 44, 61, 0.98) 0%, rgba(7, 53, 74, 0.88) 55%, rgba(22, 122, 116, 0.62) 100%),
    radial-gradient(ellipse at 82% 115%, rgba(0, 168, 157, 0.5) 0 13%, transparent 14%),
    linear-gradient(164deg, transparent 0 54%, rgba(255,255,255,0.08) 55% 56%, transparent 57% 65%, rgba(255,255,255,0.07) 66% 67%, transparent 68%),
    linear-gradient(15deg, #0b4d5a 0 31%, #123e4d 32% 47%, #062c3d 48%);
  border-radius: 0.35rem;
  box-shadow: 0 18px 45px rgba(6, 44, 61, 0.18);
  min-height: 28rem;
  overflow: hidden;
  padding: 3.4rem 3.5rem;
  position: relative;
}
.interlock-hero::before,
.interlock-hero::after {
  border: 1px solid rgba(255,255,255,0.16);
  border-radius: 50%;
  content: "";
  height: 36rem;
  position: absolute;
  right: -10rem;
  top: -14rem;
  transform: rotate(-18deg) skewX(-18deg);
  width: 54rem;
}
.interlock-hero::after {
  height: 27rem;
  right: -6rem;
  top: -8rem;
  width: 42rem;
}
.interlock-hero-content { max-width: 42rem; position: relative; z-index: 1; }
.interlock-eyebrow {
  color: #9ce2dc;
  font-size: 0.74rem;
  font-weight: 800;
  letter-spacing: 0.17em;
  margin: 0 0 1.2rem;
  text-transform: uppercase;
}
.interlock-hero h1 {
  color: #fff;
  font-size: clamp(2.65rem, 6vw, 5rem);
  letter-spacing: -0.055em;
  line-height: 0.98;
  margin: 0;
}
.interlock-hero h1 em { color: #9ce2dc; font-style: normal; }
.interlock-hero-copy {
  color: rgba(255,255,255,0.86);
  font-size: 1.06rem;
  line-height: 1.65;
  margin: 1.5rem 0 0;
  max-width: 37rem;
}
.interlock-hero-note {
  color: rgba(255,255,255,0.65);
  font-size: 0.76rem;
  margin-top: 2rem;
}

.interlock-section-kicker {
  color: var(--interlock-teal);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.15em;
  margin: 2.8rem 0 0.55rem;
  text-transform: uppercase;
}
.interlock-section-title {
  color: var(--interlock-navy);
  font-size: clamp(1.7rem, 3vw, 2.55rem);
  letter-spacing: -0.035em;
  line-height: 1.1;
  margin: 0 0 0.7rem;
}
.interlock-section-copy { color: var(--interlock-muted); line-height: 1.65; max-width: 46rem; }
.interlock-capability-title { color: var(--interlock-navy); font-size: 1.02rem; font-weight: 800; }
.interlock-capability-copy { color: var(--interlock-muted); font-size: 0.87rem; line-height: 1.6; }
.interlock-number {
  color: var(--interlock-turquoise);
  font-size: 0.75rem;
  font-weight: 800;
  letter-spacing: 0.12em;
}
.interlock-stage-title { color: var(--interlock-navy); font-size: 1.03rem; font-weight: 800; margin-top: 0.35rem; }
.interlock-stage-copy { color: var(--interlock-muted); font-size: 0.87rem; line-height: 1.55; }

.interlock-status-card {
  background: var(--interlock-pale);
  border-left: 4px solid var(--interlock-teal);
  border-radius: 0.2rem;
  padding: 1.25rem 1.4rem;
}
.interlock-status-card.review { border-left-color: var(--interlock-amber); }
.interlock-status-card.failure { border-left-color: var(--interlock-red); }
.interlock-status-label {
  color: var(--interlock-navy);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.interlock-muted { color: var(--interlock-muted); }
.interlock-small-label {
  color: var(--interlock-muted);
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.interlock-pill {
  border-radius: 999px;
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  padding: 0.24rem 0.55rem;
  text-transform: uppercase;
}
.interlock-pill.clear { background: #e0f3ed; color: #14624e; }
.interlock-pill.conditional { background: #fff3d7; color: #8a5c12; }
.interlock-pill.unknown { background: #e8f0f5; color: #356276; }
.interlock-pill.constrained { background: #f8e4e1; color: #8d3035; }

div[data-testid="stButton"] button[kind="primary"] {
  background: var(--interlock-turquoise);
  border: 1px solid var(--interlock-turquoise);
  color: #fff;
  font-weight: 800;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
  background: var(--interlock-teal);
  border-color: var(--interlock-teal);
}
div[data-testid="stFormSubmitButton"] button[kind="primary"] {
  background: var(--interlock-turquoise);
  border-color: var(--interlock-turquoise);
  color: #fff;
  font-weight: 800;
}
[data-testid="stPills"] button[aria-pressed="true"] {
  background: var(--interlock-navy);
  color: #fff;
}

.interlock-footer {
  background: var(--interlock-navy);
  color: rgba(255,255,255,0.74);
  margin: 4rem -4rem -3rem;
  padding: 2.7rem 4rem;
}
.interlock-footer strong { color: #fff; }
.interlock-footer-caption { color: #9ce2dc; font-size: 0.7rem; letter-spacing: 0.14em; text-transform: uppercase; }

@media (max-width: 800px) {
  .interlock-hero { min-height: 24rem; padding: 2.2rem 1.5rem; }
  .interlock-footer { margin-left: -1rem; margin-right: -1rem; padding-left: 1.5rem; padding-right: 1.5rem; }
  .interlock-nav-note { text-align: left; }
}
</style>
"""


def inject_styles() -> None:
    """Install the small, local brand stylesheet."""

    st.markdown(BRAND_CSS, unsafe_allow_html=True)
