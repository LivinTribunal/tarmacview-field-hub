/* pilot 2 webview connect flow - dom-free so the node test driver can run it.
   attached to window.TarmacPilotConnect in the page, exported via module.exports
   for the test driver. all user-driven wiring (form, status panel) lives in
   index.html. */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module !== null && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.TarmacPilotConnect = api;
  }
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  var BROWSER_MODE_MESSAGE =
    "Open this page in DJI Pilot 2 (Cloud Service) to connect to the field hub.";

  // global function name pilot invokes with mqtt connection state changes
  var THING_CALLBACK_NAME = "thingConnectCallback";

  // pilot client flag in the login request
  var PILOT_LOGIN_FLAG = 2;

  // auto-upload originals (type 0, not thumbnails) incl. video, per the
  // media-return design in FIELD-HUB.md
  var MEDIA_PARAMS = { autoUploadPhoto: true, autoUploadPhotoType: 0, autoUploadVideo: true };

  // status panel steps, in flow order
  var STEP_LICENSE = "license";
  var STEP_LOGIN = "login";
  var STEP_API = "api";
  var STEP_MQTT = "mqtt";
  var STEP_MEDIA = "media";
  var STEP_MISSION = "mission";

  function parseBridgeReturn(raw) {
    // bridge returns are bool-ish or json {code, message, data} envelopes
    // (code 0 = ok, data sometimes a json-encoded string itself); void
    // returns carry no error signal and count as success
    if (raw === undefined || raw === null) {
      return { ok: true, message: "", data: null };
    }
    if (typeof raw === "boolean") {
      return { ok: raw, message: raw ? "" : "bridge returned false", data: raw };
    }
    var parsed = raw;
    if (typeof raw === "string") {
      try {
        parsed = JSON.parse(raw);
      } catch (err) {
        parsed = raw.trim();
      }
    }
    if (parsed !== null && typeof parsed === "object" && "code" in parsed) {
      var data = parsed.data;
      if (typeof data === "string") {
        try {
          data = JSON.parse(data);
        } catch (err) {
          // keep the raw string
        }
      }
      if (parsed.code !== 0) {
        return { ok: false, message: parsed.message || "bridge error code " + parsed.code, data: data };
      }
      if (data === false) {
        return { ok: false, message: parsed.message || "bridge returned false", data: data };
      }
      return { ok: true, message: parsed.message || "", data: data };
    }
    if (parsed === true || parsed === false) {
      return { ok: parsed, message: parsed ? "" : "bridge returned false", data: parsed };
    }
    if (parsed === "true") {
      return { ok: true, message: "", data: true };
    }
    if (parsed === "false") {
      return { ok: false, message: "bridge returned false", data: false };
    }
    return { ok: true, message: "", data: parsed };
  }

  function callBridge(bridge, method) {
    var args = Array.prototype.slice.call(arguments, 2);
    if (!bridge || typeof bridge[method] !== "function") {
      return { ok: false, message: method + " is not available on djiBridge", data: null };
    }
    var raw;
    try {
      raw = bridge[method].apply(bridge, args);
    } catch (err) {
      var detail = err && err.message ? err.message : String(err);
      return { ok: false, message: method + " threw: " + detail, data: null };
    }
    return parseBridgeReturn(raw);
  }

  function isConnected(parsed) {
    // connect-state values: true / "true" / 1 mean attached; 0, null and
    // false-ish mean not (yet) connected
    return (
      parsed.ok &&
      parsed.data !== null &&
      parsed.data !== undefined &&
      parsed.data !== 0 &&
      parsed.data !== "0"
    );
  }

  async function fetchEnvelope(fetchFn, url, options) {
    // hub responses are {code, message, data} envelopes; code 0 = ok
    var response;
    try {
      response = await fetchFn(url, options);
    } catch (err) {
      var detail = err && err.message ? err.message : String(err);
      throw new Error("request failed: " + detail);
    }
    var body;
    try {
      body = await response.json();
    } catch (err) {
      throw new Error("bad response (http " + response.status + ")");
    }
    if (!body || body.code !== 0) {
      throw new Error((body && body.message) || "hub error (http " + response.status + ")");
    }
    return body.data;
  }

  async function runConnectFlow(deps) {
    // license verify -> login -> api -> thing (+ workspace identity) -> media
    // -> mission; each step gates the next, the first failure stops with a
    // visible error. deps: {bridge, fetchFn, apiHost, onStatus,
    // registerCallback, getCredentials, getCachedToken?, persistToken?,
    // clearToken?} - the optional token deps drive cached-session resume
    var bridge = deps.bridge;
    var fetchFn = deps.fetchFn;
    var onStatus = deps.onStatus || function () {};
    var registerCallback = deps.registerCallback || function () {};
    var result = { mode: "pilot", completed: false, failedStep: null, message: "" };

    function fail(step, message) {
      result.failedStep = step;
      result.message = message;
      onStatus(step, "error", message);
      return result;
    }

    if (!bridge) {
      result.mode = "browser";
      result.message = BROWSER_MODE_MESSAGE;
      onStatus("bridge", "browser", BROWSER_MODE_MESSAGE);
      return result;
    }

    // hub config - app credentials + attach addresses
    onStatus(STEP_LICENSE, "running", "checking license");
    var config;
    try {
      config = await fetchEnvelope(fetchFn, "/pilot/config");
    } catch (err) {
      return fail(STEP_LICENSE, "hub config: " + err.message);
    }

    // license verify
    var verify = callBridge(
      bridge,
      "platformVerifyLicense",
      config.app_id,
      config.app_key,
      config.app_license
    );
    if (!verify.ok) {
      return fail(STEP_LICENSE, "license verify: " + (verify.message || "rejected"));
    }
    var verified = callBridge(bridge, "platformIsVerified");
    if (!verified.ok) {
      return fail(STEP_LICENSE, "platform not verified: " + (verified.message || "rejected"));
    }
    onStatus(STEP_LICENSE, "ok", "license verified");

    // login - resume a cached session if its token still refreshes, otherwise
    // prompt for credentials. caching the token means a webview reload (e.g.
    // returning from the route library) doesn't force a re-login.
    var login = null;
    var cachedToken = deps.getCachedToken ? deps.getCachedToken() : null;
    if (cachedToken) {
      onStatus(STEP_LOGIN, "running", "resuming session");
      try {
        login = await fetchEnvelope(fetchFn, "/manage/api/v1/token/refresh", {
          method: "POST",
          headers: { "x-auth-token": cachedToken },
        });
      } catch (err) {
        // stale/expired token - drop it and fall back to the form
        if (deps.clearToken) deps.clearToken();
        login = null;
      }
    }
    if (!login) {
      onStatus(STEP_LOGIN, "waiting", "enter credentials");
      var credentials = await deps.getCredentials();
      onStatus(STEP_LOGIN, "running", "logging in");
      try {
        login = await fetchEnvelope(fetchFn, "/manage/api/v1/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: credentials.username,
            password: credentials.password,
            flag: PILOT_LOGIN_FLAG,
          }),
        });
      } catch (err) {
        return fail(STEP_LOGIN, "login: " + err.message);
      }
    }
    if (deps.persistToken) deps.persistToken(login.access_token);
    onStatus(STEP_LOGIN, "ok", "logged in as " + login.username);

    // api module - http host + token for pilot-initiated calls
    var api = callBridge(
      bridge,
      "platformLoadComponent",
      "api",
      JSON.stringify({ host: deps.apiHost, token: login.access_token })
    );
    if (!api.ok) {
      return fail(STEP_API, "api module: " + (api.message || "load failed"));
    }
    onStatus(STEP_API, "ok", "api module loaded");

    // thing module - mqtt attach, connect callback registered first so no
    // state change is missed
    registerCallback(THING_CALLBACK_NAME, function (state) {
      var parsed = parseBridgeReturn(state);
      if (isConnected(parsed)) {
        onStatus(STEP_MQTT, "ok", "mqtt connected");
      } else {
        onStatus(STEP_MQTT, "waiting", "mqtt disconnected");
      }
    });
    var thing = callBridge(
      bridge,
      "platformLoadComponent",
      "thing",
      JSON.stringify({
        host: login.mqtt_addr,
        username: login.mqtt_username,
        password: login.mqtt_password,
        connectCallback: THING_CALLBACK_NAME,
      })
    );
    if (!thing.ok) {
      return fail(STEP_MQTT, "thing module: " + (thing.message || "load failed"));
    }

    var workspace = callBridge(bridge, "platformSetWorkspaceId", login.workspace_id);
    if (!workspace.ok) {
      return fail(STEP_MQTT, "set workspace: " + (workspace.message || "rejected"));
    }
    var info = callBridge(
      bridge,
      "platformSetInformation",
      config.platform_name,
      config.workspace_name,
      config.workspace_desc || ""
    );
    if (!info.ok) {
      return fail(STEP_MQTT, "set platform info: " + (info.message || "rejected"));
    }
    onStatus(STEP_MQTT, "waiting", "waiting for mqtt connection");

    // catch an already-connected link; later changes arrive via the callback
    if (typeof bridge.thingGetConnectState === "function") {
      var state = callBridge(bridge, "thingGetConnectState");
      if (isConnected(state)) {
        onStatus(STEP_MQTT, "ok", "mqtt connected");
      }
    }

    // media module - auto-upload originals incl. video
    var media = callBridge(bridge, "platformLoadComponent", "media", JSON.stringify(MEDIA_PARAMS));
    if (!media.ok) {
      return fail(STEP_MEDIA, "media module: " + (media.message || "load failed"));
    }
    onStatus(STEP_MEDIA, "ok", "auto-upload on (originals + video)");

    // mission module - the wayline/route library cloud sync. params empty; the
    // http host + token come from the api module (demo loadComponent('mission', {})).
    // without it pilot's flight route library never queries the wayline endpoint.
    var mission = callBridge(bridge, "platformLoadComponent", "mission", JSON.stringify({}));
    if (!mission.ok) {
      return fail(STEP_MISSION, "mission module: " + (mission.message || "load failed"));
    }
    onStatus(STEP_MISSION, "ok", "wayline sync enabled");

    result.completed = true;
    result.username = login.username;
    result.workspaceId = login.workspace_id;
    return result;
  }

  // modules runConnectFlow loads, in load order
  var LOADED_MODULES = ["api", "thing", "media", "mission"];

  function disconnect(deps) {
    // tear down the cloud link - unload the loaded components (reverse load
    // order) so pilot drops the platform connection, and clear the cached
    // token so the next load starts at the connect form. deps: {bridge,
    // clearToken?}
    var bridge = deps.bridge;
    if (bridge && typeof bridge.platformUnloadComponent === "function") {
      LOADED_MODULES.slice()
        .reverse()
        .forEach(function (name) {
          try {
            bridge.platformUnloadComponent(name);
          } catch (err) {
            // best effort - keep unloading the rest
          }
        });
    }
    if (deps.clearToken) deps.clearToken();
  }

  return {
    BROWSER_MODE_MESSAGE: BROWSER_MODE_MESSAGE,
    THING_CALLBACK_NAME: THING_CALLBACK_NAME,
    MEDIA_PARAMS: MEDIA_PARAMS,
    LOADED_MODULES: LOADED_MODULES,
    parseBridgeReturn: parseBridgeReturn,
    runConnectFlow: runConnectFlow,
    disconnect: disconnect,
  };
});
