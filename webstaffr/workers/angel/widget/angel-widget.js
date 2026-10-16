/**
 * angel-widget.js -- embeddable chat widget for Angel.
 *
 * Minimal, dependency-free vanilla JS. Embed on a generated customer site
 * with:
 *
 *   <script src="https://YOUR_HOST/static/angel-widget.js"
 *           data-tenant-id="TENANT_ID"
 *           data-api-base="https://YOUR_HOST"
 *           data-brand-color="#HEX_COLOR"></script>
 *
 * Optional: data-brand-color defaults to #2a6df5 if not provided.
 *
 * Features:
 * - Responsive design: adapts to mobile (<600px) and desktop
 * - Dynamic theming: brand color drives button and message bubbles
 * - Accessible: ARIA roles, keyboard navigation (Esc to close)
 * - Chat-only: voice calls handled by Retell phone integration, not widget
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
    var brandColor = script.getAttribute("data-brand-color") || "#2a6df5";
    if (!tenantId || !apiBase) {
      console.error("[angel-widget] data-tenant-id and data-api-base are required.");
      return;
    }

    var state = { open: false, sending: false };
    var isMobile = window.innerWidth < 600;

    var root = document.createElement("div");
    root.id = "angel-widget-root";
    var panelWidth = isMobile ? "calc(100vw - 20px)" : "380px";
    root.innerHTML =
      '<button id="angel-widget-toggle" aria-label="Open chat with Angel" ' +
      'style="position:fixed;bottom:20px;right:20px;width:56px;height:56px;' +
      'border-radius:50%;border:none;background:' + brandColor + ';color:#fff;font-size:22px;' +
      'cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.25);z-index:999999;">&#128172;</button>' +
      '<div id="angel-widget-panel" role="dialog" aria-labelledby="angel-widget-title" style="display:none;position:fixed;bottom:88px;right:20px;' +
      "width:" + panelWidth + ";max-height:440px;background:#fff;border-radius:12px;" +
      'box-shadow:0 4px 20px rgba(0,0,0,.2);flex-direction:column;overflow:hidden;z-index:999999;font-family:sans-serif;">' +
      '<div style="padding:12px 14px;background:' + brandColor + ';color:#fff;display:flex;justify-content:space-between;align-items:center;">' +
      '<strong id="angel-widget-title">Angel</strong>' +
      '</div>' +
      '<div id="angel-widget-messages" style="flex:1;overflow-y:auto;padding:10px;font-size:14px;line-height:1.4;"></div>' +
      '<form id="angel-widget-form" style="display:flex;border-top:1px solid #eee;">' +
      '<input id="angel-widget-input" type="text" placeholder="Type a message..." autocomplete="off" aria-label="Message" ' +
      'style="flex:1;border:none;padding:10px;font-size:14px;outline:none;" />' +
      '<button type="submit" style="border:none;background:' + brandColor + ';color:#fff;padding:0 14px;cursor:pointer;" aria-label="Send message">Send</button>' +
      "</form>" +
      "</div>";
    document.body.appendChild(root);

    var panel = root.querySelector("#angel-widget-panel");
    var toggle = root.querySelector("#angel-widget-toggle");
    var messages = root.querySelector("#angel-widget-messages");
    var form = root.querySelector("#angel-widget-form");
    var input = root.querySelector("#angel-widget-input");

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
      bubble.style.background = from === "user" ? brandColor : "#f0f1f3";
      bubble.style.color = from === "user" ? "#fff" : "#111";
      el.appendChild(bubble);
      messages.appendChild(el);
      messages.scrollTop = messages.scrollHeight;
    }

    function closePanel() {
      state.open = false;
      panel.style.display = "none";
    }

    toggle.addEventListener("click", function () {
      state.open = !state.open;
      panel.style.display = state.open ? "flex" : "none";
      if (state.open && messages.children.length === 0) {
        appendMessage("Hi! I'm Angel. How can I help today?", "angel");
      }
      if (state.open) {
        input.focus();
      }
    });

    document.addEventListener("keydown", function (evt) {
      if (evt.key === "Escape" && state.open) {
        closePanel();
      }
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
