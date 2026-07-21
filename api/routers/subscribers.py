"""Public subscribe, token-restricted unsubscribe."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr

from api.security import TokenError, verify_unsubscribe_token
from database.subscriber_repository import add_subscriber, remove_subscriber


router = APIRouter(tags=["subscribers"])


class SubscribeRequest(BaseModel):
    email: EmailStr


class SubscribeResponse(BaseModel):
    email: str
    status: str


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<html><head><title>{title}</title></head>"
        f"<body style='font-family:sans-serif;max-width:480px;margin:40px auto'>{body}</body></html>"
    )


_SUBSCRIBE_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Subscribe to THE AI 7</title>
<style>
  :root {
    --navy: #12162a;
    --navy-deep: #0b0e1c;
    --paper: #f6f1e3;
    --paper-line: #e2d9c2;
    --ink: #1c1f2e;
    --ink-soft: #4a4f66;
    --gold: #cf9a44;
    --gold-soft: #e7c581;
    --ok: #3f7a54;
    --err: #b5484c;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --paper: #1c1f30; --paper-line: #33384f;
      --ink: #ece8da; --ink-soft: #a8adc4;
      --gold: #e7c581; --gold-soft: #cf9a44;
    }
  }
  :root[data-theme="dark"] {
    --paper: #1c1f30; --paper-line: #33384f;
    --ink: #ece8da; --ink-soft: #a8adc4;
    --gold: #e7c581; --gold-soft: #cf9a44;
  }
  :root[data-theme="light"] {
    --paper: #f6f1e3; --paper-line: #e2d9c2;
    --ink: #1c1f2e; --ink-soft: #4a4f66;
    --gold: #cf9a44; --gold-soft: #e7c581;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--navy-deep); min-height: 100vh;
    display: flex; flex-direction: column; align-items: center;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    color: var(--ink);
  }
  .masthead {
    width: 100%; background: linear-gradient(180deg, var(--navy) 0%, var(--navy-deep) 100%);
    padding: 56px 24px 40px; text-align: center;
  }
  .masthead h1 {
    font-family: Georgia, "Times New Roman", serif; font-weight: 700;
    font-size: clamp(40px, 8vw, 64px); letter-spacing: 0.02em;
    color: #f4efe0; margin: 0; text-wrap: balance;
  }
  .masthead .rule { width: 64px; height: 2px; background: var(--gold); margin: 18px auto; border: none; }
  .masthead .tagline {
    font-family: ui-monospace, "SF Mono", Consolas, monospace; font-size: 12px;
    letter-spacing: 0.22em; text-transform: uppercase; color: var(--gold-soft);
  }
  main {
    width: 100%; max-width: 480px; margin: -28px 20px 60px;
    background: var(--paper); border: 1px solid var(--paper-line);
    border-radius: 4px; padding: 36px 32px 32px;
    box-shadow: 0 20px 50px -20px rgba(0,0,0,0.5);
  }
  .eyebrow {
    font-family: ui-monospace, "SF Mono", Consolas, monospace; font-size: 11px;
    letter-spacing: 0.18em; text-transform: uppercase; color: var(--gold); margin: 0 0 10px;
  }
  main h2 { font-family: Georgia, "Times New Roman", serif; font-size: 24px; line-height: 1.3; margin: 0 0 8px; text-wrap: balance; }
  main p.lede { font-size: 15px; line-height: 1.55; color: var(--ink-soft); margin: 0 0 26px; }
  form { display: flex; flex-direction: column; gap: 12px; }
  label { font-size: 12px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--ink-soft); }
  input[type="email"] {
    font-size: 16px; padding: 12px 14px; border: 1px solid var(--paper-line);
    border-radius: 3px; background: transparent; color: var(--ink); font-family: inherit;
  }
  input[type="email"]:focus { outline: 2px solid var(--gold); outline-offset: 1px; }
  button {
    font-size: 15px; font-weight: 600; padding: 13px 18px; border: none; border-radius: 3px;
    background: var(--gold); color: var(--navy-deep); cursor: pointer; font-family: inherit;
    transition: filter 0.15s ease;
  }
  button:hover { filter: brightness(1.08); }
  button:disabled { cursor: default; filter: brightness(0.85); }
  button:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }
  #result { min-height: 20px; font-size: 13px; margin: 2px 0 0; }
  #result.ok { color: var(--ok); }
  #result.err { color: var(--err); }
  .fineprint {
    margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--paper-line);
    font-size: 12px; color: var(--ink-soft); line-height: 1.6;
  }
</style>
</head>
<body>
<div class="masthead">
  <h1>THE AI 7</h1>
  <hr class="rule">
  <div class="tagline">Your weekly AI intelligence brief</div>
</div>
<main>
  <p class="eyebrow">Free &middot; Weekly &middot; No spam</p>
  <h2>Get next week's issue in your inbox</h2>
  <p class="lede">Research papers, model releases, GitHub trends, and framework
    updates &mdash; reviewed by an editor before every issue ships.</p>
  <form id="subscribe-form">
    <label for="email">Email address</label>
    <input id="email" type="email" placeholder="you@example.com" required autocomplete="email">
    <button type="submit" id="submit-btn">Subscribe</button>
    <p id="result"></p>
  </form>
  <div class="fineprint">Unsubscribe anytime with the link at the bottom of every issue.</div>
</main>
<script>
  document.getElementById("subscribe-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    var email = document.getElementById("email").value;
    var result = document.getElementById("result");
    var btn = document.getElementById("submit-btn");
    btn.disabled = true;
    btn.textContent = "Subscribing\\u2026";
    try {
      var response = await fetch("/subscribe", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({email: email}),
      });
      var data = await response.json();
      if (response.ok) {
        result.className = "ok";
        result.textContent = "Subscribed! Check your inbox for future issues.";
      } else {
        result.className = "err";
        result.textContent = (data.detail && data.detail[0] && data.detail[0].msg)
          || "Please enter a valid email address.";
      }
    } catch (err) {
      result.className = "err";
      result.textContent = "Something went wrong \\u2014 please try again.";
    } finally {
      btn.disabled = false;
      btn.textContent = "Subscribe";
    }
  });
</script>
</body>
</html>"""


@router.get("/subscribe")
def subscribe_page() -> HTMLResponse:
    """Signup form matching the newsletter's own masthead branding."""
    return HTMLResponse(_SUBSCRIBE_PAGE)


@router.post("/subscribe", response_model=SubscribeResponse)
def subscribe(request: SubscribeRequest) -> SubscribeResponse:
    record = add_subscriber(request.email)
    return SubscribeResponse(email=record.email, status=record.status)


@router.get("/unsubscribe/confirm")
def unsubscribe_confirm(token: str) -> HTMLResponse:
    try:
        email = verify_unsubscribe_token(token)
    except TokenError as exc:
        return _page("Link error", f"<p>{exc}</p>")

    body = (
        f"<h2>Unsubscribe {email}?</h2>"
        f"<form method='post' action='/unsubscribe'>"
        f"<input type='hidden' name='token' value='{token}'>"
        f"<button type='submit'>Confirm Unsubscribe</button></form>"
    )
    return _page("Confirm unsubscribe", body)


@router.post("/unsubscribe")
def unsubscribe(token: str = Form(...)) -> HTMLResponse:
    try:
        email = verify_unsubscribe_token(token)
    except TokenError as exc:
        return _page("Link error", f"<p>{exc}</p>")

    remove_subscriber(email)
    return _page("Unsubscribed", f"<p>{email} has been unsubscribed.</p>")
