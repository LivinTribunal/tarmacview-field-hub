/* drives the dom-free connect flow with a recording bridge + fake fetch and
   prints a json report for one scenario - run by test_pilot_page.py via
   `node pilot_connect_driver.js <scenario>`. */
"use strict";

const path = require("path");

const connect = require(path.join(__dirname, "..", "..", "app", "static", "pilot-connect.js"));

const API_HOST = "https://192.168.8.100:8443";

const CONFIG_DATA = {
  app_id: "app-id-1",
  app_key: "app-key-1",
  app_license: "app-license-1",
  mqtt_addr: "ssl://192.168.8.100:8883",
  platform_name: "TarmacView Field Hub",
  workspace_name: "TarmacView Field",
  workspace_desc: "",
};

const LOGIN_DATA = {
  user_id: "user-1",
  username: "pilot",
  user_type: 2,
  workspace_id: "workspace-1",
  access_token: "token-1",
  mqtt_addr: "ssl://192.168.8.100:8883",
  mqtt_username: "mqtt-user",
  mqtt_password: "mqtt-pass",
};

// token/refresh returns the same shape with a fresh token (cached-session resume)
const REFRESH_DATA = Object.assign({}, LOGIN_DATA, { access_token: "token-refreshed" });

function makeBridge(events, calls, overrides) {
  const componentOverrides = (overrides && overrides.components) || {};

  function method(name, defaultReturn) {
    return function () {
      const args = Array.prototype.slice.call(arguments);
      let label = "bridge:" + name;
      if (name === "platformLoadComponent") label += ":" + args[0];
      events.push(label);
      calls.push({ method: name, args });
      if (name === "platformLoadComponent" && componentOverrides[args[0]] !== undefined) {
        return componentOverrides[args[0]];
      }
      if (overrides && overrides[name] !== undefined) return overrides[name];
      return defaultReturn;
    };
  }

  // mixed return shapes on purpose - a plain bool, a json envelope with a
  // json-encoded data string, and a void return must all parse as success
  return {
    platformVerifyLicense: method("platformVerifyLicense", true),
    platformIsVerified: method(
      "platformIsVerified",
      JSON.stringify({ code: 0, message: "ok", data: "true" })
    ),
    platformLoadComponent: method(
      "platformLoadComponent",
      JSON.stringify({ code: 0, message: "ok", data: "true" })
    ),
    platformSetWorkspaceId: method("platformSetWorkspaceId", true),
    platformSetInformation: method("platformSetInformation", undefined),
    platformUnloadComponent: method("platformUnloadComponent", true),
    thingGetConnectState: method("thingGetConnectState", false),
  };
}

function makeFetch(events, fetches, envelopes) {
  return async function (url, options) {
    const httpMethod = (options && options.method) || "GET";
    events.push("fetch:" + httpMethod + ":" + url);
    fetches.push({
      url,
      method: httpMethod,
      headers: (options && options.headers) || {},
      body: options && options.body ? JSON.parse(options.body) : null,
    });
    const envelope = envelopes[url];
    if (!envelope) {
      return { status: 404, json: async () => ({ code: 1, message: "not found", data: null }) };
    }
    return { status: 200, json: async () => envelope };
  };
}

function lastMqttStatus(statuses) {
  const mqtt = statuses.filter((s) => s.step === "mqtt");
  return mqtt[mqtt.length - 1] || null;
}

async function run(scenario) {
  const events = [];
  const calls = [];
  const fetches = [];
  const statuses = [];
  const registered = {};

  // disconnect is a standalone action (button click), not part of the flow
  if (scenario === "disconnect") {
    const store = { token: "cached-token" };
    const ops = [];
    connect.disconnect({
      bridge: makeBridge(events, calls, {}),
      clearToken: () => {
        store.token = null;
        ops.push({ op: "clear" });
      },
    });
    return { scenario, calls, tokenOps: ops, cachedToken: store.token };
  }

  const overrides = {};
  const envelopes = {
    "/pilot/config": { code: 0, message: "success", data: CONFIG_DATA },
    "/manage/api/v1/login": { code: 0, message: "success", data: LOGIN_DATA },
  };

  if (scenario === "config-fail") {
    envelopes["/pilot/config"] = {
      code: 1,
      message: "dji app credentials not configured",
      data: null,
    };
  }
  if (scenario === "verify-fail") {
    overrides.platformVerifyLicense = false;
  }
  if (scenario === "login-fail") {
    envelopes["/manage/api/v1/login"] = {
      code: 1,
      message: "invalid username or password",
      data: null,
    };
  }
  if (scenario === "thing-fail") {
    overrides.components = {
      thing: JSON.stringify({ code: 514, message: "broker unreachable", data: null }),
    };
  }

  // cached-session resume: a stored token, refreshed on load. "resume" succeeds;
  // "resume-expired" has no refresh envelope so the token is dropped -> form.
  const tokenStore = {
    token: scenario === "resume" || scenario === "resume-expired" ? "cached-token" : null,
  };
  const tokenOps = [];
  if (scenario === "resume") {
    envelopes["/manage/api/v1/token/refresh"] = {
      code: 0,
      message: "success",
      data: REFRESH_DATA,
    };
  }

  const bridge = scenario === "no-bridge" ? null : makeBridge(events, calls, overrides);

  const result = await connect.runConnectFlow({
    bridge,
    fetchFn: makeFetch(events, fetches, envelopes),
    apiHost: API_HOST,
    onStatus: (step, state, detail) => statuses.push({ step, state, detail }),
    registerCallback: (name, handler) => {
      registered[name] = handler;
    },
    getCredentials: async () => {
      events.push("credentials");
      return { username: "pilot", password: "field-test-password" };
    },
    getCachedToken: () => tokenStore.token,
    persistToken: (token) => {
      tokenStore.token = token;
      tokenOps.push({ op: "persist", token });
    },
    clearToken: () => {
      tokenStore.token = null;
      tokenOps.push({ op: "clear" });
    },
  });

  const report = {
    scenario,
    result,
    events,
    calls,
    fetches,
    statuses,
    registeredCallbacks: Object.keys(registered),
    tokenOps,
    cachedToken: tokenStore.token,
  };

  // pilot invokes the registered global with connection state changes -
  // exercise both directions after the happy flow completes
  if (scenario === "happy") {
    const callback = registered[connect.THING_CALLBACK_NAME];
    callback(false);
    report.mqttAfterDisconnect = lastMqttStatus(statuses);
    callback(true);
    report.mqttAfterConnect = lastMqttStatus(statuses);
  }

  return report;
}

run(process.argv[2] || "happy").then(
  (report) => process.stdout.write(JSON.stringify(report)),
  (err) => {
    process.stderr.write(String(err && err.stack ? err.stack : err));
    process.exit(1);
  }
);
