-- Ember — Copyright (C) 2026 Ember contributors.
-- GNU GPL version 3 or later; distributed without any warranty.
-- See LICENSE for the full license and warranty disclaimer.
local millennium = require("millennium")
local utils = require("utils")
local json = require("json")
local http = require("http")
local command = @COMMAND@
local data = @DATA@

local function read_file(name)
    local file = io.open(data .. "/" .. name, "r")
    if not file then return nil end
    local value = file:read("*a")
    file:close()
    return value
end

local function ready_runtime()
    local ok, runtime = pcall(json.decode, read_file("runtime.json") or "{}")
    if not ok or type(runtime) ~= "table" or runtime.mode ~= "desktop" or type(runtime.origin) ~= "string" or not runtime.origin:match("^http://127%.0%.0%.1:%d+$") or type(runtime.token) ~= "string" then return nil end
    local fetched, response = pcall(http.request, runtime.origin .. "/api/info", {method = "GET", timeout = 1, follow_redirects = false, proxy = "", headers = {Authorization = "Bearer " .. runtime.token}})
    if not fetched or not response or response.status ~= 200 then return nil end
    local valid, info = pcall(json.decode, response.body)
    if not valid or type(info) ~= "table" or info.mode ~= "desktop" then return nil end
    return runtime
end

local function start_backend()
    if ready_runtime() then return true end
    print("[Ember] Starting backend and waiting for readiness")
    local output, code = utils.exec(command)
    if code ~= 0 then error("Ember startup failed: " .. tostring(output)) end
    if not ready_runtime() then error("Ember startup finished without an authenticated backend") end
    return true
end

local function store_language()
    local ok, runtime = pcall(json.decode, read_file("runtime.json") or "{}")
    return ok and runtime.language == "en" and "en" or "ru"
end

local function store_call(payload, request_id)
    local ok, runtime = pcall(json.decode, read_file("runtime.json") or "{}")
    if not ok or type(runtime.origin) ~= "string" or not runtime.origin:match("^http://127%.0%.0%.1:%d+$") or type(runtime.token) ~= "string" then error("Ember is not running") end
    local options = {timeout = 3, follow_redirects = false, proxy = "", headers = {Authorization = "Bearer " .. runtime.token, ["Content-Type"] = "application/json"}}
    local url = runtime.origin .. "/api/store-add"
    local response
    if payload then
        options.method = "POST"
        options.data = json.encode(payload)
        response = http.request(url, options)
    else
        if request_id then
            if type(request_id) ~= "string" or not request_id:match("^[a-f0-9]+$") or #request_id ~= 24 then return {state = "expired"} end
            url = url .. "?request_id=" .. request_id
        end
        options.method = "GET"
        response = http.request(url, options)
    end
    if not response or response.status ~= 200 then
        local status = response and tostring(response.status) or "no response"
        print("[Ember] Store handoff HTTP failure: " .. status)
        error("Ember store handoff unavailable (HTTP " .. status .. ")")
    end
    return json.decode(response.body)
end

local function request_store_add(app_id, name)
    if type(app_id) ~= "string" or not app_id:match("^[1-9]%d*$") or #app_id > 10 or tonumber(app_id) > 4294967295 then
        return {success = false, error = "invalid_app", language = store_language()}
    end
    if type(name) ~= "string" or #name > 512 then name = "App " .. app_id end
    start_backend()
    local result = store_call({action = "request", app_id = app_id, name = name})
    result.language = store_language()
    return result
end

local function acknowledge_store_add(request_id)
    return store_call({action = "acknowledge", request_id = request_id}).success
end

local function get_store_add_status(request_id)
    local result = store_call(nil, request_id)
    result.language = store_language()
    return result
end

local function get_connection()
    local heartbeat = io.open(data .. "/millennium-heartbeat.txt", "w")
    if heartbeat then heartbeat:write(tostring(os.time())); heartbeat:close() end
    local runtime = ready_runtime()
    if not runtime then return {starting = true} end
    local language = runtime.language == "en" and "en" or "ru"
    local available, addition = pcall(store_call)
    if not available then print("[Ember] Store handoff check failed: " .. tostring(addition)) end
    return {origin = runtime.origin, token = runtime.token, pid = runtime.pid, language = language, open_request = read_file("open-request.txt") or "", add_request = available and addition.request or nil}
end

_G.start_backend = start_backend
_G.get_connection = get_connection
_G.request_store_add = request_store_add
_G.acknowledge_store_add = acknowledge_store_add
_G.get_store_add_status = get_store_add_status

return {
    on_load = function()
        millennium.ready()
        start_backend()
    end,
    start_backend = start_backend,
    get_connection = get_connection,
    request_store_add = request_store_add,
    acknowledge_store_add = acknowledge_store_add,
    get_store_add_status = get_store_add_status,
}
