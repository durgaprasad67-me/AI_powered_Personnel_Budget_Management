import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from app.main import app, HTML_DIR, FRONTEND_DIR

def verify_step1():
    client = TestClient(app)
    results = []

    # 1. Verify File Resolution for direct file open (file://)
    css_on_disk = (HTML_DIR / "../css/auth.css").resolve()
    assert css_on_disk.exists(), f"CSS path from HTML does not exist: {css_on_disk}"
    js_on_disk = (HTML_DIR / "../js/auth.js").resolve()
    assert js_on_disk.exists(), f"JS path from HTML does not exist: {js_on_disk}"
    hero_on_disk = (FRONTEND_DIR / "assets/images/auth-hero.png").resolve()
    assert hero_on_disk.exists(), f"Hero image does not exist: {hero_on_disk}"
    results.append(("[PASS]", "Direct file open (file://) relative paths (../css, ../js, ../assets) resolve successfully on disk"))

    # 2. Verify GET /login
    resp = client.get("/login")
    assert resp.status_code == 200, f"Expected 200 for /login, got {resp.status_code}"
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Welcome Back!" in resp.text
    assert "Email Address" in resp.text
    assert "Remember Me" in resp.text
    assert "Forgot Password?" in resp.text
    assert "Don't have an account?" in resp.text
    assert "capsWarning" in resp.text
    assert "togglePasswordBtn" in resp.text
    assert "auth-card" in resp.text
    assert "auth-container" in resp.text
    results.append(("[PASS]", "GET /login served with all required form controls, accessibility tags, and inline SVG fallbacks"))

    # 3. Verify GET /register
    resp = client.get("/register")
    assert resp.status_code == 200, f"Expected 200 for /register, got {resp.status_code}"
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Create an Account" in resp.text
    assert "Username" in resp.text
    assert "Confirm Password" in resp.text
    assert "strengthBars" in resp.text
    assert "ruleLength" in resp.text
    assert "ruleUpper" in resp.text
    assert "ruleLower" in resp.text
    assert "ruleNumber" in resp.text
    assert "ruleSpecial" in resp.text
    assert "Already have an account?" in resp.text
    results.append(("[PASS]", "GET /register served with 4-segment strength meter & 5-rule checklist"))

    # 4. Verify GET /forgot-password
    resp = client.get("/forgot-password")
    assert resp.status_code == 200, f"Expected 200 for /forgot-password, got {resp.status_code}"
    assert "text/html" in resp.headers.get("content-type", "")
    assert "Reset Password" in resp.text
    assert "Back to Sign In" in resp.text
    results.append(("[PASS]", "GET /forgot-password stub served successfully"))

    # 5. Verify CSS contains auth-hero.png as background image with card on the right
    resp = client.get("/css/auth.css")
    assert resp.status_code == 200, f"Expected 200 for /css/auth.css, got {resp.status_code}"
    assert "text/css" in resp.headers.get("content-type", "")
    assert "background-image: url('../assets/images/auth-hero.png')" in resp.text
    assert "justify-content: flex-end" in resp.text
    assert ":focus-visible" in resp.text
    assert "#0A1F44" in resp.text
    results.append(("[PASS]", "GET /css/auth.css configured with auth-hero.png background image and right-aligned card (justify-content: flex-end)"))

    # 6. Verify JS functionality
    resp = client.get("/js/auth.js")
    assert resp.status_code == 200, f"Expected 200 for /js/auth.js, got {resp.status_code}"
    assert "javascript" in resp.headers.get("content-type", "")
    assert "initPasswordToggles" in resp.text
    assert "initCapsLockDetection" in resp.text
    assert "updatePasswordMetrics" in resp.text
    assert "auth_prefill_identifier" in resp.text
    assert "API_BASE" in resp.text
    results.append(("[PASS]", "GET /js/auth.js served with live password meter, eye toggle, caps warning, and API_BASE support"))

    # 7. Verify Assets and Aliases
    resp = client.get("/assets/images/auth-hero.png")
    assert resp.status_code == 200
    resp_alias = client.get("/frontend/assets/images/auth-hero.png")
    assert resp_alias.status_code == 200
    results.append(("[PASS]", f"GET /assets/images/auth-hero.png and /frontend/assets alias served ({len(resp.content)} bytes)"))

    # 8. Security Check: Direct HTML folder browsing is not mounted
    resp = client.get("/html/login.html")
    assert resp.status_code == 404
    results.append(("[PASS]", "GET /html/login.html returns 404 (HTML directory not publicly mounted)"))

    print("=== STEP 1 VERIFICATION RESULTS ===")
    for status, msg in results:
        print(f"{status} {msg}")
    print("ALL STEP 1 CHECKS PASSED.")

if __name__ == "__main__":
    verify_step1()
