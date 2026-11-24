/**
 * FinSight AI - Authentication Client Script
 * Handles Login, Register, accessibility, password strength & validation.
 */
"use strict";

const API_BASE = (window.location.protocol === "file:") ? "http://127.0.0.1:8000" : "";

const SVG_ICONS = {
  eye: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>`,
  eyeOff: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"></path><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"></path><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"></path><line x1="2" y1="2" x2="22" y2="22"></line></svg>`,
  circle: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle></svg>`,
  checkCircle: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="m9 12 2 2 4-4"></path></svg>`,
  alertCircle: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
  checkSuccess: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
  alertTriangle: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`
};

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }

  initPasswordToggles();
  initCapsLockDetection();
  initPreFilledData();

  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");

  if (loginForm) {
    initLoginForm(loginForm);
  }

  if (registerForm) {
    initRegisterForm(registerForm);
  }
});

/**
 * Password Visibility Toggles (Eye button)
 */
function initPasswordToggles() {
  setupToggle("password", "togglePasswordBtn", "togglePasswordIcon");
  setupToggle("confirmPassword", "toggleConfirmPasswordBtn", "toggleConfirmPasswordIcon");
}

function setupToggle(inputId, buttonId, iconId) {
  const input = document.getElementById(inputId);
  const btn = document.getElementById(buttonId);

  if (!input || !btn) return;

  btn.addEventListener("click", () => {
    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";
    btn.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");

    btn.innerHTML = isPassword ? SVG_ICONS.eyeOff : SVG_ICONS.eye;
    input.focus();
  });
}

/**
 * Caps Lock Warning Detection
 */
function initCapsLockDetection() {
  setupCapsWarning("password", "capsWarning");
  setupCapsWarning("confirmPassword", "confirmCapsWarning");
}

function setupCapsWarning(inputId, warningId) {
  const input = document.getElementById(inputId);
  const warning = document.getElementById(warningId);

  if (!input || !warning) return;

  const updateCapsState = (e) => {
    if (e.getModifierState && typeof e.getModifierState === "function") {
      const isCaps = e.getModifierState("CapsLock");
      warning.classList.toggle("show", isCaps);
    }
  };

  input.addEventListener("keydown", updateCapsState);
  input.addEventListener("keyup", updateCapsState);
  input.addEventListener("blur", () => {
    warning.classList.remove("show");
  });
}

/**
 * Read one-time sessionStorage values for login pre-fill and success banners
 */
function initPreFilledData() {
  const identifierInput = document.getElementById("identifier");
  const passwordInput = document.getElementById("password");

  // Read one-time registration success message
  const successBanner = sessionStorage.getItem("auth_success_banner");
  if (successBanner) {
    sessionStorage.removeItem("auth_success_banner");
    showAlert(successBanner, "success");
  }

  // Read one-time prefill identifier (email)
  const prefill = sessionStorage.getItem("auth_prefill_identifier");
  if (prefill && identifierInput) {
    sessionStorage.removeItem("auth_prefill_identifier");
    identifierInput.value = prefill;
    if (passwordInput) {
      setTimeout(() => passwordInput.focus(), 50);
    }
  }
}

/**
 * Global Alert Banner Display
 */
function showAlert(message, type = "error") {
  const banner = document.getElementById("alertBanner");
  const messageSpan = document.getElementById("alertMessage");

  if (!banner || !messageSpan) return;

  banner.className = `alert-banner show alert-${type}`;
  messageSpan.innerHTML = message;

  const iconSvg = type === "success" ? SVG_ICONS.checkSuccess : type === "warning" ? SVG_ICONS.alertTriangle : SVG_ICONS.alertCircle;
  const existingIcon = banner.querySelector("svg");
  if (existingIcon) {
    existingIcon.outerHTML = iconSvg;
  }

  banner.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function hideAlert() {
  const banner = document.getElementById("alertBanner");
  if (banner) {
    banner.className = "alert-banner";
  }
}

/**
 * Field Error Display & Wrapper Highlight
 */
function setFieldError(fieldId, errorMsg) {
  const input = document.getElementById(fieldId);
  const wrapper = document.getElementById(`${fieldId}Wrapper`);
  const errorDiv = document.getElementById(`${fieldId}Error`);

  if (wrapper) wrapper.classList.add("has-error");
  if (errorDiv) {
    errorDiv.textContent = errorMsg;
    errorDiv.classList.add("show");
  }
  if (input) {
    input.setAttribute("aria-invalid", "true");
  }
}

function clearFieldErrors() {
  document.querySelectorAll(".input-wrapper").forEach((el) => el.classList.remove("has-error"));
  document.querySelectorAll(".field-error").forEach((el) => {
    el.textContent = "";
    el.classList.remove("show");
  });
  document.querySelectorAll(".form-input").forEach((el) => {
    el.removeAttribute("aria-invalid");
  });
}

/**
 * Login Form Handling
 */
function initLoginForm(form) {
  const identifierInput = document.getElementById("identifier");
  const passwordInput = document.getElementById("password");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors();
    hideAlert();

    const identifier = (identifierInput.value || "").trim();
    const password = passwordInput.value || "";
    let firstInvalid = null;

    if (!identifier) {
      setFieldError("identifier", "Please enter your email address.");
      firstInvalid = firstInvalid || identifierInput;
    }

    if (!password) {
      setFieldError("password", "Please enter your password.");
      firstInvalid = firstInvalid || passwordInput;
    }

    if (firstInvalid) {
      firstInvalid.focus();
      return;
    }

    setLoading(true);

    try {
      const rememberMe = document.getElementById("rememberMe")?.checked || false;
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          identifier,
          password,
          remember_me: rememberMe,
        }),
      });

      const data = await response.json();

      if (response.ok && data.success !== false) {
        const urlParams = new URLSearchParams(window.location.search);
        let next = urlParams.get("next") || "/dashboard";
        if (!next.startsWith("/") || next.startsWith("//") || next.includes("\\")) {
          next = "/dashboard";
        }
        window.location.href = next;
      } else {
        const error = data.error || {};
        if (response.status === 404 || error.code === "USER_NOT_FOUND") {
          const registerUrl = `/register?email=${encodeURIComponent(identifier)}`;
          showAlert(
            `We couldn't find an account with this email/username. New here? ` +
            `<a href="${registerUrl}" class="alert-link" style="font-weight:700; text-decoration:underline;">Please sign up first.</a>`,
            "error"
          );
          identifierInput.focus();
        } else if (response.status === 429 || error.code === "ACCOUNT_LOCKED") {
          showAlert(error.message || "Account is locked due to too many failed attempts. Please retry later.", "warning");
        } else if (error.field) {
          setFieldError(error.field, error.message || "Invalid input.");
          const el = document.getElementById(error.field);
          if (el) el.focus();
        } else {
          showAlert(error.message || data.detail || "Incorrect password. Please try again.", "error");
          passwordInput.focus();
        }
      }
    } catch (err) {
      showAlert(`Unable to connect to backend server (${API_BASE || 'local'}). Please ensure the backend is running.`, "error");
    } finally {
      setLoading(false);
    }
  });
}

/**
 * Register Form Handling & Password Strength
 */
function initRegisterForm(form) {
  const usernameInput = document.getElementById("username");
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const confirmPasswordInput = document.getElementById("confirmPassword");
  const pwdStrengthContainer = document.getElementById("pwdStrengthContainer");

  const urlParams = new URLSearchParams(window.location.search);
  const emailParam = urlParams.get("email");
  if (emailParam && emailInput) {
    emailInput.value = emailParam;
  }

  if (passwordInput && pwdStrengthContainer) {
    passwordInput.addEventListener("input", () => {
      const val = passwordInput.value;
      if (!val) {
        pwdStrengthContainer.classList.remove("show");
        return;
      }
      pwdStrengthContainer.classList.add("show");
      updatePasswordMetrics(val);
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors();
    hideAlert();

    const username = (usernameInput.value || "").trim();
    const email = (emailInput.value || "").trim().toLowerCase();
    const password = passwordInput.value || "";
    const confirmPassword = confirmPasswordInput.value || "";

    let firstInvalid = null;

    const usernameRegex = /^[a-zA-Z][a-zA-Z0-9_.]*$/;
    if (!username) {
      setFieldError("username", "Username is required.");
      firstInvalid = firstInvalid || usernameInput;
    } else if (username.length < 3 || username.length > 20) {
      setFieldError("username", "Username must be between 3 and 20 characters.");
      firstInvalid = firstInvalid || usernameInput;
    } else if (!usernameRegex.test(username) || username.endsWith(".") || username.endsWith("_") || username.includes("..") || username.includes("__")) {
      setFieldError("username", "Username must start with a letter and contain only letters, numbers, dot, or underscore.");
      firstInvalid = firstInvalid || usernameInput;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email) {
      setFieldError("email", "Email address is required.");
      firstInvalid = firstInvalid || emailInput;
    } else if (!emailRegex.test(email)) {
      setFieldError("email", "Please enter a valid email address.");
      firstInvalid = firstInvalid || emailInput;
    }

    const metrics = evaluatePassword(password);
    if (!password) {
      setFieldError("password", "Password is required.");
      firstInvalid = firstInvalid || passwordInput;
    } else if (metrics.score < 5) {
      setFieldError("password", "Password does not meet all security requirements.");
      firstInvalid = firstInvalid || passwordInput;
    }

    if (!confirmPassword) {
      setFieldError("confirmPassword", "Please confirm your password.");
      firstInvalid = firstInvalid || confirmPasswordInput;
    } else if (confirmPassword !== password) {
      setFieldError("confirmPassword", "Passwords do not match.");
      firstInvalid = firstInvalid || confirmPasswordInput;
    }

    if (firstInvalid) {
      firstInvalid.focus();
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/auth/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({
          username,
          email,
          password,
          confirm_password: confirmPassword,
        }),
      });

      const data = await response.json();

      if (response.status === 201 || (response.ok && data.success !== false)) {
        sessionStorage.setItem("auth_prefill_identifier", email);
        sessionStorage.setItem("auth_success_banner", "Account created successfully. Please sign in.");
        window.location.href = "/login";
      } else {
        const error = data.error || {};
        if (error.field) {
          setFieldError(error.field, error.message || "Invalid input.");
          const el = document.getElementById(error.field);
          if (el) el.focus();
        } else {
          showAlert(error.message || data.detail || "Unable to complete registration. Please check your details.", "error");
        }
      }
    } catch (err) {
      showAlert(`Unable to connect to backend server (${API_BASE || 'local'}). Please ensure the backend is running.`, "error");
    } finally {
      setLoading(false);
    }
  });
}

/**
 * Evaluate Password Rules
 */
function evaluatePassword(pwd) {
  const hasLength = pwd.length >= 8 && pwd.length <= 64;
  const hasUpper = /[A-Z]/.test(pwd);
  const hasLower = /[a-z]/.test(pwd);
  const hasNumber = /[0-9]/.test(pwd);
  const hasSpecial = /[^a-zA-Z0-9]/.test(pwd);

  const checks = [hasLength, hasUpper, hasLower, hasNumber, hasSpecial];
  const score = checks.filter(Boolean).length;

  return { hasLength, hasUpper, hasLower, hasNumber, hasSpecial, score };
}

function updatePasswordMetrics(pwd) {
  const metrics = evaluatePassword(pwd);

  updateChecklistItem("ruleLength", metrics.hasLength);
  updateChecklistItem("ruleUpper", metrics.hasUpper);
  updateChecklistItem("ruleLower", metrics.hasLower);
  updateChecklistItem("ruleNumber", metrics.hasNumber);
  updateChecklistItem("ruleSpecial", metrics.hasSpecial);

  const seg1 = document.getElementById("strengthSeg1");
  const seg2 = document.getElementById("strengthSeg2");
  const seg3 = document.getElementById("strengthSeg3");
  const seg4 = document.getElementById("strengthSeg4");
  const label = document.getElementById("strengthLabel");

  if (!seg1 || !seg2 || !seg3 || !seg4 || !label) return;

  [seg1, seg2, seg3, seg4].forEach((seg) => {
    seg.style.backgroundColor = "#E2E8F0";
  });

  if (metrics.score === 0) {
    label.textContent = "Strength: None";
    label.style.color = "#64748B";
  } else if (metrics.score <= 2) {
    seg1.style.backgroundColor = "#EF4444";
    label.textContent = "Strength: Weak";
    label.style.color = "#EF4444";
  } else if (metrics.score === 3) {
    seg1.style.backgroundColor = "#F59E0B";
    seg2.style.backgroundColor = "#F59E0B";
    label.textContent = "Strength: Fair";
    label.style.color = "#F59E0B";
  } else if (metrics.score === 4) {
    seg1.style.backgroundColor = "#0B63CE";
    seg2.style.backgroundColor = "#0B63CE";
    seg3.style.backgroundColor = "#0B63CE";
    label.textContent = "Strength: Good";
    label.style.color = "#0B63CE";
  } else {
    seg1.style.backgroundColor = "#10B981";
    seg2.style.backgroundColor = "#10B981";
    seg3.style.backgroundColor = "#10B981";
    seg4.style.backgroundColor = "#10B981";
    label.textContent = "Strength: Strong";
    label.style.color = "#10B981";
  }
}

function updateChecklistItem(elementId, isMet) {
  const el = document.getElementById(elementId);
  if (!el) return;

  el.classList.toggle("met", isMet);
  const icon = el.querySelector("svg");
  if (icon) {
    icon.outerHTML = isMet ? SVG_ICONS.checkCircle : SVG_ICONS.circle;
  }
}

/**
 * Submit Button Loading State Helper
 */
function setLoading(isLoading) {
  const submitBtn = document.getElementById("submitBtn");
  if (!submitBtn) return;

  submitBtn.disabled = isLoading;
  submitBtn.classList.toggle("loading", isLoading);
  submitBtn.setAttribute("aria-busy", isLoading ? "true" : "false");
}
