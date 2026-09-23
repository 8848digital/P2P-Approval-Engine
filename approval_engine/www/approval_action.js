// Copyright (c) 2026 8848 Digital LLP. All rights reserved.
// Proprietary and confidential. Unauthorized copying, distribution, or use
// of this file, via any medium, is strictly prohibited without prior
// written permission from 8848 Digital LLP.

// Guest approval page (/approval_action): choose an action -> email an OTP -> confirm.
// Talks to approval_engine.approval_core.api.v1.email_action (POST only). Responses use
// the 8848 envelope {status, status_code, message, data, errors}, read with fetch so
// 4xx bodies (wrong code, expired link) reach the page intact.

(function () {
	const API = "/api/method/approval_engine.approval_core.api.v1.email_action.";
	const RESEND_COOLDOWN_SECONDS = 60;

	const root = document.getElementById("approval-action");
	if (!root) {
		return;
	}

	// Nothing to wire up when this approver has no available actions (see template).
	if (!root.querySelector("[data-role=send-otp]")) {
		return;
	}

	const token = root.dataset.token;
	const reasonRequired = (root.dataset.reasonRequired || "").split(",").filter(Boolean);
	const el = {
		actions: root.querySelectorAll(".aa-action"),
		remarks: root.querySelector("[name=remarks]"),
		remarksLabel: root.querySelector(".aa-field .aa-label"),
		otp: root.querySelector("[name=otp]"),
		sendOtp: root.querySelector("[data-role=send-otp]"),
		confirm: root.querySelector("[data-role=confirm]"),
		resend: root.querySelector("[data-role=resend]"),
		back: root.querySelector("[data-role=back]"),
		otpHint: root.querySelector("[data-role=otp-hint]"),
		doneMessage: root.querySelector("[data-role=done-message]"),
		state: root.querySelector("[data-role=state]"),
		error: root.querySelector("[data-role=error]"),
	};
	// Busy and cooldown states rewrite button labels, so keep each original to restore it.
	[el.sendOtp, el.resend, el.confirm].forEach((button) => {
		button.dataset.label = button.textContent;
	});
	const state = { action: null, busy: false };

	/**
	 * POST to one of the email_action endpoints and return the parsed envelope.
	 *
	 * @param {string} method - Endpoint name, e.g. "request_otp".
	 * @param {object} body - Request arguments; the link token is added automatically.
	 * @returns {Promise<object>} The response envelope.
	 */
	async function post(method, body) {
		const response = await fetch(API + method, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-Frappe-CSRF-Token": window.frappe?.csrf_token || "",
			},
			body: JSON.stringify({ token, ...body }),
		});
		try {
			return await response.json();
		} catch (parseError) {
			return { status: false, message: __("Something went wrong. Please try again.") };
		}
	}

	/**
	 * Disable a button and show progress while its request is in flight, so a second
	 * click can't be attempted and the page visibly acknowledges the first one.
	 *
	 * @param {HTMLElement} button - The button that was clicked.
	 * @param {string} busyLabel - Label to show while busy.
	 * @param {boolean} busy - True on start, false once the request settles.
	 * @returns {void}
	 */
	function setBusy(button, busyLabel, busy) {
		state.busy = busy;
		button.disabled = busy;
		button.textContent = busy ? busyLabel : button.dataset.label;
	}

	/**
	 * Show one step of the flow and hide the others.
	 *
	 * @param {string} name - "choose", "verify" or "done".
	 * @returns {void}
	 */
	function showStep(name) {
		root.querySelectorAll(".aa-step").forEach((step) => {
			step.hidden = step.dataset.step !== name;
		});
	}

	/**
	 * Show or clear the inline error message.
	 *
	 * @param {string} [message] - Text to show; empty clears it.
	 * @returns {void}
	 */
	function showError(message) {
		el.error.textContent = message || "";
		el.error.hidden = !message;
	}

	/**
	 * Whether the chosen action needs a reason, and whether one has been typed.
	 *
	 * @returns {boolean} True when the form is complete enough to request a code.
	 */
	function canRequestOtp() {
		if (!state.action) {
			return false;
		}
		return !reasonRequired.includes(state.action) || el.remarks.value.trim().length > 0;
	}

	/**
	 * Mark `button` as the selected action and relabel the remarks field accordingly.
	 *
	 * @param {HTMLElement} button - The clicked action button.
	 * @returns {void}
	 */
	function selectAction(button) {
		state.action = button.dataset.action;
		el.actions.forEach((other) =>
			other.setAttribute("aria-checked", String(other === button))
		);

		const required = reasonRequired.includes(state.action);
		el.remarksLabel.textContent = required
			? el.remarksLabel.dataset.labelRequired
			: el.remarksLabel.dataset.labelOptional;
		el.remarks.required = required;
		el.sendOtp.disabled = !canRequestOtp();
		showError("");
	}

	/**
	 * Disable a resend button for the server-side cooldown, with a visible countdown.
	 *
	 * @returns {void}
	 */
	function startResendCooldown() {
		const label = el.resend.dataset.label;
		let remaining = RESEND_COOLDOWN_SECONDS;
		el.resend.disabled = true;
		const timer = setInterval(() => {
			remaining -= 1;
			el.resend.textContent = `${label} (${remaining}s)`;
			if (remaining <= 0) {
				clearInterval(timer);
				el.resend.textContent = label;
				el.resend.disabled = false;
			}
		}, 1000);
	}

	/**
	 * Ask the server to email a verification code for the chosen action.
	 *
	 * @param {HTMLElement} trigger - The button clicked ("Send verification code" or "Resend code").
	 * @returns {Promise<void>}
	 */
	async function requestOtp(trigger) {
		if (state.busy || !canRequestOtp()) {
			return;
		}
		showError("");
		setBusy(trigger, __("Sending…"), true);
		const result = await post("request_otp", { action: state.action });
		setBusy(trigger, "", false);

		if (!result.status) {
			showError(result.message);
			return;
		}
		el.otpHint.textContent = __(
			"We sent a 6-digit code to {0}. It is valid for {1} minutes.",
			[result.data.sent_to, result.data.validity_minutes]
		);
		showStep("verify");
		startResendCooldown();
		el.otp.value = "";
		el.otp.focus();
	}

	/**
	 * Submit the action with the typed code and remarks.
	 *
	 * @returns {Promise<void>}
	 */
	async function confirmAction() {
		if (state.busy) {
			return;
		}
		const otp = el.otp.value.trim();
		if (!/^\d{6}$/.test(otp)) {
			showError(__("Enter the 6-digit code from the email."));
			return;
		}
		showError("");
		setBusy(el.confirm, __("Confirming…"), true);
		const result = await post("submit_action", {
			action: state.action,
			otp,
			remarks: el.remarks.value,
		});
		setBusy(el.confirm, "", false);

		if (!result.status) {
			showError(result.message);
			return;
		}
		el.state.textContent = result.data.workflow_state;
		el.doneMessage.textContent = __(
			"{0} recorded. The document is now {1}. You can close this page.",
			[__(state.action), result.data.workflow_state]
		);
		showStep("done");
	}

	el.actions.forEach((button) => button.addEventListener("click", () => selectAction(button)));
	el.remarks.addEventListener("input", () => {
		el.sendOtp.disabled = state.busy || !canRequestOtp();
	});
	el.sendOtp.addEventListener("click", () => requestOtp(el.sendOtp));
	el.resend.addEventListener("click", () => requestOtp(el.resend));
	el.confirm.addEventListener("click", confirmAction);
	el.otp.addEventListener("keydown", (event) => {
		if (event.key === "Enter") {
			confirmAction();
		}
	});
	el.back.addEventListener("click", () => {
		showError("");
		showStep("choose");
	});
})();
