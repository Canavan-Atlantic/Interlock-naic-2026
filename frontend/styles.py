"""Local visual language for the Canavan Atlantic INTERLOCK frontend."""

import streamlit as st


BRAND_CSS = """
<style>
:root {
  --interlock-navy: #063747;
  --interlock-navy-2: #073b4c;
  --interlock-teal: #167a74;
  --interlock-turquoise: #00a89d;
  --interlock-aqua: #9ce2dc;
  --interlock-ink: #123447;
  --interlock-muted: #5c7380;
  --interlock-pale: #f2fafb;
  --interlock-blue: #edf8fa;
  --interlock-line: #d9e4e8;
  --interlock-amber: #a66a13;
  --interlock-red: #a63d40;
}

html, body, [class*="css"] { font-family: "Montserrat", "Aptos", "Segoe UI", Arial, sans-serif; }
.stApp { background: #ffffff; color: var(--interlock-ink); }
[data-testid="stHeader"] { background: transparent; height: 0; }
[data-testid="stDecoration"], [data-testid="stToolbar"] { display: none; }
[data-testid="stMainBlockContainer"] {
  width: 100%; max-width: 1600px; padding-top: 0.2rem;
  padding-left: clamp(1rem, 4vw, 4rem); padding-right: clamp(1rem, 4vw, 4rem);
}

.interlock-site-header {
  align-items: center; border-bottom: 1px solid var(--interlock-line); display: flex;
  justify-content: space-between; min-height: 76px; padding: 0 0.2rem;
}
.interlock-ca-brand { align-items: center; display: flex; min-width: 12rem; }
.interlock-ca-logo { display: block; height: auto; max-width: 12.8rem; width: 100%; }
.interlock-ca-fallback { color: var(--interlock-teal); font-size: 1rem; font-weight: 800; letter-spacing: 0.1em; line-height: 1; }
.interlock-ca-fallback small { color: var(--interlock-navy); display: block; font-size: 0.62rem; letter-spacing: 0.28em; margin-top: 0.3rem; }
.interlock-profile { align-items: center; color: var(--interlock-ink); display: flex; font-size: 0.78rem; gap: 0.45rem; justify-content: flex-end; min-width: 14rem; }
.interlock-profile-icon { align-items: center; background: var(--interlock-pale); border: 1px solid var(--interlock-line); border-radius: 50%; display: inline-flex; height: 28px; justify-content: center; position: relative; width: 28px; }
.interlock-profile-icon::before { background: var(--interlock-teal); border-radius: 50%; content: ""; height: 6px; position: absolute; top: 6px; width: 6px; }
.interlock-profile-icon::after { border: 1px solid var(--interlock-teal); border-radius: 8px 8px 5px 5px; bottom: 5px; content: ""; height: 7px; position: absolute; width: 12px; }
.interlock-chevron { color: var(--interlock-teal); font-size: 1rem; margin-left: 0.1rem; }

/* The keyed widget remains functional, but visually reads as web navigation. */
[data-testid="stPills"] {
  border-bottom: 0; height: 76px; margin: -76px clamp(11rem, 17vw, 19rem) 1.25rem clamp(15rem, 24vw, 27rem);
  padding: 0; position: relative; z-index: 4;
}
[data-testid="stPills"] > div { align-items: center; gap: clamp(0.35rem, 2.5vw, 2rem); height: 76px; justify-content: center; }
[data-testid="stPills"] button {
  background: transparent !important; border: 0 !important; border-radius: 0 !important;
  box-shadow: none !important; color: var(--interlock-navy) !important; font-size: 0.78rem;
  font-weight: 600; min-height: 2.6rem; padding: 0.7rem 0.1rem 0.55rem;
}
[data-testid="stPills"] button:hover { color: var(--interlock-teal) !important; }
[data-testid="stPills"] button[aria-pressed="true"] {
  background: transparent !important; border-bottom: 2px solid var(--interlock-turquoise) !important;
  color: var(--interlock-navy) !important; font-weight: 800;
}

.interlock-hero {
  background-color: #3d746d;
  background-image:
    linear-gradient(90deg, rgba(3, 50, 65, 0.98) 0%, rgba(3, 65, 75, 0.93) 25%, rgba(3, 65, 75, 0.62) 43%, rgba(3, 65, 75, 0.2) 60%, rgba(0, 0, 0, 0) 75%),
    var(--interlock-hero-image, linear-gradient(180deg, #b8d6d2 0%, #9fc8c2 42%, #7da69a 43%, #537f73 58%, #2c5f5d 59%, #113b49 100%));
  background-position: center 55%; background-size: cover; box-shadow: 0 18px 42px rgba(6, 55, 71, 0.18);
  min-height: 31rem; overflow: hidden; padding: clamp(3rem, 7vw, 5.5rem) clamp(1.5rem, 6vw, 6rem); position: relative;
}
.interlock-hero::after { border: 1px solid rgba(255, 255, 255, 0.14); border-radius: 50%; content: ""; height: 34rem; opacity: 0.7; position: absolute; right: -11rem; top: -14rem; transform: rotate(-17deg) skewX(-18deg); width: 54rem; }
.interlock-hero-content { max-width: 41rem; position: relative; z-index: 1; }
.interlock-hero-kicker { color: #ffffff; font-size: 0.74rem; font-weight: 800; letter-spacing: 0.2em; margin: 0 0 0.8rem; }
.interlock-eyebrow { color: var(--interlock-aqua); font-size: 0.73rem; font-weight: 800; letter-spacing: 0.16em; margin: 0 0 1.4rem; }
.interlock-hero h1 { color: #ffffff; font-size: clamp(3.15rem, 6vw, 4.8rem); letter-spacing: -0.055em; line-height: 0.98; margin: 0; }
.interlock-hero h1 em { color: var(--interlock-aqua); font-style: normal; }
.interlock-hero-copy { color: rgba(255, 255, 255, 0.88); font-size: 1.03rem; line-height: 1.65; margin: 1.6rem 0 0; max-width: 34rem; }

.st-key-hero_actions { margin: -8.6rem 0 2.1rem; padding: 0 clamp(1.5rem, 6vw, 6rem); position: relative; z-index: 3; }
.st-key-hero_actions [data-testid="stButton"] button { min-height: 3.25rem; padding-left: 1.4rem; padding-right: 1.4rem; }
.st-key-hero_actions [data-testid="stButton"]:last-child button { background: transparent !important; border: 0 !important; border-bottom: 1px solid rgba(255, 255, 255, 0.82) !important; border-radius: 0 !important; color: #ffffff !important; }
.st-key-hero_actions [data-testid="stButton"]:last-child button:hover { border-bottom-color: var(--interlock-aqua) !important; color: var(--interlock-aqua) !important; }

.interlock-section-kicker { color: var(--interlock-teal); font-size: 0.72rem; font-weight: 800; letter-spacing: 0.16em; margin: 2.6rem 0 0.55rem; text-transform: uppercase; }
.interlock-section-title { color: var(--interlock-navy); font-size: clamp(1.8rem, 3vw, 2.65rem); letter-spacing: -0.035em; line-height: 1.08; margin: 0 0 0.75rem; }
.interlock-pack-title { text-transform: uppercase; }
.interlock-section-copy { color: var(--interlock-muted); line-height: 1.65; max-width: 46rem; }
.interlock-line-icon { color: var(--interlock-teal); margin-bottom: 0.8rem; }
.interlock-line-icon svg { fill: none; height: 2.8rem; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; width: 2.8rem; }
.st-key-capability_strip { background: #ffffff; border-bottom: 1px solid var(--interlock-line); margin: 0 -0.5rem; padding: 0.9rem clamp(0.5rem, 2vw, 1.4rem); }
.st-key-capability_strip [data-testid="column"] + [data-testid="column"] .interlock-capability { border-left: 1px solid var(--interlock-line); padding-left: 1.4rem; }
.interlock-capability { min-height: 8.5rem; padding: 0.65rem 1.25rem 0.65rem 0; }
.interlock-capability-title { color: var(--interlock-navy); font-size: 0.98rem; font-weight: 800; margin-bottom: 0.45rem; }
.interlock-capability-copy { color: var(--interlock-muted); font-size: 0.84rem; line-height: 1.55; }

.st-key-truth_band { background: var(--interlock-blue); margin: 0 -0.5rem; overflow: hidden; padding: 1.45rem clamp(0.5rem, 4vw, 2.5rem); position: relative; }
.st-key-truth_band::after { background: repeating-radial-gradient(ellipse at center, transparent 0 1.05rem, rgba(0, 168, 157, 0.14) 1.1rem 1.18rem, transparent 1.23rem 1.9rem); content: ""; height: 15rem; pointer-events: none; position: absolute; right: -2rem; top: -6rem; transform: rotate(-11deg); width: 30rem; }
.st-key-truth_band [data-testid="column"] + [data-testid="column"] .interlock-truth-item { border-left: 1px solid rgba(22, 122, 116, 0.28); }
.interlock-truth-item { display: flex; flex-direction: column; gap: 0.35rem; min-height: 4.5rem; padding: 0.25rem 1rem; position: relative; z-index: 1; }
.interlock-truth-item strong { color: var(--interlock-teal); font-size: 1.48rem; letter-spacing: -0.03em; line-height: 1.05; }
.interlock-truth-item span { color: var(--interlock-ink); font-size: 0.82rem; }
.interlock-step-icon { align-items: center; border: 1px solid var(--interlock-turquoise); border-radius: 50%; color: var(--interlock-teal); display: flex; height: 2.8rem; justify-content: center; margin-bottom: 0.45rem; width: 2.8rem; }
.interlock-step-icon svg { fill: none; height: 1.55rem; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; width: 1.55rem; }
.interlock-step-number { color: var(--interlock-teal); font-size: 0.68rem; font-weight: 800; letter-spacing: 0.08em; }
.st-key-approach_section { padding: 1.5rem 0 0.25rem; }
.st-key-approach_section .interlock-approach-step { min-height: 8rem; padding-right: 1.2rem; position: relative; }
.st-key-approach_section .interlock-approach-step::after { color: var(--interlock-teal); content: "›"; font-size: 2.1rem; font-weight: 300; position: absolute; right: -0.15rem; top: 0.35rem; }
.st-key-approach_section .interlock-approach-step:last-child::after { display: none; }
.interlock-stage-title { color: var(--interlock-navy); font-size: 1rem; font-weight: 800; margin-top: 0.35rem; }
.interlock-stage-copy { color: var(--interlock-muted); font-size: 0.84rem; line-height: 1.55; }

.interlock-footer { align-items: center; background: var(--interlock-navy); color: rgba(255, 255, 255, 0.76); display: flex; justify-content: space-between; margin: 3rem -0.5rem -2rem; min-height: 78px; padding: 0.85rem 1.5rem; }
.interlock-footer-brand { align-items: center; color: white; display: flex; font-size: 0.86rem; }
.interlock-footer-logo { display: block; height: auto; max-width: 13rem; width: 100%; }
.interlock-footer-motto { color: var(--interlock-aqua); font-size: 0.75rem; letter-spacing: 0.12em; }
.interlock-footer-copyright { font-size: 0.7rem; }

[data-testid="stForm"] { background: #f7fbfb; border: 1px solid var(--interlock-line); border-radius: 0.25rem; padding: 1.25rem 1.5rem; }
div[data-testid="stButton"] button, div[data-testid="stFormSubmitButton"] button { border-radius: 0.12rem; font-weight: 700; }
div[data-testid="stButton"] button:not([kind="primary"]), div[data-testid="stFormSubmitButton"] button:not([kind="primary"]) { background: #ffffff; border: 1px solid var(--interlock-teal); color: var(--interlock-navy); }
div[data-testid="stButton"] button[kind="primary"], div[data-testid="stFormSubmitButton"] button[kind="primary"] { background: var(--interlock-turquoise); border: 1px solid var(--interlock-turquoise); color: #ffffff; font-weight: 800; }
div[data-testid="stButton"] button[kind="primary"]:hover, div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover { background: var(--interlock-teal); border-color: var(--interlock-teal); }

.interlock-status-card { background: var(--interlock-pale); border-left: 4px solid var(--interlock-teal); border-radius: 0.15rem; padding: 1.1rem 1.25rem; }
.interlock-status-card.review { border-left-color: var(--interlock-amber); }
.interlock-status-card.failure { border-left-color: var(--interlock-red); }
.interlock-status-label { color: var(--interlock-navy); font-size: 0.72rem; font-weight: 800; letter-spacing: 0.14em; text-transform: uppercase; }
.interlock-summary-card { background: #ffffff; border: 1px solid var(--interlock-line); border-top: 3px solid var(--interlock-turquoise); min-height: 6.2rem; padding: 0.85rem 1rem; }
.interlock-summary-card span, .interlock-summary-card small { color: var(--interlock-muted); display: block; font-size: 0.7rem; }
.interlock-summary-card strong { color: var(--interlock-navy); display: block; font-size: 2rem; line-height: 1.1; margin: 0.35rem 0; }
.interlock-evidence-count { background: var(--interlock-pale); border-top: 2px solid var(--interlock-teal); min-height: 5.6rem; padding: 0.7rem 0.8rem; }
.interlock-evidence-count strong { color: var(--interlock-navy); display: block; font-size: 1.7rem; }
.interlock-evidence-count span { color: var(--interlock-muted); display: block; font-size: 0.7rem; line-height: 1.25; }
.interlock-pill { border-radius: 999px; display: inline-block; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.06em; padding: 0.22rem 0.5rem; text-transform: uppercase; }
.interlock-pill.clear { background: #e0f3ed; color: #14624e; }
.interlock-pill.conditional { background: #fff3d7; color: #8a5c12; }
.interlock-pill.unknown { background: #e8f0f5; color: #356276; }
.interlock-pill.constrained { background: #f8e4e1; color: #8d3035; }

@media (max-width: 900px) {
  .interlock-ca-brand, .interlock-profile { min-width: auto; }
  [data-testid="stPills"] { height: auto; margin: 0 0 1rem; }
  [data-testid="stPills"] > div { gap: 0.8rem; height: auto; justify-content: flex-start; overflow-x: auto; }
  .interlock-hero { min-height: 27rem; }
  .st-key-hero_actions { margin-top: -7rem; }
  .st-key-capability_strip [data-testid="stHorizontalBlock"], .st-key-truth_band [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-capability_strip [data-testid="column"], .st-key-truth_band [data-testid="column"] { flex: 0 0 50%; max-width: 50%; }
  .st-key-capability_strip [data-testid="column"] + [data-testid="column"] .interlock-capability { border-left: 0; }
  .st-key-capability_strip [data-testid="column"]:nth-child(even) .interlock-capability, .st-key-truth_band [data-testid="column"]:nth-child(even) .interlock-truth-item { border-left: 1px solid var(--interlock-line); padding-left: 1.4rem; }
}
@media (max-width: 640px) {
  .interlock-site-header { min-height: 66px; }
  .interlock-ca-logo { max-width: 10.8rem; }
  .interlock-profile span:not(.interlock-profile-icon):not(.interlock-chevron) { display: none; }
  [data-testid="stPills"] > div { gap: 0.55rem; }
  [data-testid="stPills"] button { font-size: 0.72rem; min-height: 2.35rem; padding-bottom: 0.4rem; }
  .interlock-hero { min-height: 25rem; padding: 2.4rem 1.35rem 8rem; }
  .interlock-hero h1 { font-size: clamp(2.7rem, 12vw, 4rem); }
  .st-key-hero_actions { margin: -5.6rem 0 1.8rem; padding: 0 1.35rem; }
  .st-key-hero_actions [data-testid="stButton"] { min-width: 100%; }
  .interlock-footer { align-items: flex-start; flex-direction: column; gap: 0.55rem; margin-bottom: -1rem; }
  .st-key-capability_strip [data-testid="column"], .st-key-truth_band [data-testid="column"] { flex: 0 0 100%; max-width: 100%; }
  .st-key-capability_strip [data-testid="column"] + [data-testid="column"] .interlock-capability { border-left: 0; border-top: 1px solid var(--interlock-line); padding-left: 0; padding-top: 1rem; }
  .st-key-truth_band [data-testid="column"] + [data-testid="column"] .interlock-truth-item { border-left: 0; border-top: 1px solid rgba(22, 122, 116, 0.28); padding-left: 1rem; padding-top: 1rem; }
  .st-key-approach_section > [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
  .st-key-approach_section > [data-testid="stHorizontalBlock"] > [data-testid="column"] { flex: 0 0 100%; max-width: 100%; }
}
</style>
"""


def inject_styles() -> None:
    """Install the local Canavan Atlantic stylesheet."""

    st.markdown(BRAND_CSS, unsafe_allow_html=True)
