// Minimal host bridge shared by every widget.
//
// Works in ChatGPT (window.openai) and in any host that speaks the MCP Apps
// postMessage protocol (ui/initialize -> ui/notifications/tool-result).
// Tool output is treated as untrusted: render it with textContent, never innerHTML.
(function () {
  "use strict";
  var listeners = [];
  var pending = {};
  var nextId = 1;
  var last = null;

  function emit(data) {
    if (!data) return;
    last = data;
    listeners.forEach(function (cb) {
      try { cb(data); } catch (e) { console.error(e); }
    });
  }

  function post(msg) {
    if (window.parent && window.parent !== window) window.parent.postMessage(msg, "*");
  }

  function request(method, params) {
    var id = nextId++;
    return new Promise(function (resolve, reject) {
      pending[id] = { resolve: resolve, reject: reject };
      post({ jsonrpc: "2.0", id: id, method: method, params: params || {} });
      setTimeout(function () {
        if (pending[id]) { delete pending[id]; reject(new Error("timeout: " + method)); }
      }, 30000);
    });
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") return;
    if (msg.id !== undefined && pending[msg.id] && (msg.result !== undefined || msg.error !== undefined)) {
      var p = pending[msg.id];
      delete pending[msg.id];
      if (msg.error) p.reject(new Error(msg.error.message || "error"));
      else p.resolve(msg.result);
      return;
    }
    if (msg.method === "ui/notifications/tool-result" && msg.params) {
      emit(msg.params.structuredContent);
    }
  }, { passive: true });

  window.addEventListener("openai:set_globals", function (event) {
    var g = event.detail && event.detail.globals;
    if (g && g.toolOutput) emit(g.toolOutput);
  }, { passive: true });

  // MCP Apps handshake. Harmless in hosts that do not need it.
  request("ui/initialize", {
    protocolVersion: "2026-01-26",
    clientInfo: { name: "plugkit-widget", version: "1.0.0" },
    appCapabilities: { availableDisplayModes: ["inline"] }
  }).then(function () {
    post({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} });
  }).catch(function () { /* host without the handshake, e.g. older ChatGPT */ });

  function reportSize() {
    var h = document.documentElement.scrollHeight;
    var w = document.documentElement.scrollWidth;
    post({ jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { width: w, height: h } });
  }
  if (window.ResizeObserver) new ResizeObserver(reportSize).observe(document.documentElement);

  window.plugkit = {
    onData: function (cb) {
      listeners.push(cb);
      if (last) cb(last);
      else if (window.openai && window.openai.toolOutput) emit(window.openai.toolOutput);
    },
    callTool: function (name, args) {
      if (window.openai && window.openai.callTool) {
        return window.openai.callTool(name, args || {}).then(function (r) {
          return (r && (r.structuredContent || r)) || null;
        });
      }
      return request("tools/call", { name: name, arguments: args || {} }).then(function (r) {
        return r && r.structuredContent;
      });
    },
    openLink: function (url) {
      if (!/^https:\/\//.test(url)) return;
      if (window.openai && window.openai.openExternal) return window.openai.openExternal({ href: url });
      return request("ui/open-link", { url: url });
    },
    followUp: function (prompt) {
      if (window.openai && window.openai.sendFollowUpMessage) return window.openai.sendFollowUpMessage({ prompt: prompt });
      return request("ui/message", { role: "user", content: [{ type: "text", text: prompt }] });
    },
    el: function (tag, attrs, children) {
      var node = document.createElement(tag);
      Object.keys(attrs || {}).forEach(function (k) {
        if (k === "text") node.textContent = attrs[k];
        else if (k === "class") node.className = attrs[k];
        else if (k.indexOf("on") === 0) node.addEventListener(k.slice(2), attrs[k]);
        else node.setAttribute(k, attrs[k]);
      });
      (children || []).forEach(function (c) {
        if (c === null || c === undefined) return;
        node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
      });
      return node;
    }
  };
})();
