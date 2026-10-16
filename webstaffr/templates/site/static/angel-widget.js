/**
 * angel-widget.js -- embeddable chat widget for Angel.
 *
 * Minimal, dependency-free vanilla JS. Embed on a generated customer site
 * with:
 *
 *   <script src="https://YOUR_HOST/static/angel-widget.js"
 *           data-tenant-id="TENANT_ID"
 *           data-api-base="https://YOUR_HOST"></script>
 *
 * Voice is intentionally NOT implemented here yet -- the backend's
 * GrokVoiceBackend is a credential-checked stub, not a working realtime
 * voice integration (see webstaffr/workers/angel/voice.py). The voice
 * button below is present as a UI placeholder that clearly tells the
 * visitor voice isn't available yet, rather than silently doing nothing
 * or pretending to listen.
 */
(function () {
  "use strict";

  function currentScript() {
    return document.currentScript || document.querySelector("script[data-tenant-id]");
  }

  function init() {
    var script = currentScript();
    if (!script) {
      console.error("[angel-widget] could not find its own <script> tag; aborting.");
      return;
    }

    var tenantId = script.getAttribute("data-tenant-id");
    var apiBase = script.getAttribute("data-api-base");
    if (!tenantId || !apiBase) {
      console.error("[angel-widget] data-tenant-id and data-api-base are required.");
      return;
    }

    var state = { open: false, sending: false };

    var root = document.createElement("div");
    root.id = "angel-widget-root";
    root.innerHTML =
      '<button id="angel-widget-toggle" aria-label="Chat with us" ' +
      'style="position:fixed;bottom:20px;right:20px;width:56px;height:56px;' +
      'border-radius:50%;border:1px solid rgba(255,255,255,0.55);' +
      'background:rgba(42,109,245,0.55);' +
      'backdrop-filter:blur(12px) saturate(160%);-webkit-backdrop-filter:blur(12px) saturate(160%);' +
      'color:#fff;font-size:22px;' +
      'cursor:pointer;box-shadow:0 6px 20px rgba(31,38,135,0.30);z-index:999999;\">&#128172;</button>' +
      '<div id="angel-widget-panel" style="display:none;position:fixed;bottom:88px;right:20px;' +
      "width:330px;max-height:460px;" +
      'background:rgba(255,255,255,0.62);' +
      'backdrop-filter:blur(20px) saturate(160%);-webkit-backdrop-filter:blur(20px) saturate(160%);' +
      'border:1px solid rgba(255,255,255,0.55);border-radius:20px;' +
      'box-shadow:0 8px 32px rgba(31,38,135,0.22);' +
      'flex-direction:column;overflow:hidden;z-index:999999;font-family:sans-serif;\">' +
      '<div style=\"padding:12px 14px;background:rgba(42,109,245,0.82);color:#fff;' +
      'display:flex;justify-content:space-between;align-items:center;\">' +
      "<strong>Angel</strong>" +
      '<button id="angel-widget-voice" title="Voice (not available yet)" ' +
      'style="background:none;border:none;color:#fff;opacity:.6;cursor:not-allowed;font-size:16px;\">&#127908;</button>' +
      "</div>" +
      '<div id="angel-widget-messages" style="flex:1;overflow-y:auto;padding:10px;font-size:14px;line-height:1.4;background:transparent;"></div>' +
      '<form id="angel-widget-form" style=\"display:flex;border-top:1px solid rgba(255,255,255,0.5);' +
      'background:rgba(255,255,255,0.35);\">' +
      '<input id="angel-widget-input" type="text" placeholder="Type a message..." autocomplete="off" ' +
      'style="flex:1;border:none;padding:10px;font-size:14px;outline:none;' +
      'color:#111;background:rgba(255,255,255,0.7);" />' +
      '<button type="submit" style="border:none;background:rgba(42,109,245,0.85);' +
      'color:#fff;padding:0 14px;cursor:pointer;\">Send</button>' +
      "</form>" +
      "</div>";
    document.body.appendChild(root);

    var panel = root.querySelector("#angel-widget-panel");
    var toggle = root.querySelector("#angel-widget-toggle");
    var messages = root.querySelector("#angel-widget-messages");
    var form = root.querySelector("#angel-widget-form");
    var input = root.querySelector("#angel-widget-input");
    var voiceBtn = root.querySelector("#angel-widget-voice");

    function appendMessage(text, from) {
      var el = document.createElement("div");
      el.style.margin = "6px 0";
      el.style.textAlign = from === "user" ? "right" : "left";
      var bubble = document.createElement("span");
      bubble.textContent = text;
      bubble.style.display = "inline-block";
      bubble.style.padding = "8px 12px";
      bubble.style.borderRadius = "14px";
      bubble.style.maxWidth = "80%";
      if (from === "user") {
        bubble.style.background = "rgba(42,109,245,0.92)";
        bubble.style.color = "#fff";
      } else {
        bubble.style.background = "rgba(255,255,255,0.7)";
        bubble.style.color = "#111";
        bubble.style.border = "1px solid rgba(255,255,255,0.6)";
      }
      el.appendChild(bubble);
      messages.appendChild(el);
      messages.scrollTop = messages.scrollHeight;
    }

    toggle.addEventListener("click", function () {
      state.open = !state.open;
      panel.style.display = state.open ? "flex" : "none";
      if (state.open && messages.children.length === 0) {
        appendMessage("Hi! I'm Angel. How can I help today?", "angel");
      }
    });

    voiceBtn.addEventListener("click", function () {
      appendMessage(
        "Voice chat isn't turned on for this site yet -- type a message instead and I'll help.",
        "angel"
      );
    });

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();
      var text = input.value.trim();
      if (!text || state.sending) return;

      appendMessage(text, "user");
      input.value = "";
      state.sending = true;

      fetch(apiBase.replace(/\/$/, "") + "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, message: text }),
      })
        .then(function (resp) {
          if (!resp.ok) {
            throw new Error("Angel backend returned " + resp.status);
          }
          return resp.json();
        })
        .then(function (data) {
          appendMessage(data.reply, "angel");
        })
        .catch(function (err) {
          console.error("[angel-widget] chat request failed:", err);
          appendMessage("Sorry, I'm having trouble connecting right now. Please try again shortly.", "angel");
        })
        .finally(function () {
          state.sending = false;
        });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
